#!/usr/bin/env python3
"""Retrieve current official sources without bundling a local legal corpus.

The URL registry intentionally lives in this script. Downloaded material must
stay outside the Skill directory and is recorded in an external manifest.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.parse
import urllib.request
import uuid


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAX_BYTES = 50 * 1024 * 1024
MANIFEST_NAME = "retrieval-manifest.json"

# These are exact hosts, not suffix matches. Add a host only after confirming
# that it is an official publisher or an expected official redirect target.
APPROVED_HOSTS = frozenset(
    {
        "www.gov.cn",
        "eur-lex.europa.eu",
        "ec.europa.eu",
        "digital-strategy.ec.europa.eu",
        "commission.europa.eu",
        "op.europa.eu",
        "ai-act-service-desk.ec.europa.eu",
        "leginfo.legislature.ca.gov",
        "www.justice.gov",
    }
)


@dataclass(frozen=True)
class OfficialSource:
    """A source locator, not a bundled copy of the source."""

    identifier: str
    title: str
    url: str
    jurisdiction: str
    topics: tuple[str, ...]
    legal_character: str
    filename: str
    note: str


SOURCE_REGISTRY = (
    OfficialSource(
        "cn-generative-ai-service-measures",
        "生成式人工智能服务管理暂行办法",
        "https://www.gov.cn/zhengce/202310/content_6909368.htm",
        "中国大陆",
        ("transparency",),
        "行政规章/规范性文件，需按当前有效文本核验",
        "cn-generative-ai-service-measures.html",
        "生成式人工智能服务与相关内容标识、服务管理事实的官方入口。",
    ),
    OfficialSource(
        "cn-deep-synthesis-provisions",
        "互联网信息服务深度合成管理规定",
        "https://www.gov.cn/zhengce/zhengceku/202307/content_6891752.htm",
        "中国大陆",
        ("transparency",),
        "行政规章/规范性文件，需按当前有效文本核验",
        "cn-deep-synthesis-provisions.html",
        "深度合成服务和生成/编辑内容标识事实的官方入口。",
    ),
    OfficialSource(
        "cn-ai-generated-content-labeling-measures",
        "人工智能生成合成内容标识办法",
        "https://www.gov.cn/zhengce/zhengceku/202503/content_7014286.htm",
        "中国大陆",
        ("transparency",),
        "行政规章/规范性文件，需按当前有效文本核验",
        "cn-ai-generated-content-labeling-measures.html",
        "生成合成内容显式和隐式标识事实的官方入口。",
    ),
    OfficialSource(
        "eu-ai-act",
        "Regulation (EU) 2024/1689, consolidated text",
        "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02024R1689",
        "欧盟",
        ("transparency", "eu-ai-act"),
        "欧盟法规；应核对适用日期、修订和具体条款",
        "eu-ai-act.html",
        "EU AI Act 的官方整合文本入口。",
    ),
    OfficialSource(
        "eu-ai-act-2026-update",
        "Regulation (EU) 2026/1744 official text",
        "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32026R1744",
        "欧盟",
        ("eu-ai-act",),
        "欧盟法规文本；须先确认其与本产品及 AI Act 的关系",
        "eu-ai-act-2026-update.html",
        "用于核对 AI Act 相关的最新欧盟官方法规文本。",
    ),
    OfficialSource(
        "eu-article-50-guidance",
        "European Commission Article 50 transparency guidance",
        "https://ec.europa.eu/newsroom/dae/redirection/document/131215",
        "欧盟",
        ("transparency", "eu-ai-act"),
        "欧盟委员会官方指导，不是独立法定义务",
        "eu-article-50-guidance.pdf",
        "用于理解 AI Act 透明度义务的官方指导入口。",
    ),
    OfficialSource(
        "eu-gpai-guidelines",
        "European Commission GPAI guidance document",
        "https://ec.europa.eu/newsroom/dae/redirection/document/112367",
        "欧盟",
        ("eu-ai-act",),
        "欧盟委员会官方指导，不是独立法定义务",
        "eu-gpai-guidelines.pdf",
        "用于 GPAI 模型相关事实和官方解释的入口。",
    ),
    OfficialSource(
        "eu-gpai-code-of-practice",
        "General-Purpose AI Code of Practice",
        "https://ec.europa.eu/newsroom/dae/redirection/document/118340",
        "欧盟",
        ("eu-ai-act",),
        "官方发布的行为准则/良好实践，不是独立法定义务或安全港",
        "eu-gpai-code-of-practice.pdf",
        "用于区分 GPAI 的法律义务与自愿性良好实践。",
    ),
    OfficialSource(
        "eu-gdpr",
        "Regulation (EU) 2016/679 (GDPR)",
        "https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng",
        "欧盟",
        ("data-adjacent",),
        "欧盟法规；应核对适用事实和当前有效文本",
        "eu-gdpr.html",
        "仅在产品涉及个人数据、角色或跨境传输问题时使用。",
    ),
    OfficialSource(
        "ca-ai-transparency-bill-sb942",
        "California SB 942 official bill text",
        "https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202320240SB942",
        "美国加州",
        ("transparency",),
        "官方立法文本；必须另行核对是否已通过、生效及当前版本",
        "ca-sb942.html",
        "加州 AI 透明度立法事实的官方文本入口。",
    ),
    OfficialSource(
        "ca-ai-bill-ab853",
        "California AB 853 official bill text",
        "https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202520260AB853",
        "美国加州",
        ("transparency",),
        "官方立法文本；必须另行核对是否已通过、生效及当前版本",
        "ca-ab853.html",
        "加州 AI 相关立法事实的官方文本入口。",
    ),
    OfficialSource(
        "ca-ai-bill-history-sb1000",
        "California SB 1000 official bill history",
        "https://leginfo.legislature.ca.gov/faces/billHistoryClient.xhtml?bill_id=202520260SB1000",
        "美国加州",
        ("transparency",),
        "官方立法状态页面；不是独立义务文本",
        "ca-sb1000-history.html",
        "用于确认有关加州法案的当前状态，而非据此直接下结论。",
    ),
    OfficialSource(
        "ca-ccpa-cpra",
        "California Consumer Privacy Act official Civil Code text",
        "https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml?division=3.&part=4.&lawCode=CIV&title=1.81.5.",
        "美国加州",
        ("data-adjacent",),
        "加州成文法官方文本；应核对适用条件和当前有效版本",
        "ca-ccpa-cpra.html",
        "仅在个人信息、消费者权利或服务提供商关系被触发时使用。",
    ),
    OfficialSource(
        "us-data-security",
        "U.S. Department of Justice Data Security Program",
        "https://www.justice.gov/nsd/data-security",
        "美国",
        ("data-adjacent",),
        "美国司法部官方项目入口；应按业务事实和当前规则核验",
        "us-doj-data-security.html",
        "仅在敏感数据、受限国家或相关数据交易事实被触发时使用。",
    ),
)

SOURCE_BY_ID = {source.identifier: source for source in SOURCE_REGISTRY}
TOPICS = tuple(sorted({topic for source in SOURCE_REGISTRY for topic in source.topics}))


class SourceDownloadError(RuntimeError):
    """A source could not be retrieved under the downloader's guardrails."""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def approved_url_error(url: str) -> str | None:
    """Return a reason when ``url`` is outside the fixed official allowlist."""

    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() != "https":
        return "only HTTPS URLs are allowed"
    if parsed.username is not None or parsed.password is not None:
        return "URLs with user credentials are not allowed"
    try:
        port = parsed.port
    except ValueError:
        return "URL has an invalid port"
    if port not in (None, 443):
        return "only the default HTTPS port is allowed"
    hostname = parsed.hostname
    if not hostname:
        return "URL has no hostname"
    if hostname.lower() not in APPROVED_HOSTS:
        return f"host is not approved: {hostname}"
    return None


