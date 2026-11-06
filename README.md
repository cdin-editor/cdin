# CDIN

<p align="center">
  <a href="https://github.com/cdin-editor/cdin-editor.github.io">
    <img src="https://raw.githubusercontent.com/cdin-editor/cdin-editor.github.io/main/public/cdin-icons/source/cdin-original-transparent-512.png" width="180" alt="CDIN logo" />
  </a>
</p>

<p align="center">
  <a href="https://github.com/cdin-editor/cdin/actions/workflows/ci.yml"><img src="https://github.com/cdin-editor/cdin/actions/workflows/ci.yml/badge.svg" alt="CI status"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0--or--later-blue.svg" alt="License: GPL-3.0-or-later"></a>
  <a href="https://www.lua.org/versions.html"><img src="https://img.shields.io/badge/Runtime-Lua%205.4-blue.svg" alt="Lua 5.4"></a>
  <a href="https://github.com/cdin-editor/spec"><img src="https://img.shields.io/badge/CDIN-Specification-purple.svg" alt="CDIN specification"></a>
</p>

<p align="center">The composition root for the CDIN editor components.</p>

CDIN brings together the Kernel, Runtime, Backend and Frontend projects. It owns the application build, dependency pins, packaging, launcher and process lifecycle. Editor behavior lives in the component that owns it.

## What is CDIN?

A user-facing editor needs a document engine, editor policy, operating-system services and a way to present the interface. CDIN keeps those responsibilities in separate projects and connects them through their public contracts.

| Component | Responsibility |
| --- | --- |
| **Kernel** | Owns document bytes, edits, versions, snapshots and undo/redo. |
| **Runtime** | Runs Lua 5.4 editor policy: commands, keymaps, configuration and plugins. |
| **Backend** | Hosts Kernel and Runtime, manages sessions and OS services, and serves the Frontend Protocol. |
| **Frontend** | Adapts input, presents the semantic UI model, performs visual layout and renders the editor. |
| **CDIN** | Pins, builds, packages and launches the components. |

CDIN is not a second editor engine. It must not copy document operations from Kernel, keymap or plugin behavior from Runtime, session logic from Backend, or layout and rendering from Frontend.

## Current status

