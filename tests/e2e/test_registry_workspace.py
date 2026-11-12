#!/usr/bin/env python3
"""Product-level assertions for the Registry artifact/source workspace."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath


FULL_REVISION = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
SEMVER = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
)
FRONTEND_PACKAGE_FILES = {
    "core": (
        "include/cdin/frontend/core/version.h",
        "lib/libcdin_frontend_core.a",
        "lib/cmake/cdinFrontendCore/cdinFrontendCoreConfig.cmake",
        "lib/cmake/cdinFrontendCore/cdinFrontendCoreConfigVersion.cmake",
        "lib/cmake/cdinFrontendCore/cdinFrontendCoreTargets.cmake",
        "lib/pkgconfig/cdin-frontend-core.pc",
    ),
    "tui": (
        "include/cdin/frontend/ui/tui/tui.h",
        "lib/libcdin_frontend_ui_tui.a",
        "lib/cmake/cdinFrontendTUI/cdinFrontendTUIConfig.cmake",
        "lib/cmake/cdinFrontendTUI/cdinFrontendTUIConfigVersion.cmake",
        "lib/cmake/cdinFrontendTUI/cdinFrontendTUITargets.cmake",
        "lib/pkgconfig/cdin-frontend-tui.pc",
    ),
    "gui-sdl": (
        "include/cdin/frontend/ui/gui_sdl/gui_sdl.h",
        "lib/libcdin_frontend_ui_gui_sdl.a",
        "lib/cmake/cdinFrontendGUISDL/cdinFrontendGUISDLConfig.cmake",
        "lib/cmake/cdinFrontendGUISDL/cdinFrontendGUISDLConfigVersion.cmake",
        "lib/cmake/cdinFrontendGUISDL/cdinFrontendGUISDLTargets.cmake",
        "lib/pkgconfig/cdin-frontend-gui-sdl.pc",
    ),
}


def fail(message: str) -> None:
    raise SystemExit(message)


def source_revision(component: dict, key: tuple[str, str]) -> str:
    artifact = component.get("selected_artifact", {})
    provenance = artifact.get("source_provenance", [])
    if component.get("delivery") == "source":
        provenance = component.get("source_units", [])
    if len(provenance) != 1:
        fail(f"source provenance is incomplete for {key}")
    revision = provenance[0].get("revision", "")
    if not FULL_REVISION.fullmatch(revision):
        fail(f"source provenance is not an immutable revision for {key}")
    return revision


def verify_runtime_package(workspace: Path, component: dict) -> None:
    artifact = component.get("selected_artifact")
    if not isinstance(artifact, dict):
        fail("Runtime selected artifact descriptor is missing")
    if artifact.get("kind") != "runtime-module-archive":
        fail("Runtime artifact is not a platform-neutral Lua module archive")
    if artifact.get("layout") != "lua-module-tree-v1":
        fail("Runtime artifact does not declare lua-module-tree-v1")
    if artifact.get("target") != {"os": "any", "architecture": "any", "abi": "none"}:
        fail("Runtime module archive target must be any/any/none")
    if artifact.get("workspace_path") != "components/runtime/default/package":
        fail("Runtime package workspace path is not canonical")

    package = workspace / artifact["workspace_path"]
    root = package / f"cdin-runtime-{component['version']}"
    manifest_path = root / "package-manifest.json"
    module_entry = root / "lua" / "cdin" / "runtime.lua"
    for path in (package, root, manifest_path, module_entry):
        if path.is_symlink():
            fail(f"Runtime package contains a symlink: {path}")
    if not package.is_dir() or not root.is_dir():
        fail(f"Runtime archive root is missing: {root}")
    if not manifest_path.is_file() or not module_entry.is_file():
        fail("Runtime archive is missing its package manifest or Lua entry module")

    try:
        package_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"Runtime package manifest is invalid: {error}")
    if (
        package_manifest.get("component_id") != "runtime"
        or package_manifest.get("variant") != "default"
        or package_manifest.get("version") != component["version"]
        or package_manifest.get("layout") != "lua-module-tree-v1"
        or package_manifest.get("module_root") != "lua"
        or package_manifest.get("runtime_requirement") != "PUC Lua >=5.4 <5.5"
    ):
        fail("Runtime package manifest identity/layout does not match the Resolved Manifest")

    revision = source_revision(component, ("runtime", "default"))
    if package_manifest.get("source_revision") != revision:
        fail("Runtime package source revision differs from Registry artifact provenance")

    records = package_manifest.get("files")
    if not isinstance(records, list) or not records:
        fail("Runtime package manifest has no file integrity records")
    seen: set[str] = set()
    for record in records:
        relative_name = record.get("path", "")
        relative = PurePosixPath(relative_name)
        if (
            not relative_name
            or relative.is_absolute()
            or "\\" in relative_name
            or ":" in relative_name
            or any(part in ("", ".", "..") for part in relative.parts)
            or relative_name in seen
        ):
            fail(f"Runtime package manifest contains an unsafe/duplicate path: {relative_name!r}")
        seen.add(relative_name)
        path = root.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file():
            fail(f"Runtime package file is missing or not regular: {relative_name}")
        data = path.read_bytes()
        if len(data) != record.get("size_bytes") or hashlib.sha256(data).hexdigest() != record.get("sha256"):
            fail(f"Runtime package file digest/size mismatch: {relative_name}")


def verify_frontend_artifact(
    workspace: Path,
    target: dict,
    key: tuple[str, str],
    component: dict,
) -> str:
    variant = key[1]
    artifact = component.get("selected_artifact")
    if not isinstance(artifact, dict):
        fail(f"Frontend {variant} artifact descriptor is missing")
    if artifact.get("kind") != "native-development-package":
        fail(f"Frontend {variant} artifact has the wrong package kind")
    if artifact.get("layout") != "cmake-prefix-v1":
        fail(f"Frontend {variant} artifact has the wrong package layout")
    if artifact.get("target") != target:
        fail(f"Frontend {variant} target differs from the Resolved Manifest")
    expected_path = f"components/frontend/{variant}/package"
    if artifact.get("workspace_path") != expected_path:
        fail(f"Frontend {variant} package workspace path is not canonical")
    package = workspace / expected_path
    if package.is_symlink() or not package.is_dir():
        fail(f"Frontend {variant} package directory is missing or unsafe")
    for relative in FRONTEND_PACKAGE_FILES[variant]:
        candidate = package / relative
        if candidate.is_symlink() or not candidate.is_file():
            fail(f"Frontend {variant} package is missing {relative}")

    revision = source_revision(component, key)
    build_info = package / "share" / "cdin-frontend" / "BUILD-INFO.txt"
    try:
        values = {}
        for line in build_info.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                name, value = line.split("=", 1)
                values[name] = value
    except (OSError, UnicodeError) as error:
        fail(f"Frontend {variant} BUILD-INFO is unreadable: {error}")
    expected_values = {
        "component": "frontend",
        "variant": variant,
        "package_version": component["version"],
        "source_revision": revision,
        "target_os": target["os"],
        "target_architecture": target["architecture"],
        "target_abi": target["abi"],
    }
    if any(values.get(name) != value for name, value in expected_values.items()):
        fail(f"Frontend {variant} BUILD-INFO does not match its Manifest identity")
    return revision


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--profile", choices=("tui", "gui-sdl"), required=True)
    parser.add_argument(
        "--developer-source-components",
        action="store_true",
        help="allow source-delivered Runtime/Frontend in the explicit developer workflow",
    )
    args = parser.parse_args()

    manifest_path = args.workspace / "registry-manifest.json"
    if not manifest_path.is_file():
        fail(f"missing Registry manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    component_list = manifest.get("components")
    if not isinstance(component_list, list):
        fail("Resolved Manifest components must be an array")
    components = {
        (item["component_id"], item["variant"]): item
        for item in component_list
    }
    if len(components) != len(component_list):
        fail("Resolved Manifest contains duplicate component/variant identities")

    resolution = manifest.get("resolution")
    if not isinstance(resolution, dict):
        fail("Resolved Manifest is missing the immutable delivery policy")
    expected_delivery_mode = (
        "artifact-or-source" if args.developer_source_components else "artifact"
    )
    if resolution.get("delivery_mode") != expected_delivery_mode:
        fail(
            f"Resolved Manifest delivery mode is {resolution.get('delivery_mode')!r}; "
            f"expected {expected_delivery_mode!r}"
        )
    target = resolution.get("target")
    if not isinstance(target, dict) or set(target) != {"os", "architecture", "abi"}:
        fail("Resolved Manifest target tuple is missing or malformed")

    expected = {
        ("runtime", "default"),
        ("backend", "default"),
        ("frontend", "tui"),
    }
    if args.profile == "gui-sdl":
        expected.add(("frontend", "gui-sdl"))
    if not args.developer_source_components:
        expected.add(("frontend", "core"))
    if set(components) != expected:
        fail(
            f"resolved component graph mismatch: {sorted(components)} != {sorted(expected)}"
        )

    for key, component in components.items():
        if not SEMVER.fullmatch(component.get("version", "")):
            fail(f"invalid resolved SemVer for {key}: {component.get('version')!r}")

        delivery = component.get("delivery", "source")
        if key == ("backend", "default"):
            if component["version"] != "1.2.1" or delivery != "artifact":
                fail("Backend 1.2.1 must be delivered as a native Registry artifact")
            artifact = component.get("selected_artifact")
            if not isinstance(artifact, dict):
                fail("Backend's selected artifact descriptor is missing")
            if artifact.get("kind") != "native-development-package":
                fail("Backend selected artifact has the wrong package kind")
            if artifact.get("layout") != "cmake-prefix-v1":
                fail("Backend selected artifact has the wrong package layout")
            if artifact.get("target") != target:
                fail("Backend artifact target differs from the Manifest target")
            if not artifact.get("artifact_id"):
                fail("Backend artifact identity is empty")
            if artifact.get("workspace_path") != "components/backend/default/package":
                fail("Backend package workspace path is not canonical")
            package = args.workspace / artifact["workspace_path"]
            for required in (
                "include/cdin/backend.h",
                "lib/libcdin_backend.a",
                "lib/libcdin_backend_services.a",
                "lib/libcdin_protocol.a",
                "lib/cmake/cdinBackend/cdinBackendConfig.cmake",
                "lib/pkgconfig/cdin-backend.pc",
                "lib/pkgconfig/cdin-backend-services.pc",
                "lib/pkgconfig/cdin-protocol.pc",
            ):
                candidate = package / required
                if candidate.is_symlink() or not candidate.is_file():
                    fail(f"Backend Registry package is missing {required}")
            provenance = artifact.get("source_provenance", [])
            if len(provenance) != 1 or not FULL_REVISION.fullmatch(provenance[0].get("revision", "")):
                fail("Backend artifact source provenance is not an immutable Git revision")
            if provenance[0].get("source_unit_id") != "backend-source":
                fail("Backend artifact provenance references the wrong source unit")
            continue

        if delivery == "source":
            if not args.developer_source_components:
                fail(
                    f"normal product mode cannot use source-delivered {key}; "
                    "publish and pin its immutable artifact before enabling this path"
                )
            units = component.get("source_units", [])
            if len(units) != 1:
                fail(f"expected one source unit for {key}, found {len(units)}")
            for unit in units:
                if not FULL_REVISION.fullmatch(unit.get("revision", "")):
                    fail(f"non-immutable source revision for {key}: {unit.get('revision')}")
                source = args.workspace / unit["workspace_path"]
                if not source.is_dir():
                    fail(f"missing materialized source unit for {key}: {source}")
            continue

        if delivery != "artifact":
            fail(f"unexpected artifact delivery for {key}: {delivery}")
        artifact = component.get("selected_artifact")
        if not isinstance(artifact, dict):
            fail(f"selected artifact descriptor is missing for {key}")
        expected_path = f"components/{key[0]}/{key[1]}/package"
        if artifact.get("workspace_path") != expected_path:
            fail(f"artifact workspace path is not canonical for {key}")
        package = args.workspace / expected_path
        if package.is_symlink() or not package.is_dir():
            fail(f"materialized package is missing or unsafe for {key}")
        if artifact.get("kind") == "native-development-package" and artifact.get("target") != target:
            fail(f"native artifact target differs from the Manifest target for {key}")

    runtime = components[("runtime", "default")]
    if runtime.get("delivery") == "artifact":
        verify_runtime_package(args.workspace, runtime)
    elif not args.developer_source_components:
        fail("Runtime source delivery is permitted only in explicit developer mode")

    frontend_revisions: set[str] = set()
    for key, component in components.items():
        if key[0] != "frontend":
            continue
        if component.get("delivery", "source") == "artifact":
            revision = verify_frontend_artifact(args.workspace, target, key, component)
        else:
            revision = source_revision(component, key)
        frontend_revisions.add(revision)
    if len(frontend_revisions) != 1:
        fail("Frontend Core/TUI/GUI-SDL variants must resolve to the same immutable source revision")

    def has_contract(component: dict, direction: str, contract_id: str,
                     version: str | None = None) -> bool:
        declarations = component.get("contracts", {}).get(direction, [])
        return any(
            item["contract_id"] == contract_id
            and (version is None or item.get("version") == version)
            for item in declarations
        )

    runtime = components[("runtime", "default")]
    backend = components[("backend", "default")]
    environment_contracts = {
        (item["contract_id"], item["version"])
        for item in manifest.get("environment_contracts", [])
    }
    expected_environment = {
        ("org.cdin.kernel-abi", "1.1.0"),
        ("org.m-mdy-m.log-c-api", "0.1.0"),
        ("org.lua.puc-lua-c-api", "5.4.0"),
    }
    if not expected_environment.issubset(environment_contracts):
        fail("Kernel/logger/Lua environment providers are not recorded in the Manifest")
    backend_requirements = backend.get("contracts", {}).get("requires", [])
    for contract_id in (
        "org.cdin.kernel-abi",
        "org.m-mdy-m.log-c-api",
        "org.lua.puc-lua-c-api",
    ):
        if not any(item["contract_id"] == contract_id for item in backend_requirements):
            fail(f"Backend {contract_id} environment requirement is missing")
    if not has_contract(backend, "provides", "org.cdin.runtime-host-api", "1.0.0"):
        fail("Backend Runtime Host API provider contract is missing")
    if not has_contract(runtime, "requires", "org.cdin.runtime-host-api"):
        fail("Runtime Host API requirement is missing")
    if not has_contract(backend, "provides", "org.cdin.frontend-protocol", "1.0.0"):
        fail("Backend Frontend Protocol provider contract is missing")
    for key, component in components.items():
        if key[0] == "frontend" and key[1] != "core" and not has_contract(
            component, "requires", "org.cdin.frontend-protocol"
        ):
            fail(f"Frontend {key[1]} Protocol requirement is missing")

    if not args.developer_source_components:
        for variant in ("tui", "gui-sdl"):
            key = ("frontend", variant)
            if key not in components:
                continue
            dependencies = {
                (item.get("component_id"), item.get("variant"), item.get("version"))
                for item in components[key].get("dependencies", [])
            }
            core_version = components[("frontend", "core")]["version"]
            if ("frontend", "core", core_version) not in dependencies:
                fail(f"Frontend {variant} does not depend on the selected Core package")
            if core_version != components[key]["version"]:
                fail(f"Frontend {variant} and Core package versions are not synchronized")

    dependencies = {
        (item["component_id"], item["variant"], item["version"])
        for item in backend["dependencies"]
    }
    if any(item[0] == "kernel" for item in dependencies):
        fail("Kernel must be supplied by the CDIN environment, not Registry dependency closure")
    if not any(item[0] == "runtime" for item in dependencies):
        fail("Backend release did not resolve its Runtime dependency")

    delivery_summary = (
        "immutable Runtime and Frontend package artifacts"
        if not args.developer_source_components
        else "source-delivered Runtime/Frontend developer inputs"
    )
    print(
        "Registry product E2E passed: Backend 1.2.1 artifact + pinned Kernel/logger SDK + "
        f"{delivery_summary}, frontend={args.profile}, target={target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
