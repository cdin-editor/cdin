#!/usr/bin/env python3
"""Resolve, prepare, verify and replay the immutable CDIN component workspace."""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
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


def registry_pin(*, development: bool = False) -> tuple[str, str]:
    entry = load_lock()["tooling"]["registry"]
    if development:
        entry = entry.get("development")
        if not isinstance(entry, dict):
            raise RuntimeError("deps.lock is missing the exact Registry development source pin")
    return entry["repository"], entry["revision"]


def checkout_registry(*, development: bool = False) -> None:
    repository, revision = registry_pin(development=development)
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
    _, revision = registry_pin(development=True)
    if run_tests or not REGISTRY_SOURCE.exists():
        checkout_registry(development=True)
    else:
        actual = subprocess.check_output(
            ["git", "-C", str(REGISTRY_SOURCE), "rev-parse", "HEAD"], text=True
        ).strip()
        if actual != revision:
            checkout_registry(development=True)
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


def detect_target_tuple(
    *,
    system: str | None = None,
    machine: str | None = None,
    libc: tuple[str, str] | None = None,
    mac_version: str | None = None,
    msystem: str | None = None,
) -> dict[str, str]:
    """Return the exact ABI tuple supported by the published CDIN packages."""
    system = system or platform.system()
    machine = (machine or platform.machine()).strip().lower()
    architecture = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "x64": "x86_64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(machine)
    if architecture is None:
        raise RuntimeError(f"unsupported Registry artifact architecture: {machine!r}")

    normalized_system = system.strip().lower()
    if normalized_system == "linux":
        libc = libc or platform.libc_ver()
        libc_name, libc_version = libc
        if libc_name.lower() not in {"glibc", "gnu libc"}:
            raise RuntimeError(
                f"unsupported Linux C runtime {libc_name!r}; CDIN artifacts require glibc >= 2.39"
            )
        match = re.match(r"^(\d+)\.(\d+)", libc_version)
        if not match or tuple(map(int, match.groups())) < (2, 39):
            raise RuntimeError(
                f"Linux glibc {libc_version or 'unknown'} is older than the supported 2.39 baseline"
            )
        return {"os": "linux", "architecture": architecture, "abi": "gnu-glibc-2.39"}

    if normalized_system in {"darwin", "macos"}:
        mac_version = mac_version if mac_version is not None else platform.mac_ver()[0]
        match = re.match(r"^(\d+)(?:\.(\d+))?", mac_version)
        if not match or int(match.group(1)) < 15:
            raise RuntimeError(
                f"macOS {mac_version or 'unknown'} is older than the supported macOS 15 baseline"
            )
        return {"os": "darwin", "architecture": architecture, "abi": "macos-15"}

    if normalized_system in {"windows", "win32"}:
        if architecture != "x86_64":
            raise RuntimeError("CDIN currently publishes only Windows x86_64 UCRT64 packages")
        msystem = msystem if msystem is not None else os.environ.get("MSYSTEM", "")
        if msystem.upper() != "UCRT64":
            raise RuntimeError(
                "Windows package staging requires the MSYS2 UCRT64 environment (MSYSTEM=UCRT64)"
            )
        return {"os": "windows", "architecture": "x86_64", "abi": "windows-ucrt64"}

    raise RuntimeError(f"unsupported Registry artifact operating system: {system!r}")