The Composition Root candidate is tracked by [PR #110](https://github.com/cdin-editor/cdin/pull/110), branch feature/complete-composition-root-rewrite. Current head: 634075a92aeb5a6e58b817d2045d653dfbf8bbf2. The native full-stack workflow [42304522348](https://github.com/cdin-editor/cdin/actions/runs/42304522348) has been dispatched but its jobs have not started yet; the GUI live-session smoke is **NOT VERIFIED** on this head.

Earlier attempts exposed and led to fixes for the CDIN private include path, SDL3 text-event pointer semantics, exact-byte test length, CLI test allowlisting/gate wording, and reading the ui.flush scope/revision after its ACK reused the protocol client buffer. The current candidate captures that metadata before ACK and warms the SDL event loop by draining initial focus/resize events before injecting deterministic text and Ctrl+S. These are implementation fixes, not a GUI PASS claim.

CDIN pins Frontend PR #17 at immutable candidate 1dd2fc0826d302883fa0e6bab0cbead3ec84a6d4. [Frontend CI run 42304001468](https://github.com/cdin-editor/frontend/actions/runs/42304001468) passed Linux, macOS, Windows, SDL3 AddressSanitizer model/adapter tests, clean-prefix package consumer and Pipeline quality. The GUI model binds the actual Runtime view ID from the first view-scoped snapshot; it no longer assumes the Frontend attach view ID and Runtime-created view ID are identical. This verifies the independent Frontend package, not CDIN application launch.

Backend PR #18 is ready for review at 987acd2f04bf6cc7eed360a4328bb11085628457. [Backend CI 42300963625](https://github.com/cdin-editor/backend/actions/runs/42300963625) passed Markdown lint, Pipeline quality and Lua 5.4 resolver integration on Ubuntu, macOS and Windows. [Live Runtime integration 42300963086](https://github.com/cdin-editor/backend/actions/runs/42300963086), [Native resource stress 42300963234](https://github.com/cdin-editor/backend/actions/runs/42300963234) and [Code Quality 42300958559](https://github.com/cdin-editor/backend/actions/runs/42300958559) also passed. Backend Issue [#14](https://github.com/cdin-editor/backend/issues/14) is closed with these results.

The headless editing/save path and POSIX PTY remain verified on earlier fully green CDIN candidate [42265415995](https://github.com/cdin-editor/cdin/actions/runs/42265415995), before GUI-SDL composition was added. That historical evidence is not a substitute for current-head GUI acceptance. Keep interactive GUI-SDL launch experimental behind CDIN_ENABLE_EXPERIMENTAL_GUI_SDL=1; the renderer is still an ASCII/debug-text baseline, with font shaping, bidi/Persian layout, IME and full pane rendering incomplete.

The CDIN epic [#111](https://github.com/cdin-editor/cdin/issues/111) remains open. Reconnect with pending work, process recovery, repeated start/stop, plugin capability isolation, product RSS/latency/soak baselines and native installers remain release gates. CodeQL C/C++, Python and Actions checks pass, but the JavaScript/TypeScript job fails because this repository has no JS/TS source; remove that language from the repository security/code-scanning language selection. This is a repository setting, not a source change.

The [CDIN Specification](https://github.com/cdin-editor/spec) defines the cross-component contracts. This README describes the implementation in this repository and does not override the Spec.

## Build the pinned stack

You need a C11 compiler, CMake 3.22 or newer, Make, Git, Python 3.11 or newer, `pkg-config`, PUC Lua 5.4 development files and Go 1.25 or newer for the repository tools.

Clone CDIN and build the pinned component stack:

```sh
git clone https://github.com/cdin-editor/cdin.git
cd cdin
make stack
```

The stack task checks out the immutable revisions in `deps.lock`, builds and tests the pinned logger, Kernel, Backend and Frontend projects, installs them into `.deps/install`, then builds CDIN and runs its CLI and lifecycle checks.

Platform-specific setup and the full local workflow are in the [Developer guide](docs/development.md). For a short explanation of the commands available today, see the [User guide](docs/user-guide.md).

## Try the current executable

After `make stack`, the executable is installed under `.deps/install/bin`:

```sh
./.deps/install/bin/cdin --help
./.deps/install/bin/cdin --version
./.deps/install/bin/cdin --check
SDL_VIDEODRIVER=dummy ./.deps/install/bin/cdin --frontend gui-sdl --check
# Interactive GUI is experimental:
CDIN_ENABLE_EXPERIMENTAL_GUI_SDL=1 ./.deps/install/bin/cdin --frontend gui-sdl
```

On Windows, use `.deps/install/bin/cdin.exe` from the MSYS2 UCRT64 environment.

The `--check` command is a headless lifecycle and protocol integration check. It attaches a Frontend Protocol session, verifies snapshot/flush/ACK and resize, then exercises document create → text/paste → undo/redo → save → close → open through public Frontend/Backend/Runtime/Kernel APIs. It compares exact bytes, including NUL, invalid UTF-8, BOM and line-ending variants, against both disk and the reopened document. The headless CTest passed in the Linux, macOS and Windows jobs in CI run 42117574266. It does not render a display or launch the TUI. On POSIX, an experimental TUI path can be attempted only with `CDIN_ENABLE_EXPERIMENTAL_TUI=1`; its release gate is still failing.

## What CDIN provides

- Immutable component and tooling pins in `deps.lock`.
- A repeatable source-build workflow for the pinned component stack.
- Build-time Frontend/Backend Protocol version checks and runtime Backend/Runtime version checks.
- Runtime asset installation and Backend lifecycle composition.
- A small CLI for help, version and lifecycle validation.
- Pipeline tasks, PSX repository checks and Gix branch-flow configuration.
- A deterministic source snapshot with SHA-256 verification; trusted pushes to `main` receive artifact provenance attestation after all required CI jobs pass.

## Documentation

| Guide | What it covers |
| --- | --- |
| [User guide](docs/user-guide.md) | What CDIN does today, prerequisites and the current CLI. |
| [Installation](docs/installation.md) | Building and installing a local development stack; package status. |
| [Architecture](docs/architecture.md) | Component ownership, dependency direction and process lifecycle. |
| [Developer guide](docs/development.md) | Repository layout, build loop, tests, CI and contribution workflow. |
| [Architecture audit](docs/architecture/audit.md) | Implemented, partial and missing areas in the current rewrite. |
| [Spec traceability](docs/architecture/traceability.md) | Requirement IDs mapped to source and verification evidence. |
| [Dependency matrix](docs/development/dependency-matrix.md) | Pinned revisions and declared compatibility information. |
| [Integration status](docs/development/integration-status.md) | Current product capabilities and release gates. |
| [Tooling](docs/development/tooling.md) | Pipeline, PSX, Gix and dependency management. |
| [Resource benchmarks](tests/bench/README.md) | Benchmark requirements and current status. |
| [Changelog](CHANGELOG.md) | Changes recorded for the current rewrite. |

## CDIN projects

| Project | Role |
| --- | --- |
| [Specification](https://github.com/cdin-editor/spec) | Architecture, accepted ADRs and cross-component contracts. |
| [Kernel](https://github.com/cdin-editor/kernel) | Document and text engine. |
| [Backend](https://github.com/cdin-editor/backend) | Runtime host, Kernel integration, sessions and protocol server. |
| [Runtime](https://github.com/cdin-editor/runtime) | Lua editor behavior and extension policy. |
| [Frontend](https://github.com/cdin-editor/frontend) | Protocol client, input adapters and presentation. |
| [Website](https://github.com/cdin-editor/cdin-editor.github.io) | The separately maintained CDIN website. |

## Contributing

Changes in this repository must stay within the Composition Root boundary. Before changing an interface, inspect the Spec and the relevant component's public API. Read [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md) and the [Developer guide](docs/development.md).

Run the relevant build and integration checks locally. Report checks that were not run as `NOT RUN`; do not infer success from a configured workflow.

See also: [Code of Conduct](CODE_OF_CONDUCT.md) · [Security](SECURITY.md) · [Code owners](CODEOWNERS).

## License

CDIN is licensed under **GPL-3.0-or-later**. See [LICENSE](LICENSE) and [NOTICE](NOTICE) for the license text and third-party attributions.