def require_approved_url(url: str) -> None:
    error = approved_url_error(url)
    if error:
        raise SourceDownloadError(error)


class ApprovedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects unless their resolved target is another approved URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        target = urllib.parse.urljoin(req.full_url, newurl)
        require_approved_url(target)
        return super().redirect_request(req, fp, code, msg, headers, target)


def source_as_dict(source: OfficialSource) -> dict[str, object]:
    return {
        "id": source.identifier,
        "title": source.title,
        "url": source.url,
        "jurisdiction": source.jurisdiction,
        "topics": list(source.topics),
        "legal_character": source.legal_character,
        "filename": source.filename,
        "note": source.note,
    }


def select_sources(
    source_ids: list[str] | tuple[str, ...] = (),
    topics: list[str] | tuple[str, ...] = (),
    include_all: bool = False,
) -> tuple[OfficialSource, ...]:
    """Select the union of explicit sources, topic sources, and ``--all``."""

    unknown_sources = sorted(set(source_ids) - SOURCE_BY_ID.keys())
    if unknown_sources:
        raise ValueError("unknown source id: " + ", ".join(unknown_sources))
    unknown_topics = sorted(set(topics) - set(TOPICS))
    if unknown_topics:
        raise ValueError("unknown topic: " + ", ".join(unknown_topics))
    if not source_ids and not topics and not include_all:
        raise ValueError("select at least one --source, --topic, or --all")

    selected_ids = set(source_ids)
    selected_topics = set(topics)
    selected: list[OfficialSource] = []
    for source in SOURCE_REGISTRY:
        if include_all or source.identifier in selected_ids or selected_topics.intersection(source.topics):
            selected.append(source)
    return tuple(selected)


