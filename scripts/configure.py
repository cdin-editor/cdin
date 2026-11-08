#!/usr/bin/env python3
"""Configure the CDIN Composition Root without shell-specific substitution."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def selected_package_version(
    manifest_path: Path, component_id: str, variant: str
) -> str:
    """Return exactly one Registry-selected package version."""
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Registry manifest is missing at {manifest_path}; prepare the Registry workspace first"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    matches = [
        item.get("version")
        for item in manifest.get("components", [])
        if item.get("component_id") == component_id
        and item.get("variant") == variant
    ]
    if len(matches) != 1 or not isinstance(matches[0], str) or not matches[0]:
        raise ValueError(
            f"expected exactly one {component_id}/{variant} release in "
            f"{manifest_path}; found {matches}"
        )
    return matches[0]


def absolute_path(value: str) -> str:
    """Render paths with forward slashes for consistent CMake parsing on Windows."""
    return Path(value).expanduser().resolve().as_posix()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", default="build")
    parser.add_argument("--prefix", default=".deps/install")
    parser.add_argument(
        "--profile",
        choices=("tui", "gui-sdl"),
        default=os.environ.get("CDIN_FRONTEND_VARIANT", "tui"),
    )
    args = parser.parse_args()

    manifest_path = (
        ROOT / ".deps" / f"registry-workspace-{args.profile}" / "registry-manifest.json"
    )
    backend_version = selected_package_version(manifest_path, "backend", "default")
    frontend_version = selected_package_version(
        manifest_path, "frontend", args.profile
    )
    gui_enabled = "ON" if args.profile == "gui-sdl" else "OFF"

    command = [
        "cmake",
        "-S", absolute_path(str(ROOT)),
        "-B", absolute_path(args.build_dir),
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_INSTALL_PREFIX={absolute_path(args.prefix)}",
        f"-DCDIN_RUNTIME_SOURCE_DIR={absolute_path(str(ROOT / '.deps' / 'src' / 'runtime'))}",
        f"-DCDIN_REGISTRY_PROFILE={args.profile}",
        f"-DCDIN_BACKEND_PACKAGE_VERSION={backend_version}",
        f"-DCDIN_FRONTEND_PACKAGE_VERSION={frontend_version}",
        f"-DCDIN_ENABLE_GUI_SDL={gui_enabled}",
    ]
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
