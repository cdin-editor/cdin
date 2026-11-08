# CDIN

The composition root for the CDIN editor components.

CDIN supplies declarative Product Definitions and uses the independently
maintained Registry tool to resolve, collect and verify component source. It
builds, packages and launches the prepared product. It does not own a Catalog
Index or component repository map; those are maintained with Registry and
component release metadata, respectively.

## Components

| Component | Responsibility |
| --- | --- |
| **Kernel** | Document bytes, edits, versions, snapshots and undo/redo. |
| **Runtime** | Lua editor behavior: commands, keymaps, configuration and plugins. |
| **Backend** | Sessions, OS services, Runtime host and Frontend Protocol server. |
| **Frontend** | Input adapters, semantic UI presentation, layout and rendering. |
| **Registry** | Build-time release resolution, immutable source collection and Resolved Manifest; never a runtime dependency. |
| **CDIN** | Product Definitions, build, packaging, launcher and process lifecycle. |

## Current status

- CDIN Composition Root and Registry handoff: [PR #110](https://github.com/cdin-editor/cdin/pull/110), merged on 2026-11-08 as `e2ea9f74bf247a1b1104cded53255ac4a34551a0`.
- Product integration epic: [Issue #111](https://github.com/cdin-editor/cdin/issues/111).
- Registry is a build-time delivery-plane tool. It resolves component versions and immutable source revisions, prepares the workspace and emits the Resolved Manifest. It is never linked into CDIN or any component at runtime.
- Kernel, Runtime, Backend and Frontend own their own Registry Release Metadata. CDIN supplies TUI and GUI-SDL Product Definitions. The Catalog Index snapshot is versioned in the pinned Registry checkout; CDIN contains no component repository URLs or release metadata map.
- The current Registry integration candidate is Runtime `1.0.0-rc.2`, which provides `org.cdin.runtime-extension-contract` 1.0.0, plus Frontend TUI/GUI-SDL `1.0.1`. Runtime prerelease selection remains explicitly transitional until a stable Runtime release.
- Current Registry pin: `2a611eca830c0f235dacab04a1d006a8fd46e586`; selected packages are Kernel `1.2.1`, Backend `1.2.0`, Frontend TUI/GUI-SDL `1.0.1`, and Runtime `1.0.0-rc.2`.
- Runtime RC2 provides `org.cdin.runtime-extension-contract@1.0.0`; prerelease selection remains transitional until a stable Runtime release.
- Runtime #7, Backend #19, Spec #16 and Spec #23 are closed. Frontend #24 remains open only for the formal v1.0.1 tag/release decision; Frontend #15 and CDIN #111 retain product gates.
- The JavaScript/TypeScript CodeQL no-source analyzer requires a repository Settings language-selection update tracked by [Issue #113](https://github.com/cdin-editor/cdin/issues/113); no dummy source is added.
- The Composition Root and Registry handoff are merged and verified: [exact-head CI run 42447891569](https://github.com/cdin-editor/cdin/actions/runs/42447891569) passed all six Linux/macOS/Windows × TUI/GUI-SDL jobs and the full-stack ASan/UBSan/leak job. Registry Go tests, schema validation, resolve/prepare/replay, Manifest verification and product E2E passed.
- GUI-SDL remains experimental. PaneTree/multi-pane geometry and live-session smoke pass, but the renderer is still an ASCII/debug-text baseline; production Unicode shaping/bidi/Persian text, IME, panels/scrolling, FE-019 stress and supported release-mode launch remain gates.

## Build

Requirements: C11 compiler, CMake 3.22+, Make, Git, Python 3.11+, Go 1.27.3+,
`pkg-config` and Lua 5.4 development files.

```sh
git clone https://github.com/cdin-editor/cdin.git
cd cdin
make stack                         # TUI product profile
make stack-gui                     # TUI + GUI-SDL product profile
./.deps/install/bin/cdin --help
./.deps/install/bin/cdin --version
./.deps/install/bin/cdin --check
```

On Windows, use `.deps/install/bin/cdin.exe` from MSYS2 UCRT64.

## Documentation

[User guide](docs/user-guide.md) ·
[Installation](docs/installation.md) ·
[Architecture](docs/architecture.md) ·
[Developer guide](docs/development.md) ·
[Architecture audit](docs/architecture/audit.md) ·
[Spec traceability](docs/architecture/traceability.md) ·
[Dependency matrix](docs/development/dependency-matrix.md) ·
[Registry integration](docs/development/registry.md) ·
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
