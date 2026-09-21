#!/usr/bin/env python3
"""Package the online-only Skill while enforcing its no-corpus size boundary."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import uuid
import zipfile


SOURCE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT_NAME = "global-ai-system-model-compliance-online-lite"
MAX_PACKAGE_BYTES = 5_000_000
REQUIRED_FILES = (
    "SKILL.md",
    "README.md",
    "agents/openai.yaml",
    "assets/questionnaire.md",
    "scripts/fetch_official_sources.py",
    "scripts/package_skill.py",
    "scripts/check_worktree_ready.py",
)

# A no-corpus package may not contain any of these directories, even if their
# contents would fit under the byte limit.
FORBIDDEN_SOURCE_DIRECTORIES = frozenset(
    {"references", "corpus", "downloads", "source-cache", "database"}
)
EXCLUDED_DIRECTORIES = frozenset({".git", "dist", "__pycache__"})
EXCLUDED_FILE_NAMES = frozenset({".DS_Store"})
EXCLUDED_SUFFIXES = frozenset({".pyc", ".pyo"})
FORBIDDEN_FILE_NAMES = frozenset({"retrieval-manifest.json"})
FORBIDDEN_SOURCE_SUFFIXES = frozenset(
    {".pdf", ".doc", ".docx", ".epub", ".html", ".htm", ".xml", ".sqlite", ".db", ".csv", ".tsv", ".parquet", ".json"}
)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def is_excluded(path: Path, source: Path) -> bool:
    relative = path.relative_to(source)
    if any(part in EXCLUDED_DIRECTORIES for part in relative.parts):
        return True
    if path.name in EXCLUDED_FILE_NAMES or path.name.startswith("._"):
        return True
    return path.suffix.lower() in EXCLUDED_SUFFIXES


def should_include(path: Path, source: Path) -> bool:
    return path.is_file() and not is_excluded(path, source)


def package_files(source: Path) -> list[Path]:
    return [path for path in sorted(source.rglob("*")) if should_include(path, source)]


def source_tree_bytes(source: Path) -> int:
    return sum(path.stat().st_size for path in package_files(source))


def validate_output_path(source: Path, output: Path) -> list[str]:
    if _is_within(output, source) and not _is_within(output, source / "dist"):
        return ["output inside the Skill directory must be under dist/"]
    return []


def validate_source(source: Path) -> list[str]:
    errors: list[str] = []
    if not source.is_dir():
        return [f"Skill source directory not found: {source}"]

    for relative in REQUIRED_FILES:
        if not (source / relative).is_file():
            errors.append(f"missing required file: {relative}")

    for path in source.rglob("*"):
        if is_excluded(path, source):
            continue
        relative = path.relative_to(source)
        if path.is_dir() and path.name in FORBIDDEN_SOURCE_DIRECTORIES:
            errors.append(f"forbidden embedded-source directory: {relative}")
        if not path.is_file():
            continue
        if path.name in FORBIDDEN_FILE_NAMES:
            errors.append(f"forbidden retrieval artifact: {relative}")
        if path.suffix.lower() in FORBIDDEN_SOURCE_SUFFIXES:
            errors.append(f"forbidden embedded-source file type: {relative}")

    payload_bytes = source_tree_bytes(source)
    if payload_bytes > MAX_PACKAGE_BYTES:
        errors.append(
            f"package source tree exceeds {MAX_PACKAGE_BYTES} bytes: {payload_bytes}"
        )
    return errors


def _archive_name(path: Path, source: Path) -> str:
    return str(PurePosixPath(PACKAGE_ROOT_NAME) / PurePosixPath(path.relative_to(source)))


def package(source: Path, output: Path) -> tuple[int, int, int]:
    """Build the ZIP atomically and return file count, source bytes, zip bytes."""

    errors = validate_source(source) + validate_output_path(source, output)
    if errors:
        raise ValueError("; ".join(errors))

    files = package_files(source)
    source_bytes = sum(path.stat().st_size for path in files)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.parent / f".{output.name}.{uuid.uuid4().hex}.part"
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, _archive_name(path, source))
        zip_bytes = temporary.stat().st_size
        if zip_bytes > MAX_PACKAGE_BYTES:
            raise ValueError(f"ZIP exceeds {MAX_PACKAGE_BYTES} bytes: {zip_bytes}")
        os.replace(temporary, output)
        return len(files), source_bytes, zip_bytes
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def inspect_zip(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    except (OSError, zipfile.BadZipFile) as error:
        return [f"cannot read ZIP: {error}"]

    expected_prefix = f"{PACKAGE_ROOT_NAME}/"
    for relative in REQUIRED_FILES:
        if expected_prefix + relative not in names:
            errors.append(f"package missing: {relative}")
    for name in names:
        parts = PurePosixPath(name).parts
        if not name.startswith(expected_prefix) or ".." in parts or name.startswith("/"):
            errors.append(f"unsafe archive path: {name}")
            continue
        if any(part in EXCLUDED_DIRECTORIES | FORBIDDEN_SOURCE_DIRECTORIES for part in parts):
            errors.append(f"package contains excluded directory: {name}")
        if PurePosixPath(name).name in EXCLUDED_FILE_NAMES | FORBIDDEN_FILE_NAMES:
            errors.append(f"package contains excluded artifact: {name}")
        if PurePosixPath(name).suffix.lower() in EXCLUDED_SUFFIXES | FORBIDDEN_SOURCE_SUFFIXES:
            errors.append(f"package contains excluded file type: {name}")
    if path.stat().st_size > MAX_PACKAGE_BYTES:
        errors.append(f"ZIP exceeds {MAX_PACKAGE_BYTES} bytes: {path.stat().st_size}")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="校验并打包在线精简版 AI 合规 Skill")
    parser.add_argument("--source", type=Path, default=SOURCE_ROOT, help="Skill 源目录")
    parser.add_argument("--output", type=Path, help="输出 ZIP 路径")
    parser.add_argument("--check-only", action="store_true", help="只检查源目录，不生成 ZIP")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    source = args.source.expanduser().resolve()
    output = (
        args.output.expanduser().resolve()
        if args.output is not None
        else source / "dist" / f"{PACKAGE_ROOT_NAME}.zip"
    )
    errors = validate_source(source) + validate_output_path(source, output)
    file_count = 0
    source_bytes = source_tree_bytes(source) if source.is_dir() else 0
    zip_bytes: int | None = None

    if not errors and not args.check_only:
        try:
            file_count, source_bytes, zip_bytes = package(source, output)
            errors.extend(inspect_zip(output))
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            errors.append(str(error))

    result = {
        "valid": not errors,
        "source": str(source),
        "output": str(output),
        "file_count": file_count,
        "source_tree_bytes": source_bytes,
        "zip_bytes": zip_bytes,
        "max_package_bytes": MAX_PACKAGE_BYTES,
        "errors": errors,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif errors:
        for error in errors:
            print("ERROR: " + error)
    elif args.check_only:
        print(f"Skill source is ready to package ({source_bytes} bytes).")
    else:
        print(f"Packaged {file_count} files ({zip_bytes} bytes): {output}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
