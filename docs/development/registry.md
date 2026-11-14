# Registry integration

CDIN uses Registry as an independent build-time dependency resolver and artifact/source workspace preparer. Registry is not linked into the editor executable and is never a component runtime dependency.

The normative boundary is defined by the [Spec Registry contracts](https://github.com/cdin-editor/spec/blob/main/docs/architecture/registry-contracts.md), [ADR-0025 — Immutable Target Artifact Delivery](https://github.com/cdin-editor/spec/blob/main/docs/adr/ADR-0025-immutable-target-artifact-delivery.md), [ADR-0028 — GitHub Release Metadata Discovery](https://github.com/cdin-editor/spec/blob/main/docs/adr/ADR-0028-github-release-metadata-discovery.md), and the [module ownership boundaries](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md).

## Current artifact-first and API-authentication status — 2026-11-15

Use the [dependency and delivery matrix](dependency-matrix.md) for the exact candidate versions, immutable source identities, metadata assets, target packages and acceptance state. This section supersedes the older dated implementation notes below wherever they describe previous package pins or a Registry executable that had not yet been published.

- Kernel/logger SDK 1.2.3, Runtime 1.0.0, Backend 1.2.2, Frontend Core/TUI/GUI-SDL 1.2.2 and SDL3 SDK 3.4.16 have published immutable package identities. Their publication does not by itself complete CDIN product acceptance.
- Registry stable `v1.0.0` is published with five executables, a same-tag Catalog and descriptor. It is not accepted by a clean consumer: Manifest schema 1.2.0 is required when ADR-0028 discovery provenance is present, while the immutable v1.0.0 executable serializes schema 1.1.0. Registry PR #75 fixes that regression; PR #77 adds authenticated Release discovery. Both are merged on Registry main, but the corrected immutable `v1.0.1` Release has not yet been published.
- CDIN PR #149 is the active artifact-first candidate. It is not merged and its ten target/profile Product Acceptance jobs must pass on the exact PR head before #121/#122/#124 can be closed.
- Product integration remains incomplete independently of packaging: live IME/PaneTree E2E, production Unicode shaping and bidirectional text (including Persian/Arabic), real TUI/GUI editing, lifecycle/recovery, performance/soak, security and installed distribution gates remain under CDIN #111/#118.

### Cross-repository GitHub API credential for CI

The CDIN workflows discover immutable Releases from several repositories. The automatic GitHub Actions `GITHUB_TOKEN` is intentionally limited to the repository running the workflow and must not be used as the credential for the Kernel, Runtime, Backend, Frontend or Registry APIs.

Configure an Actions secret named `CDIN_GITHUB_READ_TOKEN` as a fine-grained personal access token or GitHub App installation token with **Contents: read only** for the selected repositories:

- `cdin-editor/cdin`
- `cdin-editor/kernel`
- `cdin-editor/runtime`
- `cdin-editor/backend`
- `cdin-editor/frontend`
- `cdin-editor/registry`

The CI and Product Acceptance workflows expose this secret as `CDIN_GITHUB_API_TOKEN` and `REGISTRY_GITHUB_API_TOKEN`. `GH_TOKEN` remains available for ordinary GitHub CLI operations that act on the CDIN repository and must not be repurposed as the cross-repository read credential. Do not grant write permissions. The value is used only for GitHub API Release/tag discovery, is never printed, and is not embedded in artifacts or distributed with CDIN. The application bootstrap still verifies exact tag commits, API asset digest/size, archive contents and package identities; authentication does not replace those checks.

For a local developer run, set `CDIN_GITHUB_API_TOKEN` and `REGISTRY_GITHUB_API_TOKEN` (or `GH_TOKEN`) to a credential with the same read scope. The SDK bootstrap and Registry client use the dedicated variables first and ignore the automatic Actions `GITHUB_TOKEN` when running in CI. If the optional secret is absent, public API discovery continues anonymously and remains subject to GitHub's lower unauthenticated rate limit. The SDK bootstrap also accepts `CDIN_GITHUB_API_TOKEN`; Registry accepts `REGISTRY_GITHUB_API_TOKEN`. A local-shell `GITHUB_TOKEN` fallback remains available outside GitHub Actions. The Actions-provided repository token is deliberately ignored by these cross-repository readers.

## Ownership

- **Spec** owns the Registry data contracts, schemas, compatibility rules and conformance vectors.
- **Registry** owns generic Catalog validation, SemVer/dependency/contract resolution, GitHub Release discovery, immutable artifact/source acquisition, cache verification and Manifest replay. It must not contain CDIN-specific repository mappings.
- **Each component repository** owns its package artifacts and Component Release Metadata publication.
- **CDIN** owns Product Definitions, the pinned Registry/Catalog inputs, Composition Root orchestration, product integration and product distribution.
- **cdin-x** owns the extension ecosystem. CDIN must not implement a second extension manager.

Registry is not a runtime dependency. No component imports or links Registry.

## Catalog models and ADR-0028

A Catalog Index uses exactly one of the two supported models:

1. Static `entries`, preserving compatibility with existing immutable Catalog snapshots.
2. Dynamic `release_sources`, declaring one source per component/variant/repository. Registry enumerates the complete eligible GitHub Release inventory and resolves the highest compatible SemVer; it does not use the most recently published release or the first API result.

A single Catalog document must not mix `entries` and `release_sources`. Existing static Catalogs remain valid during migration. CDIN must not switch Product Definitions to dynamic discovery until the pinned Registry executable implements Data Contract 1.4.0 and all participating component publishers have published valid canonical metadata assets.

For each new versioned component release, its owning repository generates Component Release Metadata from the exact tag commit after package artifacts and checksums exist, then uploads the JSON as an asset on that GitHub Release. It is not committed under a per-version `registry/releases/` source-tree path.

Canonical asset names:

- Default variant: `<component-id>-<version>.json`.
- Non-default variant: `<component-id>-<variant>-<version>.json`, for example `frontend-tui-1.1.1.json`.

The metadata's `publication` object binds the exact repository URI, release tag, full tag-resolved commit and metadata asset basename. GitHub Release Asset API size/digest identify the metadata bytes themselves. Package descriptors separately bind immutable artifact URI, target, format, layout, source/toolchain provenance, SHA-256 and exact byte size.

Registry validates those publication identities before a candidate reaches the normal SemVer/dependency/contract resolver. A moved tag, missing/duplicate asset, missing digest, size/digest mismatch, invalid source revision, malformed metadata, ambiguous release identity or exhausted pagination/retry budget is a hard failure. A corrupted discovered release must not silently fall back to a source build. Resolved Manifests preserve the exact release/asset identity so replay does not discover a newer version.

## Immutable Registry executable bootstrap

The normal Registry executable path is artifact-first. CDIN's `deps.lock` must pin all of the following under `[tooling.registry]` before the consumer path can run:

- Registry repository URI.
- Full immutable source commit SHA and Registry SemVer.
- Exact release tag (`v<version>`).
- SHA-256 and exact byte size of `registry-release-<version>.json`.

The bootstrap selects one of the five supported executable targets:

| Target ID | Required binary asset |
|---|---|
| `linux-amd64` | `registry-linux-amd64` |
| `linux-arm64` | `registry-linux-arm64` |
| `darwin-amd64` | `registry-darwin-amd64` |
| `darwin-arm64` | `registry-darwin-arm64` |
| `windows-amd64` | `registry-windows-amd64.exe` (MSYS2 UCRT64) |

It then verifies the exact GitHub Release tag and its resolved commit (including annotated tags), the prerelease flag, the lock-pinned descriptor bytes, the five-target descriptor inventory, GitHub's asset digests/sizes, the Catalog identity/schema/digest/size, and the selected executable's actual ELF/Mach-O/PE architecture. The Catalog and Registry executable therefore come from one pinned Registry release identity.

The cache key binds the Registry version, target, and descriptor digest. Every cache hit is re-verified. Offline use is allowed only for a previously verified cache of the exact same pin and target. Corrupt or incomplete cache content is never executed or reused. The normal bootstrap does not clone the Registry source repository, install Go, run Registry Go tests or compile Registry on the consumer machine.

**Historical state (superseded 2026-11-15):** The old `v0.1.0-dev`/`0.2.0-dev.1` warning below predates the immutable Registry `v1.0.0` Release. The current blocker is the schema/authentication defect in that immutable `v1.0.0` consumer and the absence of the corrected immutable `v1.0.1` Release. See the current artifact-first status and dependency matrix above; do not substitute `latest` or an unpublished source commit.

## Developer source mode

Registry source builds are available only as an explicit developer operation:

```sh
make registry-dev
make registry-gui-dev
```

These targets use the pinned Registry source revision and pass the separate `--developer-source-components` policy to permit source delivery for Runtime/Frontend while their immutable package Releases are unavailable. They require Git and Go 1.27.3 or newer. The Pipeline source task uses the same explicit opt-in; it is not the ordinary consumer bootstrap.

The current PR #149 candidate pins the published Kernel 1.2.3 plus logger 0.1.0 SDK and Backend 1.2.2 native `cmake-prefix-v1` artifacts, then stages them into CDIN's private prefix and checks Kernel ABI plus Manifest identity. These are candidate selections until PR #149 merges and all clean-consumer acceptance jobs pass.

The PR #149 candidate consumes the published Runtime 1.0.0 Lua module package and Frontend Core/TUI/GUI-SDL 1.2.2 artifacts. The five-target SDL3 SDK 3.4.16 Release is also published and pinned for the GUI-SDL profile. TUI remains SDL-free. Clean-prefix consumption, target compatibility, and real installed-product interaction tests remain mandatory; package publication alone does not complete #122 or #124.

Registry `v1.0.0` and its same-tag Catalog/descriptor are published and pinned in the PR #149 candidate, but the binary fails the current Manifest schema floor when ADR-0028 provenance is serialized. Registry #75/#77 fixes are on Registry `main`; the immutable `v1.0.1` release remains required before the normal consumer pin can advance. CDIN #122 still requires clean target-specific installation, secure extraction, cache/offline replay and a Composition-Root-only build.

## Product profiles

- `registry/product-definition.tui.yaml` selects the shared Kernel, Runtime and Backend contracts plus Frontend TUI.
- `registry/product-definition.gui-sdl.yaml` selects the shared Core and GUI-SDL adapter, with TUI fallback where defined by the Product Definition.
- Core is resolved and installed once. TUI never acquires SDL3. SDL3 is exclusive to GUI-SDL.
- Product Definitions are updated only to immutable component releases that have verified package assets and compatible API/ABI/Protocol/Host API identities.

Do not update profile pins to an unmerged PR branch or to a component main SHA that has no published release metadata. Do not expose IME or PaneTree capabilities until the exact pinned stack passes product-level live E2E tests.

## Commands

Consumer Registry executable acquisition:

```sh
make registry
make registry-gui
CDIN_OFFLINE=1 make registry
```

The current hybrid developer stack (explicit Registry source mode):

```sh
make deps
make registry-dev
make stack-dev
make check
```

On current CDIN `main`, `make registry` continues to use its existing immutable pin. PR #149 carries the updated artifact-first candidate and remains unmerged. The next Registry pin can advance only after the corrected `v1.0.1` Release, Catalog, descriptor, five target executables and checksums have been published and independently verified.

For a GUI-SDL source-development stack, use `make registry-gui-dev` and the explicit SDL3 developer-source opt-in provided by the GUI stack target. Ordinary GUI-SDL consumer installation must use the pinned prebuilt SDK and must not build SDL3 from source.

The resolved Registry Manifest is authoritative for selected component versions and exact source/artifact identities. CDIN must not maintain a second component-version map. Product Definitions provide the consumer-specific roots and policies; the generic Registry remains independent.

## Verification and current product readiness

The Registry artifact bootstrap has isolated tests for target selection, annotated tag resolution, release/descriptor identity, Catalog pairing, executable architecture, cache corruption and offline reuse. The full Registry executable tests remain in the Registry repository's own release workflow; ordinary consumer installation does not run them.

A valid Registry resolution is not proof that CDIN is integrated or usable. CDIN still needs to:

- Consume real immutable Registry, component and SDL3 SDK releases from a clean prefix.
- Verify package digests and identities and securely extract the artifacts.
- Build only the Composition Root in the normal artifact-first path.
- Complete live IME and PaneTree tests against the exact compatible stack.
- Validate Unicode shaping, bidi, Persian/Arabic editing, TUI and GUI-SDL behavior.
- Verify extension capability isolation, process/session recovery, performance/soak and cross-platform installation/upgrade/uninstall.

Publisher code, a successful component CI run, or a source snapshot must not be reported as a release-ready CDIN application.
