#!/usr/bin/env python3
"""Checkout and verify immutable component revisions recorded in deps.lock."""
from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "deps.lock"
DEST = ROOT / ".deps" / "src"


def run(args: list[str]) -> None:
    subprocess.run(args, check=True)


def git_output(target: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(target), *args], text=True
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true", help="verify existing checkouts only")
    args = parser.parse_args()
    data = tomllib.loads(LOCK.read_text(encoding="utf-8"))

    for name, dep in data["dependencies"].items():
        target = DEST / name
        revision = dep["revision"]

        if not target.exists():
            if args.verify:
                print(f"MISSING {name}: {target}", file=sys.stderr)
                return 1
            target.parent.mkdir(parents=True, exist_ok=True)
            # The explicit checkout below is required: clone --no-checkout can
            # set HEAD to the right commit while leaving the worktree empty.
            run(["git", "clone", "--no-checkout", dep["repository"], str(target)])

        try:
            actual = git_output(target, "rev-parse", "HEAD")
        except subprocess.CalledProcessError:
            print(f"INVALID CHECKOUT {name}: {target}", file=sys.stderr)
            return 1

        if actual != revision:
            if args.verify:
                print(f"MISMATCH {name}: expected {revision}, found {actual}", file=sys.stderr)
                return 1
            run(["git", "-C", str(target), "fetch", "--depth", "1", "origin", revision])

        if args.verify:
            tracked = git_output(target, "ls-tree", "-r", "--name-only", revision).splitlines()
            missing = [path for path in tracked if not (target / path).is_file()]
            if not tracked or missing:
                preview = ", ".join(missing[:5]) or "(no tracked files)"
                print(f"NOT CHECKED OUT {name}: {preview}", file=sys.stderr)
                return 1
        else:
            # Always materialize the exact source tree, even when HEAD already
            # equals the pin. Never build from an empty or stale worktree.
            run(["git", "-C", str(target), "checkout", "--detach", "--force", revision])

        materialized = git_output(target, "rev-parse", "HEAD")
        if materialized != revision:
            print(f"CHECKOUT MISMATCH {name}: expected {revision}, found {materialized}", file=sys.stderr)
            return 1
        print(f"OK {name} {revision}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
