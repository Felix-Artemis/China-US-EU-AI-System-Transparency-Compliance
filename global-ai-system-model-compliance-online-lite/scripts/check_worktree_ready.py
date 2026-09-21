#!/usr/bin/env python3
"""Diagnose an unborn Git HEAD before a task tries to create a worktree."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def check(root: Path) -> dict[str, object]:
    """Return whether ``HEAD`` can safely be passed to ``git worktree add``."""

    repository = _git(root, "rev-parse", "--show-toplevel")
    if repository.returncode != 0:
        return {
            "ready": False,
            "reason": "not_a_git_repository",
            "detail": repository.stderr.strip() or "Git repository not found",
        }

    repo_root = Path(repository.stdout.strip())
    head = _git(repo_root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    if head.returncode != 0:
        return {
            "ready": False,
            "reason": "head_missing",
            "repository": str(repo_root),
            "detail": (
                "This repository has no valid commit at HEAD, so HEAD is not a valid "
                "worktree reference."
            ),
            "repair": "Create the intended first commit before running git worktree add.",
        }

    return {
        "ready": True,
        "repository": str(repo_root),
        "head": head.stdout.strip(),
        "detail": "HEAD is a valid commit reference for git worktree add.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查当前仓库能否以 HEAD 创建 Git worktree")
    parser.add_argument("--root", type=Path, default=Path("."), help="仓库或其子目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)
    result = check(args.root.expanduser().resolve())

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ready"]:
        print(result["detail"])
    elif result["reason"] == "head_missing":
        print("ERROR: " + str(result["detail"]))
        print("Repair: " + str(result["repair"]))
    else:
        print("ERROR: " + str(result["detail"]))
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
