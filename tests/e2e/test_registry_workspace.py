#!/usr/bin/env python3
"""Product-level assertions for the Registry-prepared CDIN source graph."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--profile", choices=("tui", "gui-sdl"), required=True)
    args = parser.parse_args()

    manifest_path = args.workspace / "registry-manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"missing Registry manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    components = {
        (item["component_id"], item["variant"]): item
        for item in manifest["components"]
    }
    expected = {
        ("kernel", "default"),
        ("runtime", "default"),
        ("backend", "default"),
        ("frontend", args.profile),
    }
    if set(components) != expected:
        raise SystemExit(
            f"resolved component graph mismatch: {sorted(components)} != {sorted(expected)}"
        )

    for key, component in components.items():
        if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9]*)"
                            r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?",
                            component["version"]):
            raise SystemExit(f"invalid resolved SemVer for {key}: {component['version']}")
        units = component["source_units"]
        if len(units) != 1:
            raise SystemExit(f"expected one declared source unit for {key}, found {len(units)}")
        for unit in units:
            if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", unit["revision"]):
                raise SystemExit(f"non-immutable source revision for {key}: {unit['revision']}")
            source = args.workspace / unit["workspace_path"]
            if not source.is_dir():
                raise SystemExit(f"missing materialized source unit for {key}: {source}")

    backend = components[("backend", "default")]
    dependencies = {
        (item["component_id"], item["variant"], item["version"])
        for item in backend["dependencies"]
    }
    if not any(item[0] == "kernel" for item in dependencies):
        raise SystemExit("Backend release did not resolve its Kernel dependency")
    if not any(item[0] == "runtime" for item in dependencies):
        raise SystemExit("Backend release did not resolve its Runtime dependency")

    print(
        "Registry product E2E passed: backend -> kernel/runtime, "
        f"frontend={args.profile}, immutable sources materialized"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
