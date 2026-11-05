#!/usr/bin/env python3
"""Checkout immutable component revisions recorded in deps.lock."""
from __future__ import annotations
import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "deps.lock"
DEST = ROOT / ".deps" / "src"


def run(args: list[str], cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True)


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
            run(["git", "clone", "--no-checkout", dep["repository"], str(target)])
        actual = subprocess.check_output(
            ["git", "-C", str(target), "rev-parse", "HEAD"], text=True
        ).strip()
        if actual != revision:
            if args.verify:
                print(f"MISMATCH {name}: expected {revision}, found {actual}", file=sys.stderr)
                return 1
            run(["git", "-C", str(target), "fetch", "--depth", "1", "origin", revision])
            run(["git", "-C", str(target), "checkout", "--detach", revision])
        print(f"OK {name} {revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
