#!/usr/bin/env python3
"""Create a verified, explicitly source-only CDIN pre-release manifest."""
from __future__ import annotations

from hashlib import sha256
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import re

ROOT = Path(__file__).resolve().parents[1]
FULL_REVISION = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})")
DIST = ROOT / "dist"
ARCHIVE = DIST / "cdin-composition-root-source.zip"
CHECKSUM = DIST / "cdin-composition-root-source.zip.sha256"


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def main() -> int:
    profile = os.environ.get("CDIN_FRONTEND_VARIANT", "tui")
    if profile not in {"tui", "gui-sdl"}:
        raise SystemExit(f"unsupported Frontend profile: {profile}")

    if not ARCHIVE.is_file() or not CHECKSUM.is_file():
        raise SystemExit("source archive/checksum missing; run the Pipeline package task first")

    expected = CHECKSUM.read_text(encoding="ascii").split()[0]
    actual = digest(ARCHIVE)
    if expected != actual:
        raise SystemExit(f"source archive checksum mismatch: expected {expected}, got {actual}")

    manifest_path = ROOT / ".deps" / f"registry-workspace-{profile}" / "registry-manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"Registry Resolved Manifest missing: {manifest_path}")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    components = manifest.get("components")
    if not isinstance(components, list):
        raise SystemExit("Registry Resolved Manifest has no components array")

    required_components = {"runtime", "backend", "frontend"}
    selected_components = {item.get("component_id") for item in components}
    if selected_components != required_components:
        raise SystemExit(
            f"Resolved Manifest components are {sorted(selected_components)}, "
            f"expected {sorted(required_components)}; Kernel/logger are environment providers, "
            "not separately resolved component packages"
        )

    expected_environment = {
        ("org.cdin.kernel-abi", "1.1.0"),
        ("org.m-mdy-m.log-c-api", "0.1.0"),
        ("org.lua.puc-lua-c-api", "5.4.0"),
    }
    environment_contracts = manifest.get("environment_contracts")
    if not isinstance(environment_contracts, list):
        raise SystemExit("Resolved Manifest has no environment contract records")
    actual_environment = {
        (item.get("contract_id"), item.get("version"))
        for item in environment_contracts
        if isinstance(item, dict)
    }
    if not expected_environment.issubset(actual_environment):
        missing = sorted(expected_environment - actual_environment)
        raise SystemExit(f"Resolved Manifest is missing pinned environment contracts: {missing}")

    frontend_variants = {
        item.get("variant") for item in components
        if item.get("component_id") == "frontend"
    }
    expected_variants = {"tui"} if profile == "tui" else {"tui", "gui-sdl"}
    if frontend_variants != expected_variants:
        raise SystemExit(
            f"Resolved Manifest Frontend variants are {sorted(frontend_variants)}, "
            f"expected {sorted(expected_variants)}"
        )

    package_records = []
    for item in sorted(components, key=lambda value: (value["component_id"], value.get("variant", ""))):
        delivery = item.get("delivery", "source")
        if delivery == "artifact":
            artifact = item.get("selected_artifact")
            if not isinstance(artifact, dict):
                raise SystemExit(f"artifact descriptor is missing for {item['component_id']}")
            provenance = artifact.get("source_provenance", [])
        elif delivery == "source":
            artifact = None
            provenance = item.get("source_units", [])
        else:
            raise SystemExit(f"unsupported delivery mode for {item['component_id']}: {delivery!r}")

        revisions = []
        for source in provenance:
            revision = source.get("revision") if isinstance(source, dict) else None
            if not isinstance(revision, str) or not FULL_REVISION.fullmatch(revision):
                raise SystemExit(f"invalid immutable source revision in {item['component_id']}")
            revisions.append(revision)
        if not revisions:
            raise SystemExit(f"component {item['component_id']} has no immutable source provenance")

        record = {
            "component_id": item["component_id"],
            "variant": item.get("variant", "default"),
            "version": item["version"],
            "delivery": delivery,
            "source_revisions": revisions,
        }
        if item.get("release_metadata_uri") is not None:
            record["release_metadata_uri"] = item["release_metadata_uri"]
        if item.get("release_metadata_sha256") is not None:
            record["release_metadata_sha256"] = item["release_metadata_sha256"]
        if item.get("release_discovery") is not None:
            record["release_discovery"] = item["release_discovery"]
        if artifact is not None:
            record["selected_artifact"] = artifact
        package_records.append(record)

    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    tag_name = os.environ.get("GITHUB_REF_NAME", "")
    tag_version = tag_name[1:] if tag_name.startswith("v") else ""
    version = os.environ.get(
        "CDIN_PRERELEASE_VERSION", tag_version or f"0.0.0-dev.{commit[:12]}"
    )
    report = {
        "schema_version": "1.0.0",
        "product": "com.cdin.editor",
        "channel": "pre-release",
        "version": version,
        "source_commit": commit,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "profile": profile,
        "verification": {
            "pipeline_task": "pre-release",
            "required_pipeline_dependencies": ["check", "package"],
            "registry_manifest_sha256": sha256(manifest_bytes).hexdigest(),
            "source_archive_sha256": actual,
        },
        "registry_version": manifest.get("registry_version"),
        "catalogs": manifest.get("catalogs", []),
        "roots": manifest.get("roots", []),
        "resolution_order": manifest.get("resolution_order", []),
        "resolution": manifest.get("resolution"),
        "environment_contracts": sorted(
            ({"contract_id": item["contract_id"], "version": item["version"]}
             for item in environment_contracts),
            key=lambda item: (item["contract_id"], item["version"]),
        ),
        "components": package_records,
        "artifacts": [{
            "file": ARCHIVE.name,
            "kind": "source-snapshot",
            "sha256": actual,
            "installable_application": False,
        }],
        "release_note": (
            "This is a verified source pre-release snapshot, not a runnable "
            "CDIN application installer or signed desktop package."
        ),
    }
    output = DIST / "cdin-pre-release.json"
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)
    print(f"Pre-release report: {output}")
    print(f"Source archive SHA-256: {actual}")
    print(f"Resolved components: {len(package_records)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as error:
        print(f"pre-release: {error}", file=sys.stderr)
        raise SystemExit(1)
