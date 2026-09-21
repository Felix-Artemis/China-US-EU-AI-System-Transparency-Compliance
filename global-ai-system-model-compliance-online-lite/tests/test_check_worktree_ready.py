from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "check_worktree_ready.py"


def load_worktree_module():
    spec = importlib.util.spec_from_file_location("online_lite_worktree", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


worktree = load_worktree_module()


class CheckWorktreeReadyTests(unittest.TestCase):
    def test_unborn_head_has_actionable_diagnosis(self) -> None:
        repository = Path("/tmp/example-repository")
        responses = [
            subprocess.CompletedProcess([], 0, stdout=str(repository) + "\n", stderr=""),
            subprocess.CompletedProcess([], 128, stdout="", stderr="fatal: Needed a single revision"),
        ]
        with patch.object(worktree, "_git", side_effect=responses):
            result = worktree.check(repository)
        self.assertFalse(result["ready"])
        self.assertEqual(result["reason"], "head_missing")
        self.assertIn("first commit", result["repair"])

    def test_valid_head_is_ready(self) -> None:
        repository = Path("/tmp/example-repository")
        responses = [
            subprocess.CompletedProcess([], 0, stdout=str(repository) + "\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="abc123\n", stderr=""),
        ]
        with patch.object(worktree, "_git", side_effect=responses):
            result = worktree.check(repository)
        self.assertTrue(result["ready"])
        self.assertEqual(result["head"], "abc123")


if __name__ == "__main__":
    unittest.main()