def create_effective_product_definition(
    source: Path,
    destination: Path,
    target: dict[str, str],
) -> Path:
    """Create a private host-specific Product Definition copy for resolution."""
    content = source.read_text(encoding="utf-8")
    if re.search(r"(?m)^resolution\s*:", content):
        raise RuntimeError(f"checked-in Product Definition already declares resolution: {source}")
    content, substitutions = re.subn(
        r'''(?m)^schema_version:\s*["']?1\.0\.0["']?\s*$''',
        'schema_version: "1.1.0"',
        content,
        count=1,
    )
    if substitutions != 1:
        raise RuntimeError(f"unsupported Product Definition schema version in {source}")
    content = content.rstrip() + (
        "\n\nresolution:\n"
        "  delivery_mode: artifact-or-source\n"
        "  target:\n"
        f"    os: {target['os']}\n"
        f"    architecture: {target['architecture']}\n"
        f"    abi: {target['abi']}\n"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8", newline="\n")
    return destination


def verify_workspace(binary: Path, profile: str, target: dict[str, str]) -> None:
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

    by_key = {
        (item["component_id"], item["variant"]): item
        for item in manifest["components"]
    }
    backend = by_key[("backend", "default")]
    if backend["version"] != "1.2.1" or backend.get("delivery") != "artifact":
        raise RuntimeError(
            "CDIN requires Backend 1.2.1 as a verified Registry artifact; "
            "refusing a silent source fallback"
        )
    selected_artifact = backend.get("selected_artifact")
    if not isinstance(selected_artifact, dict):
        raise RuntimeError("Registry Manifest is missing Backend's selected artifact")
    if selected_artifact.get("kind") != "native-development-package":
        raise RuntimeError("Backend selected artifact is not a native development package")
    if selected_artifact.get("layout") != "cmake-prefix-v1":
        raise RuntimeError("Backend package does not declare the cmake-prefix-v1 layout")
    if selected_artifact.get("target") != target:
        raise RuntimeError(
            f"Backend artifact target {selected_artifact.get('target')} does not match host {target}"
        )
    backend_package = workspace / "components" / "backend" / "default" / "package"
    if selected_artifact.get("workspace_path") != "components/backend/default/package":
        raise RuntimeError("Backend package workspace path is not canonical")
    if not backend_package.is_dir():
        raise RuntimeError(f"Registry Backend package is missing: {backend_package}")

    for key, component in by_key.items():
        if key[0] == "backend":
            continue
        if component.get("delivery", "source") != "source":
            raise RuntimeError(f"unexpected artifact delivery for component {key}")
        units = component.get("source_units", [])
        if len(units) != 1:
            raise RuntimeError(f"CDIN build adapter expects one source unit for {key}")
        for source in units:
            materialized = workspace / source["workspace_path"]
            if not materialized.is_dir():
                raise RuntimeError(f"Registry source unit is missing: {materialized}")


def prepare(profile: str, binary: Path) -> None:
    source_product, workspace, replay = paths(profile)
    catalog = REGISTRY_CATALOG
    if not catalog.is_file():
        raise RuntimeError(f"pinned Registry Catalog Index is missing: {catalog}")
    if workspace.exists() or replay.exists():
        raise RuntimeError(
            f"Registry output already exists for {profile}; remove {workspace} and {replay} "
            "explicitly before preparing again"
        )
    target = detect_target_tuple()
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=f"registry-product-{profile}-",
        dir=WORKSPACE_ROOT,
    ) as temporary:
        product = create_effective_product_definition(
            source_product,
            Path(temporary) / "product-definition.yaml",
            target,
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
        verify_workspace(binary, profile, target)

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

        # Materialize only source-delivered components in the source build area.
        # Backend's verified package remains in the Registry workspace.
        source_root = ROOT / ".deps" / "src"
        source_root.mkdir(parents=True, exist_ok=True)
        for component in json.loads(original.decode("utf-8"))["components"]:
            component_id = component["component_id"]
            if component_id not in {"kernel", "runtime", "backend", "frontend"}:
                continue
            # Kernel is provided by the separately pinned 1.2.1 + logger 0.1.0
            # SDK asset in deps.lock; keep its Registry metadata in the Manifest
            # but do not create a second source-build checkout.
            if component_id == "kernel":
                stale = source_root / component_id
                if stale.exists():
                    shutil.rmtree(stale)
                continue
            if component_id == "backend" and component.get("delivery") == "artifact":
                stale = source_root / component_id
                if stale.exists():
                    shutil.rmtree(stale)
                continue
            if component_id == "frontend" and component["variant"] != profile:
                continue
            units = component.get("source_units", [])
            if len(units) != 1:
                raise RuntimeError(
                    f"CDIN build adapter expects one source unit for {component_id}; "
                    "update the adapter explicitly for multi-source releases"
                )
            source_unit = units[0]
            source = workspace / source_unit["workspace_path"]
            destination = source_root / component_id
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source, destination)
    resolved_components = json.loads(original.decode("utf-8"))["components"]
    backend_versions = [
        item["version"] for item in resolved_components
        if item["component_id"] == "backend" and item["variant"] == "default"
    ]
    if len(backend_versions) != 1:
        raise RuntimeError("Resolved Manifest does not contain exactly one Backend version")
    print(
        f"Registry workspace ready: {workspace} "
        f"(delivery=artifact-or-source, backend={backend_versions[0]}, target={target})",
        flush=True,
    )


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
        verify_workspace(binary, profile, detect_target_tuple())
    else:
        prepare(profile, binary)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError, KeyError, ValueError) as error:
        print(f"registry: {error}", file=sys.stderr)
        raise SystemExit(1)
