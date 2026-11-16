# Installed CDIN development distributions

**Status:** the installed-prefix distribution builder creates target/profile-qualified integration and CI artifacts. It is not yet a user-facing installer or a CDIN product release.

## What is packaged

The archive is created from the actual installed prefix at `.deps/install`, not from the Git source snapshot. Each target/profile bundle contains:

- `bin/cdin` (or `bin/cdin.exe`) and the files installed by the selected component packages;
- the Runtime Lua module tree under `share/cdin/lua`;
- the exact Registry Resolved Manifest under `share/cdin/registry-manifest.json`;
- `BUILD-INFO.json`, `LICENSE` and `NOTICE`.

Linux and macOS use `.tar.gz`; Windows UCRT64 uses `.zip`. The filename includes the project version, target OS/architecture and profile, for example `cdin-0.2.0-linux-x86_64-tui.tar.gz`. CDIN's CMake/project version is still `0.2.0`; it must not be labelled `1.0.0` before the Stable release gates pass.

The adjacent `.sha256` file hashes the archive. The adjacent `.manifest.json` binds its exact size and digest to the source commit, target ABI, profile, Registry version, Catalog metadata identities, Registry Manifest digest, component Release metadata and artifact/source provenance, environment contracts, build dependencies and CI run identity.

The Kernel dependency is the immutable **Kernel v1.2.3** target SDK, tag commit `2fb09f52dc1a9963cf358ec54d584c520e174e67`, ABI `1.1.0`; its archive also includes the separately versioned logger C API `0.1.0` SDK. The five exact target archive sizes and digests are pinned in `deps.lock`.

GUI-SDL uses the published immutable **SDL3 SDK 3.4.16** Release, tag `sdl3-sdk-v3.4.16`, tag-resolved commit `d249122c51acbab7262a6cd1e675922fd043bac7`. All five target archives and checksum sidecars are pinned in `deps.lock`. The producer-only SDL source archive is separately pinned for the explicit SDK publishing workflow; ordinary GUI-SDL consumers use the prebuilt SDK. TUI must not download, stage or link SDL3.

The active CDIN PR #149 candidate selects Backend and Frontend 1.2.2 plus Runtime 1.0.0 from the same-tag Registry Catalog. The Registry consumer pin is still the published immutable **v1.0.0** binary; it has a known Manifest schema-floor defect when ADR-0028 Release-discovery provenance is serialized. Registry PR #75 fixes the schema logic on Registry main, but the corrected immutable **v1.0.1** tag/Release assets have not yet been published. Do not claim the candidate is clean-consumer accepted until the Registry v1.0.1 Release is verified and CDIN consumes it successfully.

## Build and verification

The Pipeline `distribution-tests` task exercises Manifest validation, archive/checksum generation, bounded safe extraction, path collision/traversal rejection, provenance validation and failure cleanup. The `distribution` task runs after the selected stack has been installed.

The archive is staged in a temporary directory, extracted into a fresh directory outside the checkout, and verified before the archive, checksum and manifest are moved into the CI output directory. A failed extraction or executable smoke must leave no published candidate files.

The extracted executable is run with `--version` and `--check` without setting `CDIN_RUNTIME_ROOT`. This proves the headless Composition Root validation path can discover the bundled Runtime module tree relative to the extracted executable. It does **not** prove interactive TUI terminal startup/restoration or GUI-SDL startup/cleanup; those remain separate product acceptance gates.

A TUI bundle rejects SDL3 files and never acquires the SDL3 source or SDK. A normal GUI-SDL consumer obtains the exact immutable SDK through `scripts/sdl3_artifact.py`; the bootstrap verifies the tagged Release commit, GitHub asset size/digest, SHA-256 sidecar, package manifest, target ABI and static linkage before staging the SDK. The normal consumer must not compile SDL3 from source. Only the explicit SDK producer/developer path may use the separately checksum-pinned SDL source archive.

The Product Acceptance workflow is designed to produce one archive/checksum/manifest set for each of the five native targets × two profiles (ten bundles total), with artifact names keyed by explicit target and profile; uploaded workflow artifacts are retained for 30 days. They are CI artifacts, not GitHub Releases. A queued, cancelled or partial matrix is not acceptance evidence. The full ten-job run must pass on the exact PR head.

## Runtime dependency boundary

The current Backend package uses the Lua 5.4 C API supplied by the target build environment. The Lua shared runtime is not copied into the installed prefix by this distribution task. The Registry Manifest's `environment_contracts` records the Lua 5.4 contract, while the target ABI records the platform baseline. Hosted CI extraction smoke runs on runners where Lua 5.4 is installed.

Consequently, these bundles are not yet clean-machine installers. Before a product release, CDIN must either provide a supported OS-native dependency installation strategy or bundle the exact permitted runtime libraries, then verify dynamic dependency closure on clean supported machines. A successful `--check` on a configured CI runner is not evidence that a generic clean machine already has every runtime dependency.

## Release boundary

These archives are **development-build artifacts**, not stable releases, rolling `latest` updates or immutable SemVer application releases. CDIN currently has three distinct source/product channels:

- Every successful pushed CI run (including `main`) may publish a unique source-only `v0.0.0-dev.<run_number>` prerelease from that exact commit. This is contributor/source distribution, not an installable application.
- The fixed `latest` product prerelease is gated by a separate successful Product Acceptance workflow on `main`. A source build, headless smoke, or partial installed-product matrix is not sufficient to trigger it.
- A pushed SemVer tag is checked for reachability from `main`, then deliberately fails closed at the product-readiness gate. No versioned CDIN product Release is published until artifact-first component installation, full Product Acceptance, verified target/profile application archives and the exact immutable Registry Resolved Manifest are connected to Pipeline's compiled release publisher. `v0.0.0-dev.*` tags are excluded from this path.

`source-release.yml` is reserved for explicitly labelled source-only contributor distribution; it is not a versioned product publisher. The current SemVer workflow intentionally grants no write permission and fails at the readiness gate rather than publishing a source ZIP as an application. The source-snapshot and rolling publishers use their calling job's scoped Actions token for same-repository publication.

The product remains DEVELOPMENT until artifact-first component Releases, supported product launch/E2E, Unicode shaping and Persian/Arabic presentation, IME and PaneTree product gates, clean-machine dependency handling, and actual rolling/versioned product release acceptance have passed.

See [integration status](integration-status.md), [installation](../installation.md) and [CDIN #111](https://github.com/cdin-editor/cdin/issues/111).
