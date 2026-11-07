# CDIN

The composition root for the CDIN editor components.

CDIN pins, builds, packages and launches the independent Kernel, Runtime,
Backend and Frontend projects. It owns application composition and process
lifecycle; editor behavior stays in the component that owns it.

## Components

| Component | Responsibility |
| --- | --- |
| **Kernel** | Document bytes, edits, versions, snapshots and undo/redo. |
| **Runtime** | Lua editor behavior: commands, keymaps, configuration and plugins. |
| **Backend** | Sessions, OS services, Runtime host and Frontend Protocol server. |
| **Frontend** | Input adapters, semantic UI presentation, layout and rendering. |
| **CDIN** | Dependency pins, build, packaging, launcher and process lifecycle. |

## Current status

- CDIN Composition Root and Registry handoff: [PR #110](https://github.com/cdin-editor/cdin/pull/110).
- Product integration epic: [Issue #111](https://github.com/cdin-editor/cdin/issues/111).
- Registry is a build-time delivery-plane tool. It resolves component versions and immutable source revisions, prepares the workspace and emits the Resolved Manifest. It is never linked into CDIN or any component at runtime.
- Kernel, Runtime, Backend and Frontend own their own Registry Release Metadata. CDIN supplies TUI and GUI-SDL Product Definitions and a pinned Catalog Index.
- The current Runtime candidate is 1.0.0-rc.1; prerelease selection is explicitly transitional and will be disabled after a stable Runtime release.
- Registry implementation and the new product E2E tests are in the branch; the full current-head Linux/macOS/Windows and sanitizer CI matrix is still required before this integration is marked verified.
- GUI-SDL remains experimental. The renderer is an ASCII/debug-text baseline; full PaneTree rendering, IME, shaping, bidi/Persian layout and recovery remain release gates.

## Build

Requirements: C11 compiler, CMake 3.22+, Make, Git, Python 3.11+, Go 1.27.3+,
`pkg-config` and Lua 5.4 development files.

```sh
git clone https://github.com/cdin-editor/cdin.git
cd cdin
make stack
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
