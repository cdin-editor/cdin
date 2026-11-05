# Development tooling

CDIN uses external tools rather than copying their implementations. Immutable revisions are recorded in `deps.lock`.

## 1. Pipeline

[`m-mdy-m/pipeline`](https://github.com/m-mdy-m/pipeline) owns the local/CI task graph in `pipeline.toml`.

```sh
pipeline validate
pipeline run check
pipeline run package
```

GitHub Actions installs the platform toolchain and invokes Pipeline. Build and test ordering belongs in Pipeline tasks, not a second set of workflow-specific shell scripts.

## 2. PSX

[`m-mdy-m/psx`](https://github.com/m-mdy-m/psx) checks the repository shape declared in `psx.yml`.

```sh
psx check
```

The expected layout is intentionally small: C11 launcher modules, scripts, integration-test documentation, architecture/development docs and the workflow directory.

## 3. Gix

[`m-mdy-m/gix`](https://github.com/m-mdy-m/gix) owns branch-flow checks. The active configuration is `.gix/config`.

```sh
gix doctor
```

The current flow uses `main` as the base branch and topic branches with `feature/`, `bugfix/`, `hotfix/` and `release/` prefixes. A separate `develop` branch is not configured for this repository.

## 4. Dependencies

`deps.lock` pins each component and tool to an immutable commit. `scripts/deps.py` checks out the exact source revision; `scripts/build_stack.py` builds and tests the component stack in dependency order.

```sh
python3 scripts/deps.py
make stack
```

The source checkouts under `.deps/src/` are build inputs for verification. CDIN source consumes installed public headers and libraries from `.deps/install/`; it must not include private component headers or compile copied implementation files.

## 5. Logging

CDIN uses the pinned `m-mdy-m/log.c` library for its own startup and composition diagnostics. Backend records arrive through Backend's configured callback and are translated from Backend's level values into the logger's level values. The callback context must remain alive until Backend has been destroyed.

Do not add another logger or route component logs around their documented logging boundary.

## 6. CI, artifact integrity and action updates

The CI workflow runs the pinned stack on Linux, macOS and Windows, plus a Linux ASan/UBSan/leak-detection job. The separate CodeQL workflow performs traced C/C++ analysis and Python analysis.

Third-party Actions are referenced by full commit SHA, with the upstream release tag recorded in a comment. Dependabot checks the GitHub Actions ecosystem weekly and opens update PRs; review each update and require the CI/CodeQL checks before merging it.

The source-snapshot task writes a deterministic ZIP with sorted paths, fixed timestamps and permissions, and no symlink traversal. It builds the archive twice and compares the bytes, checks archive paths/CRCs, and writes a SHA-256 sidecar. CI validates the checksum before uploading the archive.

Only a trusted push to `main` creates a signed GitHub artifact provenance attestation for the source snapshot. PR builds do not receive a trusted release attestation. The source snapshot is a review artifact, not a runnable installer or application release.

The repository's GitHub Default Setup CodeQL workflow is configured outside these files. Its current dynamic workflow still attempts JavaScript/TypeScript analysis even though this repository has no JavaScript/TypeScript source. The explicit workflow in this repository covers C/C++ and Python; adjust the repository's Default Setup language selection in GitHub settings to remove the unsupported JS/TS selection.
