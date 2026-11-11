# Registry integration

CDIN uses Registry as an independent build-time dependency resolver and artifact/source workspace preparer. Registry is not linked into the editor executable and is never a component runtime dependency.

The normative boundary is defined by the [Spec Registry contracts](https://github.com/cdin-editor/spec/blob/main/docs/architecture/registry-contracts.md), [ADR-0025 — Immutable Target Artifact Delivery](https://github.com/cdin-editor/spec/blob/main/docs/adr/ADR-0025-immutable-target-artifact-delivery.md), [ADR-0028 — GitHub Release Metadata Discovery](https://github.com/cdin-editor/spec/blob/main/docs/adr/ADR-0028-github-release-metadata-discovery.md), and the [module ownership boundaries](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md).

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

**Current release blocker (2026-11-11):** Registry main contains the corrected five-target publisher and release descriptor for `0.2.0-dev.1`, but that matching GitHub Release has not been published. The only published executable release, `v0.1.0-dev`, has duplicated Linux and macOS architecture digests and is not safe to consume as target-specific binaries. The current CDIN `deps.lock` does not yet contain the descriptor digest/size pin. Consequently, the normal Registry artifact path fails closed until Registry #58 is completed and the exact release identity is pinned. Do not substitute `latest`, the broken old release or an unpublished source commit.

## Developer source mode

Registry source builds are available only as an explicit developer operation:

```sh
make registry-dev
make registry-gui-dev
```

These targets use the pinned source revision and require Git and Go 1.27.3 or newer. The Pipeline's source-build Registry task is likewise a contributor/CI path; it is not the ordinary consumer bootstrap.

The current developer/CI stack is hybrid. Kernel 1.2.1 plus its bundled logger 0.1.0 SDK are downloaded from the existing immutable Kernel Release assets, and Backend 1.2.1 is selected and materialized by Registry as a native `cmake-prefix-v1` artifact. CDIN stages both into its private install prefix and checks the Kernel version/ABI against the Manifest.

Runtime and Frontend are still source-delivered by the current Catalog; the stack builds those checked-out source units. GUI-SDL also builds the checksum-pinned SDL3 3.4.16 source archive until the merged SDK publisher has a real five-target Release with verified digests. TUI does not acquire SDL3.

The consumer Registry Release is still unavailable: the normal pin intentionally lacks descriptor digest/size, so the default binary path fails closed rather than using the unsafe `v0.1.0-dev` assets. The explicit Registry source-build mode is used for contributor/CI verification only. These partial artifact steps do not complete CDIN #122; the normal install still needs real Registry, Runtime, Frontend and SDL3 Releases and must then build only the Composition Root.

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

The ordinary `make registry` / `make stack` path uses the pinned Registry Release executable and fails closed until Registry #58 publishes the corrected immutable Release.

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
