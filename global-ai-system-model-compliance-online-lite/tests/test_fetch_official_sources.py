from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "fetch_official_sources.py"


def load_fetch_module():
    spec = importlib.util.spec_from_file_location("online_lite_fetch", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


fetch = load_fetch_module()


class FakeResponse:
    def __init__(self, url: str, chunks: list[bytes]) -> None:
        self.url = url
        self.chunks = chunks
        self.headers: dict[str, str] = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def geturl(self) -> str:
        return self.url

    def read(self, size: int) -> bytes:
        return self.chunks.pop(0) if self.chunks else b""


class FakeOpener:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    def open(self, request, timeout: float):
        return self.response


class FetchOfficialSourcesTests(unittest.TestCase):
    def test_registry_only_uses_approved_https_urls(self) -> None:
        identifiers = [source.identifier for source in fetch.SOURCE_REGISTRY]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        for source in fetch.SOURCE_REGISTRY:
            self.assertIsNone(fetch.approved_url_error(source.url), source.identifier)

    def test_non_official_and_non_https_urls_are_rejected(self) -> None:
        self.assertIsNotNone(fetch.approved_url_error("http://www.gov.cn/example"))
        self.assertIsNotNone(fetch.approved_url_error("https://example.com/example"))
        self.assertIsNotNone(fetch.approved_url_error("https://www.gov.cn:444/example"))

    def test_topic_selection_is_stable_and_deduplicated(self) -> None:
        selected = fetch.select_sources(
            source_ids=["eu-ai-act"], topics=["eu-ai-act"], include_all=False
        )
        identifiers = [source.identifier for source in selected]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertIn("eu-ai-act", identifiers)
        self.assertTrue(all("eu-ai-act" in source.topics for source in selected))

    def test_unknown_topic_and_source_are_errors(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown topic"):
            fetch.select_sources(topics=["not-a-topic"])
        with self.assertRaisesRegex(ValueError, "unknown source"):
            fetch.select_sources(source_ids=["not-a-source"])

    def test_skill_internal_output_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside the Skill directory"):
            fetch.validate_output_dir(SKILL_ROOT / "downloads")

    def test_dry_run_creates_no_output_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory) / "evidence"
            with contextlib.redirect_stdout(io.StringIO()):
                status = fetch.main(
                    [
                        "--topic",
                        "transparency",
                        "--dry-run",
                        "--output-dir",
                        str(output_dir),
                        "--json",
                    ]
                )
            self.assertEqual(status, 0)
            self.assertFalse(output_dir.exists())

    def test_failed_download_removes_partial_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            source = fetch.SOURCE_REGISTRY[0]
            result = fetch.download_source(
                source,
                output_dir,
                max_bytes=2,
                opener=FakeOpener(FakeResponse(source.url, [b"too-large"])),
            )
            self.assertEqual(result["status"], "failed")
            self.assertEqual(list(output_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
