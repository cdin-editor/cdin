# CDIN

The composition root for the CDIN editor components.

CDIN owns declarative Product Definitions and an immutable Product Catalog
Index. The independently maintained Registry tool validates that Catalog,
resolves the component graph, and acquires verified artifacts or explicitly
permitted developer source. Each Catalog entry binds a public Release Metadata
URL to its exact SHA-256. CDIN then builds, packages and launches the product.

## Components

| Component | Responsibility |
| --- | --- |
| **Kernel** | Document bytes, edits, versions, snapshots and undo/redo. |
| **Runtime** | Lua editor behavior: commands, keymaps, configuration and plugins. |
| **Backend** | Sessions, OS services, Runtime host and Frontend Protocol server. |
| **Frontend** | Input adapters, semantic UI presentation, layout and rendering. |
| **Registry** | Build-time release resolution, immutable artifact/source acquisition and Resolved Manifest; never a runtime dependency. |
| **CDIN** | Product Definitions, immutable Product Catalog, build, packaging, launcher and process lifecycle. |

## Current status

**CDIN 1.0.0 Stable is not ready.** The repository is still the 0.2.0 Composition Root candidate. Component artifacts have now been published, but clean product installation, supported interactive launch and the live product acceptance gates remain separate requirements.

### Published component and tool identities

- **Kernel:** stable `v1.2.3`, Kernel ABI `1.1.0`, and logger C API `0.1.0`. Its five target-native SDK archives are pinned independently from the component Registry packages.
- **Runtime:** stable `v1.0.0`, including the platform-neutral Lua module archives and canonical Release metadata.
- **Backend:** stable `v1.2.2`, with five target-native CMake development packages and canonical Release metadata.
- **Frontend:** stable `v1.2.2`, with separate Core, TUI and GUI-SDL packages for the five maintained native targets.
- **Registry:** stable `v1.0.1` is published as an immutable Release with five native executables, its generic Catalog, a source/asset descriptor and SHA256SUMS. CDIN PR #149 pins the exact tag-resolved commit `ed7c8fbe5513b6b0d6eb76d31191c696b98f8d27` and descriptor digest `c37a1902afe6d41291b0f29d6970408d70dae239881307533673ceaf85634403`. CDIN uses its own separately pinned product Catalog. Registry remains a build-time tool, not a runtime dependency.
- **SDL3 SDK:** `sdl3-sdk-v3.4.16` is published as an immutable-tagged prerelease. Its five target archives are pinned by tag-resolved source commit, byte size and SHA-256 in `deps.lock`; only GUI-SDL may acquire it.

### Product integration state

