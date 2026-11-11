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

- The Composition Root foundation is merged: [PR #110](https://github.com/cdin-editor/cdin/pull/110), merge commit `e2ea9f74bf247a1b1104cded53255ac4a34551a0`.
- SDL3 SDK producer [PR #126](https://github.com/cdin-editor/cdin/pull/126) is merged at `f12f1fca4ca1d4fb5060a802549596085e3172d2`. Its five-target native build/consumer matrix has passed, but the tag-backed SDK Release and downloadable assets are not published.
- Artifact-first consumer work is in [PR #131](https://github.com/cdin-editor/cdin/pull/131); the previous bounded SDL3 staging hardening is merged in [PR #130](https://github.com/cdin-editor/cdin/pull/130). PR #131 remains under exact-head native, sanitizer, package-consumer and quality validation.
- The current hybrid developer/CI stack reuses the existing Kernel 1.2.1 SDK (including logger 0.1.0), consumes Backend 1.2.1 as a native package, and still uses source delivery for Runtime 1.0.0-rc.2 and Frontend 1.0.2. GUI-SDL development still builds the pinned SDL3 3.4.16 source; TUI never acquires SDL3.
- The next immutable publisher candidates are Runtime 1.0.0-rc.3, Backend 1.2.2, Frontend 1.1.1, Registry 0.2.0-dev.1 and the SDL3 3.4.16 SDK. Publisher code is prepared, but their tags, canonical metadata assets and package Releases have not been published. Historical releases remain unchanged.
- Artifact-first installation is intentionally fail-closed until the corrected Registry executable/Catalog pair, Runtime module archive, Backend/Frontend packages and GUI-SDL SDK are published, pinned and verified. Normal `make install` must not clone or build component repositories.
- Product integration remains DEVELOPMENT. [CDIN #111](https://github.com/cdin-editor/cdin/issues/111), [#118](https://github.com/cdin-editor/cdin/issues/118), [#121](https://github.com/cdin-editor/cdin/issues/121), [#122](https://github.com/cdin-editor/cdin/issues/122) and [#124](https://github.com/cdin-editor/cdin/issues/124) remain open. IME and PaneTree splitter capabilities must stay unadvertised until compatible immutable Runtime/Backend/Frontend releases are pinned and live product E2E passes.
- GUI-SDL remains experimental. Its current renderer is an ASCII/debug-text baseline; production Unicode shaping/bidi/Persian text, IME, panels/scrolling, FE-019 stress and supported release-mode launch remain product gates. Do not distribute the current `--check` executable or experimental TUI as a completed interactive editor.
- See [integration status](docs/development/integration-status.md), [installation](docs/installation.md) and [issue #111](https://github.com/cdin-editor/cdin/issues/111) for the live readiness boundary.

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

**Current release readiness:** ordinary `make install` is intentionally fail-closed until the corrected Registry Release, Runtime/Frontend packages and GUI-SDL SDK are published and pinned. Use the `*-dev` targets only for the current hybrid source-development workflow; this is not a completed artifact-first consumer install.

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
