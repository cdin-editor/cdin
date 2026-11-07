#!/usr/bin/env python3
"""Resolve, prepare, verify and replay the immutable CDIN component workspace."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "deps.lock"
REGISTRY_SOURCE = ROOT / ".deps" / "tools" / "registry"
REGISTRY_BUILD = ROOT / "build" / "tools"
WORKSPACE_ROOT = ROOT / ".deps"


def run(command: list[str], *, cwd: Path = ROOT) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def profile_name(value: str) -> str:
    if value not in {"tui", "gui-sdl"}:
        raise ValueError(f"unsupported Frontend variant: {value}")
    return value


def load_lock() -> dict:
    return tomllib.loads(LOCK.read_text(encoding="utf-8"))


def registry_pin() -> tuple[str, str]:
    entry = load_lock()["tooling"]["registry"]
    return entry["repository"], entry["revision"]


def checkout_registry() -> None:
    repository, revision = registry_pin()
    REGISTRY_SOURCE.parent.mkdir(parents=True, exist_ok=True)
    if not REGISTRY_SOURCE.exists():
        run(["git", "clone", "--no-checkout", repository, str(REGISTRY_SOURCE)])
    run(["git", "-C", str(REGISTRY_SOURCE), "fetch", "--depth", "1", "origin", revision])
    run(["git", "-C", str(REGISTRY_SOURCE), "checkout", "--detach", "--force", revision])
    actual = subprocess.check_output(
        ["git", "-C", str(REGISTRY_SOURCE), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != revision:
        raise RuntimeError(f"Registry source pin mismatch: expected {revision}, found {actual}")


def build_registry() -> Path:
    if shutil.which("git") is None or shutil.which("go") is None:
        raise RuntimeError("Registry preparation requires Git and Go 1.27.3 or newer")
    checkout_registry()
    run(["go", "test", "./..."], cwd=REGISTRY_SOURCE)
    REGISTRY_BUILD.mkdir(parents=True, exist_ok=True)
    binary = REGISTRY_BUILD / ("registry.exe" if os.name == "nt" else "registry")
    run(["go", "build", "-trimpath", "-o", str(binary), "./cmd/registry"], cwd=REGISTRY_SOURCE)
    return binary


def paths(profile: str) -> tuple[Path, Path, Path]:
    product = ROOT / "registry" / f"product-definition.{profile}.yaml"
    workspace = WORKSPACE_ROOT / f"registry-workspace-{profile}"
    replay = WORKSPACE_ROOT / f"registry-replay-{profile}"
    return product, workspace, replay


def verify_workspace(binary: Path, profile: str) -> None:
    product, workspace, _ = paths(profile)
    manifest_path = workspace / "registry-manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"Registry workspace is missing: {manifest_path}")
    run([str(binary), "manifest", "verify", "--input", str(manifest_path)])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {"kernel", "runtime", "backend", "frontend"}
    selected = {item["component_id"] for item in manifest["components"]}
    if selected != required:
        raise RuntimeError(f"Registry selected {sorted(selected)}, expected {sorted(required)}")
    frontend = next(item for item in manifest["components"] if item["component_id"] == "frontend")
    if frontend["variant"] != profile:
        raise RuntimeError(
            f"Registry selected Frontend variant {frontend['variant']!r}, expected {profile!r}"
        )
    for component in manifest["components"]:
        for source in component["source_units"]:
            materialized = workspace / source["workspace_path"]
            if not materialized.is_dir():
                raise RuntimeError(f"Registry source unit is missing: {materialized}")


def prepare(profile: str, binary: Path) -> None:
    product, workspace, replay = paths(profile)
    catalog = ROOT / "registry" / "catalog-index.json"
    if workspace.exists() or replay.exists():
        raise RuntimeError(
            f"Registry output already exists for {profile}; remove {workspace} and {replay} "
            "explicitly before preparing again"
        )
    run([str(binary), "validate", "product-definition", str(product)])
    run([str(binary), "validate", "catalog-index", str(catalog)])
    common = [
        "--product", str(product),
        "--catalog", str(catalog),
        "--allow-host", "raw.githubusercontent.com",
        "--allow-host", "github.com",
    ]
    run([str(binary), "resolve", *common])
    run([str(binary), "prepare", *common, "--output", str(workspace)])
    verify_workspace(binary, profile)

    manifest_path = workspace / "registry-manifest.json"
    run([
        str(binary), "manifest", "replay",
        "--input", str(manifest_path),
        "--output", str(replay),
        "--allow-host", "github.com",
    ])
    replay_manifest = replay / "registry-manifest.json"
    run([str(binary), "manifest", "verify", "--input", str(replay_manifest)])
    original = manifest_path.read_bytes()
    replayed = replay_manifest.read_bytes()
    if original != replayed:
        raise RuntimeError("Registry replay produced a different Resolved Manifest")

    # The build consumes only Registry-collected source units. The stable .deps/src
    # paths are a private build staging area, not a second dependency resolver.
    source_root = ROOT / ".deps" / "src"
    source_root.mkdir(parents=True, exist_ok=True)
    for component in json.loads(original.decode("utf-8"))["components"]:
        component_id = component["component_id"]
        if component_id not in {"kernel", "runtime", "backend", "frontend"}:
            continue
        if component_id == "frontend" and component["variant"] != profile:
            continue
        if len(component["source_units"]) != 1:
            raise RuntimeError(
                f"CDIN build adapter expects one source unit for {component_id}; "
                "update the adapter explicitly for multi-source releases"
            )
        source = workspace / component["source_units"][0]["workspace_path"]
        destination = source_root / component_id
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
    print(f"Registry workspace ready: {workspace}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("tui", "gui-sdl"),
                        default=os.environ.get("CDIN_FRONTEND_VARIANT", "tui"))
    parser.add_argument("--verify-workspace", action="store_true",
                        help="verify an already prepared workspace without resolving again")
    args = parser.parse_args()
    profile = profile_name(args.profile)
    binary = build_registry()
    if args.verify_workspace:
        verify_workspace(binary, profile)
    else:
        prepare(profile, binary)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError, KeyError, ValueError) as error:
        print(f"registry: {error}", file=sys.stderr)
        raise SystemExit(1)
