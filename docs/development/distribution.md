# Installed CDIN development distributions

**Status:** the distribution builder and extraction smoke are being integrated in the current CDIN change. A passing exact-head CI matrix is required before treating the generated files as validated.

## What is packaged

The distribution is built from the installed product prefix at `.deps/install`, not from the Git source snapshot. Each target/profile bundle contains:

- `bin/cdin` (or `bin/cdin.exe`) and all installed runtime libraries from the selected component packages;
- the Runtime Lua module tree under `share/cdin/lua`;
- the exact Registry Resolved Manifest under `share/cdin/registry-manifest.json`;
- `BUILD-INFO.json`, `LICENSE` and `NOTICE`.

Linux and macOS use a `.tar.gz` archive; Windows UCRT64 uses a `.zip` archive. The filename includes the CDIN version, target OS, architecture and profile, for example `cdin-0.2.0-linux-x86_64-tui.tar.gz`.

The adjacent `.sha256` file hashes the archive. The adjacent `.manifest.json` records the archive digest/size, source commit, target and ABI, profile, Registry Manifest digest, selected component package versions and immutable source revisions, and the CI run identity.

## Build and verification

The Pipeline `distribution-tests` task exercises the manifest, archive, checksum, safe-extraction and fail-closed cases. The `distribution` task runs after `stack` has installed the product. It creates the archive and extracts it into a fresh temporary directory outside the repository checkout.

The extracted executable is then run with `--version` and `--check`. The smoke deliberately does **not** set `CDIN_RUNTIME_ROOT`: CDIN must discover `share/cdin/lua` relative to its own installed `bin/cdin` path. This checks that the package remains usable after it has been moved away from the build prefix.

A TUI bundle rejects SDL3 files. A GUI-SDL bundle requires the pinned SDL3 SDK to be present in the installed prefix. Unsupported target/ABI combinations, symlinks in the installed prefix, archive path traversal, incomplete manifests and attempts to overwrite an existing distribution identity fail closed.

Run the pipeline task from a configured developer workspace with:

```sh
CDIN_FRONTEND_VARIANT=tui pipeline run distribution
CDIN_FRONTEND_VARIANT=gui-sdl pipeline run distribution
```

The normal CI pipeline runs the tests and distribution task as part of its full pre-release verification. Each OS/profile job uploads its generated archive, checksum and manifest as a GitHub Actions artifact for 30 days.

## Release boundary

These archives are **development-build artifacts**, not stable releases and not a claim that the complete interactive editor is production-ready. CI artifact upload is not GitHub Release publication. The current work does not create the rolling `latest` channel or an immutable SemVer application release.

The product remains DEVELOPMENT until the artifact-first component releases, supported product launch/E2E, GUI Unicode and Persian/Arabic presentation, IME and PaneTree product gates, and the separate rolling/SemVer release workflows have passed. See [integration status](integration-status.md) and [CDIN #111](https://github.com/cdin-editor/cdin/issues/111).
