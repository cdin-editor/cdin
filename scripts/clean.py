#!/usr/bin/env python3
"""Remove generated CDIN build and Registry workspace directories portably."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def remove(path: Path) -> None:
    resolved = path.absolute()
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError(f"refusing to remove a path outside the repository: {resolved}") from exc
    if resolved.is_dir() and not resolved.is_symlink():
        shutil.rmtree(resolved)
    elif resolved.exists() or resolved.is_symlink():
        resolved.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", default="build")
    args = parser.parse_args()
    paths = [
        ROOT / args.build_dir,
        ROOT / "build-tests",
        ROOT / "dist",
        *ROOT.glob(".deps/registry-workspace-*"),
        *ROOT.glob(".deps/registry-replay-*"),
    ]
    for path in paths:
        remove(path)
        print(f"removed {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
