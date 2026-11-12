# Installed CDIN development distributions

**Status:** the installed-prefix distribution builder is an integration/CI artifact path. It is not a user-facing installer or a product release.

## What is packaged

The archive is created from the actual installed prefix at `.deps/install`, not from the Git source snapshot. Each target/profile bundle contains:

- `bin/cdin` (or `bin/cdin.exe`) and the files installed by the selected component packages;
- the Runtime Lua module tree under `share/cdin/lua`;
- the exact Registry Resolved Manifest under `share/cdin/registry-manifest.json`;
- `BUILD-INFO.json`, `LICENSE` and `NOTICE`.

Linux and macOS use `.tar.gz`; Windows UCRT64 uses `.zip`. The filename includes the product version, target OS/architecture and profile, for example `cdin-0.2.0-linux-x86_64-tui.tar.gz`.

The adjacent `.sha256` file hashes the archive. The adjacent `.manifest.json` binds its exact size and digest to the source commit, target ABI, profile, Registry version, Catalog metadata identities, Registry Manifest digest, component release-metadata and artifact/source provenance, environment contracts, build dependencies and CI run identity.

The build record includes the exact target-specific Kernel SDK v1.2.1 asset identity and its independently versioned logger 0.1.0 SDK. GUI-SDL also records the currently pinned SDL3 3.4.16 source archive and digest. This records reuse of the existing Kernel/logger packages; it does not create a new Kernel or logger packaging workstream.

## Build and verification

The Pipeline `distribution-tests` task exercises manifest validation, archive/checksum generation, bounded safe extraction, path collision/traversal rejection, provenance validation and failure cleanup. The `distribution` task runs after the selected stack has been installed.

The archive is staged in a temporary directory, extracted into a fresh directory outside the checkout, and verified before the archive, checksum and manifest are moved into the CI output directory. A failed extraction or executable smoke leaves no published candidate files.

The extracted executable is run with `--version` and `--check` without setting `CDIN_RUNTIME_ROOT`. This proves the headless Composition Root validation path can discover the bundled Runtime module tree relative to the extracted executable. It does **not** prove interactive TUI terminal startup/restoration or GUI-SDL startup/cleanup; those remain separate product acceptance gates.

A TUI bundle rejects SDL3 files and never acquires the SDL3 source or SDK. A GUI-SDL development bundle requires its pinned SDL3 files in the install prefix. Until CDIN #124 publishes the five target SDK assets, GUI-SDL CI still builds the pinned SDL3 source as an explicit developer/CI fallback.

The merged CI matrix now uploads one tested archive/checksum/manifest set for each of the five native targets × two profiles (ten bundles total), with artifact names keyed by explicit target and profile; retention remains 30 days. These are workflow artifacts, not GitHub Releases.

## Runtime dependency boundary

The current Backend package uses the Lua 5.4 C API supplied by the target build environment. The Lua shared runtime is not copied into the installed prefix by this distribution task. The Registry Manifest's `environment_contracts` records the Lua 5.4 contract, while the target ABI records the platform baseline. The hosted CI extraction smoke runs on runners where Lua 5.4 is installed.

Consequently, these bundles are not yet clean-machine installers. Before a product release, CDIN must either provide a supported OS-native dependency installation strategy or bundle the exact permitted runtime libraries, then verify dynamic dependency closure on clean supported machines. A successful `--check` on a configured CI runner is not evidence that a generic clean machine already has every runtime dependency.

## Release boundary

These archives are **development-build artifacts**, not stable releases, rolling `latest` updates or immutable SemVer application releases. The rolling channel is gated by a separate successful Product Acceptance workflow on main; the current version/check extraction smoke alone is not sufficient to trigger it. The product remains DEVELOPMENT until artifact-first component Releases, supported product launch/E2E, Unicode shaping and Persian/Arabic presentation, IME and PaneTree product gates, clean-machine dependency handling, and the separate rolling/SemVer release workflows have passed.

See [integration status](integration-status.md), [installation](../installation.md) and [CDIN #111](https://github.com/cdin-editor/cdin/issues/111).
