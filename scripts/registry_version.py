#!/usr/bin/env python3
"""Print one selected component version from the Registry Resolved Manifest."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("component")
    parser.add_argument("--variant", default="default")
    parser.add_argument("--profile", choices=("tui", "gui-sdl"),
                        default=os.environ.get("CDIN_FRONTEND_VARIANT", "tui"))
    args = parser.parse_args()
    manifest = (
        ROOT / ".deps" / f"registry-workspace-{args.profile}" / "registry-manifest.json"
    )
    if not manifest.is_file():
        raise SystemExit(f"Registry manifest not found: {manifest}; run make registry")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    matches = [
        item["version"] for item in data["components"]
        if item["component_id"] == args.component and item["variant"] == args.variant
    ]
    if len(matches) != 1:
        raise SystemExit(
            f"expected one {args.component}/{args.variant} release in {manifest}, found {matches}"
        )
    print(matches[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