def validate_output_dir(output_dir: Path, skill_root: Path = SKILL_ROOT) -> Path:
    """Resolve an external output directory without creating it."""

    candidate = output_dir.expanduser().resolve()
    root = skill_root.resolve()
    if _is_within(candidate, root):
        raise ValueError("--output-dir must be outside the Skill directory")
    return candidate


def _safe_target(output_dir: Path, source: OfficialSource) -> Path:
    filename = Path(source.filename)
    if filename.name != source.filename or source.filename in {"", ".", ".."}:
        raise SourceDownloadError(f"unsafe registered filename for {source.identifier}")
    return output_dir / filename


def _unlink_if_present(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def download_source(
    source: OfficialSource,
    output_dir: Path,
    max_bytes: int,
    timeout: float = 30.0,
    opener: urllib.request.OpenerDirector | None = None,
) -> dict[str, object]:
    """Download one source atomically and return an auditable result record."""

    started_at = utc_timestamp()
    result: dict[str, object] = {
        "id": source.identifier,
        "title": source.title,
        "source_url": source.url,
        "legal_character": source.legal_character,
        "status": "failed",
        "retrieved_at": started_at,
    }
    temporary_path: Path | None = None

    try:
        require_approved_url(source.url)
        target = _safe_target(output_dir, source)
        temporary_path = output_dir / f".{target.name}.{uuid.uuid4().hex}.part"
        active_opener = opener or urllib.request.build_opener(ApprovedRedirectHandler())
        request = urllib.request.Request(
            source.url,
            headers={"User-Agent": "ai-compliance-online-lite/1.0"},
        )
        with active_opener.open(request, timeout=timeout) as response:
            final_url = response.geturl()
            require_approved_url(final_url)
            result["final_url"] = final_url
            content_length = response.headers.get("Content-Length")
            if content_length and content_length.isdigit() and int(content_length) > max_bytes:
                raise SourceDownloadError(
                    f"response exceeds --max-bytes ({content_length} > {max_bytes})"
                )

            digest = hashlib.sha256()
            total_bytes = 0
            with temporary_path.open("xb") as destination:
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        raise SourceDownloadError(
                            f"response exceeds --max-bytes ({total_bytes} > {max_bytes})"
                        )
                    digest.update(chunk)
                    destination.write(chunk)

        os.replace(temporary_path, target)
        temporary_path = None
        result.update(
            {
                "status": "downloaded",
                "path": str(target),
                "bytes": total_bytes,
                "sha256": digest.hexdigest(),
            }
        )
    # Network libraries can raise protocol-specific exceptions outside the
    # common URLError family. Record every ordinary retrieval failure.
    except Exception as error:
        result["error"] = str(error)
    finally:
        if temporary_path is not None:
            _unlink_if_present(temporary_path)
    return result


def write_manifest(output_dir: Path, results: list[dict[str, object]]) -> Path:
    """Atomically write the record for this retrieval attempt."""

    manifest = {
        "generated_at": utc_timestamp(),
        "skill": "global-ai-system-model-compliance-online-lite",
        "source_mode": "online_only",
        "results": results,
    }
    destination = output_dir / MANIFEST_NAME
    temporary = output_dir / f".{MANIFEST_NAME}.{uuid.uuid4().hex}.part"
    try:
        with temporary.open("x", encoding="utf-8") as file:
            json.dump(manifest, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary, destination)
    finally:
        _unlink_if_present(temporary)
    return destination


def _print_result(result: dict[str, object], json_output: bool) -> None:
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    mode = result["mode"]
    if mode in {"list", "dry_run"}:
        prefix = "Available" if mode == "list" else "Planned"
        for source in result["sources"]:  # type: ignore[index]
            print(
                f"{prefix}: {source['id']} [{', '.join(source['topics'])}]\n"
                f"  {source['title']}\n  {source['url']}\n"
                f"  {source['legal_character']}"
            )
        return

    for item in result["results"]:  # type: ignore[index]
        if item["status"] == "downloaded":
            print(f"Downloaded: {item['id']} -> {item['path']}")
        else:
            print(f"FAILED: {item['id']}: {item.get('error', 'unknown error')}")
    print(f"Manifest: {result['manifest']}")


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从内置官方 URL 注册表下载当前合规资料（不含本地法规库）"
    )
    parser.add_argument("--list", action="store_true", help="列出全部官方来源")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出清单或结果")
    parser.add_argument("--source", action="append", default=[], metavar="SOURCE_ID", help="选择来源 ID，可重复")
    parser.add_argument("--topic", action="append", default=[], metavar="TOPIC", help="选择主题，可重复")
    parser.add_argument("--all", action="store_true", help="选择全部注册来源")
    parser.add_argument("--dry-run", action="store_true", help="只显示下载计划，不访问网络或写文件")
    parser.add_argument("--output-dir", type=Path, help="Skill 根目录之外的证据输出目录")
    parser.add_argument(
        "--max-bytes",
        type=positive_int,
        default=DEFAULT_MAX_BYTES,
        help=f"单个文件最大字节数，默认 {DEFAULT_MAX_BYTES}",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="每个请求的超时秒数，默认 30")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    try:
        if args.list:
            sources = select_sources(args.source, args.topic, args.all) if (
                args.source or args.topic or args.all
            ) else SOURCE_REGISTRY
            _print_result(
                {"mode": "list", "sources": [source_as_dict(source) for source in sources]},
                args.json,
            )
            return 0

        sources = select_sources(args.source, args.topic, args.all)
        if args.dry_run:
            output_dir = (
                str(validate_output_dir(args.output_dir)) if args.output_dir is not None else None
            )
            _print_result(
                {
                    "mode": "dry_run",
                    "output_dir": output_dir,
                    "sources": [source_as_dict(source) for source in sources],
                },
                args.json,
            )
            return 0

        if args.output_dir is None:
            parser.error("--output-dir is required unless --list or --dry-run is used")
        output_dir = validate_output_dir(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    except ValueError as error:
        parser.error(str(error))

    results = [download_source(source, output_dir, args.max_bytes, args.timeout) for source in sources]
    try:
        manifest = write_manifest(output_dir, results)
    except OSError as error:
        print(f"ERROR: could not write retrieval manifest: {error}", file=sys.stderr)
        return 1

    _print_result(
        {"mode": "download", "manifest": str(manifest), "results": results},
        args.json,
    )
    return 0 if all(item["status"] == "downloaded" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
