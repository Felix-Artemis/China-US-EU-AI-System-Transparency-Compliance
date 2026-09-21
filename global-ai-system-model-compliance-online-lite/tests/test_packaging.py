from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "package_skill.py"


def load_package_module():
    spec = importlib.util.spec_from_file_location("online_lite_package", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


package_skill = load_package_module()


class PackageSkillTests(unittest.TestCase):
    def test_package_has_runtime_files_and_stays_under_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "online-lite.zip"
            file_count, source_bytes, zip_bytes = package_skill.package(SKILL_ROOT, output)
            self.assertGreater(file_count, 0)
            self.assertLessEqual(source_bytes, package_skill.MAX_PACKAGE_BYTES)
            self.assertLessEqual(zip_bytes, package_skill.MAX_PACKAGE_BYTES)
            self.assertEqual(package_skill.inspect_zip(output), [])
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
            prefix = package_skill.PACKAGE_ROOT_NAME + "/"
            self.assertIn(prefix + "SKILL.md", names)
            self.assertIn(prefix + "README.md", names)
            self.assertIn(prefix + "scripts/fetch_official_sources.py", names)

    def test_embedded_source_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            copy_root = Path(temporary_directory) / "skill"
            shutil.copytree(SKILL_ROOT, copy_root, ignore=shutil.ignore_patterns("dist"))
            (copy_root / "downloads").mkdir()
            errors = package_skill.validate_source(copy_root)
            self.assertTrue(any("forbidden embedded-source directory" in error for error in errors))

    def test_os_metadata_is_not_shipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            copy_root = temporary_root / "skill"
            shutil.copytree(SKILL_ROOT, copy_root, ignore=shutil.ignore_patterns("dist"))
            (copy_root / ".DS_Store").write_bytes(b"metadata")
            output = temporary_root / "package.zip"
            package_skill.package(copy_root, output)
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
            self.assertFalse(any(name.endswith(".DS_Store") for name in names))

    def test_output_inside_source_requires_dist_directory(self) -> None:
        errors = package_skill.validate_output_path(SKILL_ROOT, SKILL_ROOT / "package.zip")
        self.assertEqual(errors, ["output inside the Skill directory must be under dist/"])


if __name__ == "__main__":
    unittest.main()
