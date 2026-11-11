#!/usr/bin/env python3
"""Product-level assertions for the Registry artifact/source workspace."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


FULL_REVISION = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")


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
        ("frontend", "tui"),
    }
    if args.profile == "gui-sdl":
        expected.add(("frontend", "gui-sdl"))
    if set(components) != expected:
        raise SystemExit(
            f"resolved component graph mismatch: {sorted(components)} != {sorted(expected)}"
        )

    resolution = manifest.get("resolution")
    if not isinstance(resolution, dict):
        raise SystemExit("Resolved Manifest is missing the immutable delivery policy")
    if resolution.get("delivery_mode") != "artifact-or-source":
        raise SystemExit("Resolved Manifest did not record artifact-or-source delivery")
    target = resolution.get("target")
    if not isinstance(target, dict) or set(target) != {"os", "architecture", "abi"}:
        raise SystemExit("Resolved Manifest target tuple is missing or malformed")

    for key, component in components.items():
        if not re.fullmatch(
            r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
            r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?",
            component["version"],
        ):
            raise SystemExit(f"invalid resolved SemVer for {key}: {component['version']}")

        delivery = component.get("delivery", "source")
        if key == ("backend", "default"):
            if component["version"] != "1.2.1" or delivery != "artifact":
                raise SystemExit("Backend 1.2.1 must be delivered as a native Registry artifact")
            artifact = component.get("selected_artifact")
            if not isinstance(artifact, dict):
                raise SystemExit("Backend's selected artifact descriptor is missing")
            if artifact.get("kind") != "native-development-package":
                raise SystemExit("Backend selected artifact has the wrong package kind")
            if artifact.get("layout") != "cmake-prefix-v1":
                raise SystemExit("Backend selected artifact has the wrong package layout")
            if artifact.get("target") != target:
                raise SystemExit("Backend artifact target differs from the Manifest target")
            if artifact.get("artifact_id") == "":
                raise SystemExit("Backend artifact identity is empty")
            if artifact.get("workspace_path") != "components/backend/default/package":
                raise SystemExit("Backend package workspace path is not canonical")
            package = args.workspace / artifact["workspace_path"]
            for required in (
                "include/cdin/backend.h",
                "lib/libcdin_backend.a",
                "lib/libcdin_backend_services.a",
                "lib/libcdin_protocol.a",
                "lib/cmake/cdinBackend/cdinBackendConfig.cmake",
                "lib/pkgconfig/cdin-backend.pc",
            ):
                candidate = package / required
                if candidate.is_symlink() or not candidate.is_file():
                    raise SystemExit(f"Backend Registry package is missing {required}")
            provenance = artifact.get("source_provenance", [])
            if len(provenance) != 1 or not FULL_REVISION.fullmatch(provenance[0].get("revision", "")):
                raise SystemExit("Backend artifact source provenance is not an immutable Git revision")
            if provenance[0].get("source_unit_id") != "backend-source":
                raise SystemExit("Backend artifact provenance references the wrong source unit")
            continue

        if delivery != "source":
            raise SystemExit(f"unexpected artifact delivery for {key}: {delivery}")
        units = component.get("source_units", [])
        if len(units) != 1:
            raise SystemExit(f"expected one source unit for {key}, found {len(units)}")
        for unit in units:
            if not FULL_REVISION.fullmatch(unit["revision"]):
                raise SystemExit(f"non-immutable source revision for {key}: {unit['revision']}")
            source = args.workspace / unit["workspace_path"]
            if not source.is_dir():
                raise SystemExit(f"missing materialized source unit for {key}: {source}")

    frontend_revisions = {
        unit["revision"]
        for key, component in components.items()
        if key[0] == "frontend"
        for unit in component["source_units"]
    }
    if len(frontend_revisions) != 1:
        raise SystemExit("TUI and GUI-SDL variants must resolve to the same Frontend source revision")

    def has_contract(component: dict, direction: str, contract_id: str,
                     version: str | None = None) -> bool:
        declarations = component.get("contracts", {}).get(direction, [])
        return any(
            item["contract_id"] == contract_id
            and (version is None or item.get("version") == version)
            for item in declarations
        )

    kernel = components[("kernel", "default")]
    runtime = components[("runtime", "default")]
    backend = components[("backend", "default")]
    if not has_contract(kernel, "provides", "org.cdin.kernel-abi", "1.1.0"):
        raise SystemExit("Kernel ABI provider contract was not resolved")
    if not has_contract(backend, "requires", "org.cdin.kernel-abi"):
        raise SystemExit("Backend Kernel ABI requirement is missing")
    if not has_contract(backend, "provides", "org.cdin.runtime-host-api", "1.0.0"):
        raise SystemExit("Backend Runtime Host API provider contract is missing")
    if not has_contract(runtime, "requires", "org.cdin.runtime-host-api"):
        raise SystemExit("Runtime Host API requirement is missing")
    if not has_contract(backend, "provides", "org.cdin.frontend-protocol", "1.0.0"):
        raise SystemExit("Backend Frontend Protocol provider contract is missing")
    for key, component in components.items():
        if key[0] == "frontend" and not has_contract(
            component, "requires", "org.cdin.frontend-protocol"
        ):
            raise SystemExit(f"Frontend {key[1]} Protocol requirement is missing")

    dependencies = {
        (item["component_id"], item["variant"], item["version"])
        for item in backend["dependencies"]
    }
    if not any(item[0] == "kernel" for item in dependencies):
        raise SystemExit("Backend release did not resolve its Kernel dependency")
    if not any(item[0] == "runtime" for item in dependencies):
        raise SystemExit("Backend release did not resolve its Runtime dependency")

    print(
        "Registry product E2E passed: Backend 1.2.1 artifact + "
        f"source-delivered Kernel/Runtime/Frontend, frontend={args.profile}, target={target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
