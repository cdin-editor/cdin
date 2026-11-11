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

try:
    from .registry_artifact import acquire_registry_artifact
except ImportError:  # Direct execution: scripts/ is sys.path[0].
    from registry_artifact import acquire_registry_artifact

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "deps.lock"
REGISTRY_SOURCE = ROOT / ".deps" / "tools" / "registry"
REGISTRY_CATALOG = REGISTRY_SOURCE / "catalogs" / "cdin-components" / "catalog-index.json"
REGISTRY_BUILD = ROOT / "build" / "tools"
WORKSPACE_ROOT = ROOT / ".deps"
REGISTRY_CACHE = WORKSPACE_ROOT / "cache" / "registry"


def run(
    command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None
) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def registry_go_environment() -> dict[str, str]:
    """Use the canonical Go proxy by default, with an explicit local override.

    The Registry module pins its Go toolchain in go.mod. Go downloads that
    toolchain through GOPROXY, so inheriting an unreliable third-party proxy
    can make an otherwise valid Registry build fail before tests start.
    """
    environment = os.environ.copy()
    environment["GOPROXY"] = os.environ.get(
        "CDIN_GOPROXY", "https://proxy.golang.org,direct"
    )
    environment.setdefault("GOTOOLCHAIN", "auto")
    return environment


def run_registry_go(command: list[str]) -> None:
    try:
        run(command, cwd=REGISTRY_SOURCE, env=registry_go_environment())
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            "Registry Go command failed. The pinned Go toolchain is selected "
            "from go.mod; check network access to proxy.golang.org or set "
            "CDIN_GOPROXY to a reachable Go module proxy."
        ) from error


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


def build_registry(
    *,
    run_tests: bool = True,
    source_build: bool = False,
    offline: bool = False,
) -> Path:
    global REGISTRY_CATALOG
    if not source_build:
        pin = load_lock()["tooling"]["registry"]
        binary, catalog = acquire_registry_artifact(
            pin,
            cache_root=REGISTRY_CACHE,
            offline=offline,
        )
        REGISTRY_CATALOG = catalog
        print(f"Verified Registry executable: {binary}", flush=True)
        print(f"Verified Registry Catalog: {catalog}", flush=True)
        return binary

    if shutil.which("git") is None or shutil.which("go") is None:
        raise RuntimeError(
            "Registry source builds are developer-only and require Git and Go 1.27.3 or newer"
        )
    _, revision = registry_pin()
    if run_tests or not REGISTRY_SOURCE.exists():
        checkout_registry()
    else:
        actual = subprocess.check_output(
            ["git", "-C", str(REGISTRY_SOURCE), "rev-parse", "HEAD"], text=True
        ).strip()
        if actual != revision:
            checkout_registry()
    if run_tests:
        run_registry_go(["go", "test", "./..."])
    REGISTRY_BUILD.mkdir(parents=True, exist_ok=True)
    binary = REGISTRY_BUILD / ("registry.exe" if os.name == "nt" else "registry")
    stamp = REGISTRY_BUILD / "registry-source.sha"
    if (
        run_tests
        or not binary.is_file()
        or not stamp.is_file()
        or stamp.read_text(encoding="utf-8").strip() != revision
    ):
        run_registry_go(["go", "build", "-trimpath", "-o", str(binary), "./cmd/registry"])
        stamp.write_text(revision + "\n", encoding="utf-8")
    return binary


def paths(profile: str) -> tuple[Path, Path, Path]:
    product = ROOT / "registry" / f"product-definition.{profile}.yaml"
    workspace = WORKSPACE_ROOT / f"registry-workspace-{profile}"
    replay = WORKSPACE_ROOT / f"registry-replay-{profile}"
    return product, workspace, replay


def verify_workspace(binary: Path, profile: str) -> None:
    _, workspace, _ = paths(profile)
    manifest_path = workspace / "registry-manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"Registry workspace is missing: {manifest_path}")
    run([str(binary), "manifest", "verify", "--input", str(manifest_path)])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {"kernel", "runtime", "backend", "frontend"}
    selected = {item["component_id"] for item in manifest["components"]}
    if selected != required:
        raise RuntimeError(f"Registry selected {sorted(selected)}, expected {sorted(required)}")
    frontend_variants = {
        item["variant"] for item in manifest["components"]
        if item["component_id"] == "frontend"
    }
    expected_variants = {"tui"} if profile == "tui" else {"tui", "gui-sdl"}
    if frontend_variants != expected_variants:
        raise RuntimeError(
            f"Registry selected Frontend variants {sorted(frontend_variants)}, "
            f"expected {sorted(expected_variants)}"
        )
    for component in manifest["components"]:
        for source in component["source_units"]:
            materialized = workspace / source["workspace_path"]
            if not materialized.is_dir():
                raise RuntimeError(f"Registry source unit is missing: {materialized}")


def prepare(profile: str, binary: Path) -> None:
    product, workspace, replay = paths(profile)
    catalog = REGISTRY_CATALOG
    if not catalog.is_file():
        raise RuntimeError(f"pinned Registry Catalog Index is missing: {catalog}")
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
        source_unit = component["source_units"][0]
        source = workspace / source_unit["workspace_path"]
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
    parser.add_argument("--source-build", action="store_true",
                        help="developer-only: clone, test and compile Registry from its pinned source")
    parser.add_argument("--offline", action="store_true",
                        help="reuse only a previously verified Registry executable/Catalog cache")
    args = parser.parse_args()
    profile = profile_name(args.profile)
    binary = build_registry(
        run_tests=not args.verify_workspace,
        source_build=args.source_build,
        offline=args.offline or os.environ.get("CDIN_OFFLINE", "").lower() in {"1", "true", "yes"},
    )
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