- Registry `v1.0.1` is now published with both upstream fixes: Manifest schema-floor selection (Registry [PR #75](https://github.com/cdin-editor/registry/pull/75)) and authenticated cross-repository Release discovery (Registry [PR #78](https://github.com/cdin-editor/registry/pull/78)). CDIN PR #149 pins the immutable `v1.0.1` consumer assets and exact source commit. The earlier `v1.0.0` release remains immutable and is not used by the new PR head.
- CDIN PR [#148](https://github.com/cdin-editor/cdin/pull/148) is merged at `dc9d6314a8424ef9b1247cbc50af1af11f4e8ba5`. It preserves the immutable SDL3 tag during recovery and makes live smoke tests resolve the Runtime package selected by the active CMake configuration.
- CDIN PR [#149](https://github.com/cdin-editor/cdin/pull/149) carries the artifact-first consumer refresh: Registry consumer and explicit developer source both pin immutable `1.0.1` at commit `ed7c8fbe5513b6b0d6eb76d31191c696b98f8d27`, Backend/Frontend `1.2.2`, Runtime `1.0.0`, the exact five-target SDL3 SDK pin, dynamic Backend artifact validation, stable Product Definition prerelease policy, and public artifact-first Kernel/Registry/SDL3 bootstraps. It remains open; exact-head CI, Product Acceptance and SDL3 checks must pass before merge. Registry publication is complete, but CDIN clean-consumer acceptance remains in progress.
- The TUI Product Definition does not declare or acquire SDL3. The GUI-SDL Product Definition declares the external SDL3 SDK contract.
- CDIN product resolution uses six static Catalog entries with exact public Release Metadata URLs and SHA-256 digests, pinned by `tooling.cdin_catalog` in `deps.lock`. Consumer, sanitizer and Product Acceptance workflows therefore make no cross-repository Release-discovery API calls and require no PAT secret. The Registry and SDK bootstraps still verify all downloaded bytes.
- Linux distributions target glibc `2.39` and are built on Ubuntu `24.04`; CI does not use the moving `ubuntu-latest` label for these packages. Build and packaging checks reject a different host glibc version so the declared ABI cannot understate the binary's real runtime requirement.
- GUI-SDL's current renderer still uses diagnostic debug text and does not provide production shaping, font fallback, grapheme layout or bidi. Persian/Arabic editing is not a supported stable claim.
- The GUI-SDL IME and PaneTree implementations exist in Frontend `v1.2.2`, but their compile-time capability gates default to OFF in the published packages. They must remain unadvertised until CDIN #118 passes against the exact selected stack.
- TUI and GUI-SDL launch remain experimental product paths; a successful component build or headless smoke is not proof of a supported interactive editor.

### Stable release gates

The parent acceptance issue is [CDIN #111](https://github.com/cdin-editor/cdin/issues/111). The remaining tracked work includes [live IME and PaneTree E2E #118](https://github.com/cdin-editor/cdin/issues/118), [pinned Registry verification #121](https://github.com/cdin-editor/cdin/issues/121), [artifact-first product installation #122](https://github.com/cdin-editor/cdin/issues/122), and [SDL3 SDK consumption #124](https://github.com/cdin-editor/cdin/issues/124). Downstream clean-consumer verification remains tracked by Runtime [#16](https://github.com/cdin-editor/runtime/issues/16), Backend [#35](https://github.com/cdin-editor/backend/issues/35) and Frontend [#40](https://github.com/cdin-editor/frontend/issues/40).

Before a `v1.0.0` tag or Stable Release can be created, the exact selected component stack must pass clean-cache, warm-cache and offline installation; extracted-package tests outside the source checkout; TUI and GUI-SDL launch/input/shutdown; Windows console readiness; live capability tests; extension and process/transport recovery; Unicode shaping and Persian/Arabic presentation; performance/soak and security checks; and the complete supported target/profile matrix. Upgrade/uninstall, package contents, licenses, release provenance and checksums must also be verified. A queued workflow is not a pass, and an immutable component release is not a CDIN product release.

## Build

Consumer build requirements: C11 compiler, CMake 3.22+, Make, Python 3.11+,
`pkg-config` and Lua 5.4 development files. Git and Go 1.27.3+ are needed only
for the explicit hybrid developer/CI source-build targets.

```sh
git clone https://github.com/cdin-editor/cdin.git
cd cdin
make install                       # normal artifact-only TUI consumer path
CDIN_FRONTEND_VARIANT=gui-sdl make install
make stack-dev                      # explicit hybrid developer/CI TUI path
make stack-gui-dev                  # explicit hybrid developer/CI GUI-SDL path
./.deps/install/bin/cdin --help
./.deps/install/bin/cdin --version
./.deps/install/bin/cdin --check
```

On Windows, use `.deps/install/bin/cdin.exe` from MSYS2 UCRT64.

**Current release readiness:** the ordinary `make install` path uses the immutable Registry 1.0.1 executable, the CDIN-owned SHA-256-pinned Product Catalog and published component packages; no source checkout or cross-repository Release API discovery is part of that consumer path. The exact five-target × two-profile install, offline/cache and extracted-product acceptance is still being validated. The `*-dev` targets remain explicit contributor/CI source-build paths and are not substitutes for consumer installation.

## Documentation

[User guide](docs/user-guide.md) ·
[Installation](docs/installation.md) ·
[Architecture](docs/architecture.md) ·
[Developer guide](docs/development.md) ·
[Architecture audit](docs/architecture/audit.md) ·
[Spec traceability](docs/architecture/traceability.md) ·
[Dependency matrix](docs/development/dependency-matrix.md) ·
[Registry integration](docs/development/registry.md) ·
[Installed distributions](docs/development/distribution.md) ·
[Integration status](docs/development/integration-status.md) ·
[Tooling](docs/development/tooling.md)

## Related

[Specification](https://github.com/cdin-editor/spec) ·
[Registry](https://github.com/cdin-editor/registry) ·
[Kernel](https://github.com/cdin-editor/kernel) ·
[Runtime](https://github.com/cdin-editor/runtime) ·
[Backend](https://github.com/cdin-editor/backend) ·
[Frontend](https://github.com/cdin-editor/frontend)

## License

GPL-3.0-or-later. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
