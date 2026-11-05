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

This repository is in the Composition Root rewrite. The current application target is version `0.2.0`. The headless Frontend/Backend/Runtime/Kernel document path is implemented, and the POSIX TUI has an opt-in experimental launch path. The latest fully completed native matrix inspected for the current candidate is [CI run 42117574266](https://github.com/cdin-editor/cdin/actions/runs/42117574266), on commit `dd1f5896c27756948750a1adc1770b16b4207b66`.

The headless `--check` path performs HELLO/HELLO_ACK, real ATTACH, ordered UI snapshot/flush/ACK and resize, then document creation, text and binary paste, undo/redo, atomic save, close/open and byte-exact reads. Its expanded fixtures cover NUL, invalid UTF-8, BOM, LF-only and mixed CRLF/LF/CR data, plus missing-file and failed-save recovery. The headless CTest passes on Linux, macOS and Windows in run 42117574266; the Windows job also completed the full 9/9 CDIN CTest suite, all 6 architecture tests and the compiler-resolved include graph audit.

The POSIX `--frontend tui` launch path is present but deliberately gated by `CDIN_ENABLE_EXPERIMENTAL_TUI=1`. It opens the real terminal, attaches to Backend, drives the Frontend TUI event-loop adapter and restores terminal state on shutdown. It is **not release-ready**: the live PTY smoke on Linux and macOS still fails after initial rendering because a matching `view.lines` response can arrive after Frontend has cleared its pending-request state. Frontend PR [#11](https://github.com/cdin-editor/frontend/pull/11) has merged the request-lifecycle fix as `e29df5118e7b822912724b15c0c963b0b99f2f8a`; CDIN pins that SHA. The current CDIN PTY/native matrix is being re-run on the merged dependency in [CI run 42122228431](https://github.com/cdin-editor/cdin/actions/runs/42122228431). Windows TUI remains fail-closed until a native Console readiness bridge exists. GUI-SDL launch is not implemented.

This is **not yet a complete, interactive editor**. Plugin capability isolation, multiple Frontends and reconnect recovery, product RSS/latency/soak benchmarks, platform installers and a stable release process remain open gates. Track them in [issue #111](https://github.com/cdin-editor/cdin/issues/111) and see [Integration status](docs/development/integration-status.md). The separate GitHub Code Quality workflow still attempts JavaScript/TypeScript analysis even though this repository has no JS/TS source; Python passes, but the JS/TS job fails after extracting only YAML files. Deselect JavaScript/TypeScript under Settings → Security → Code quality. CodeQL Default Setup remains enabled; the custom advanced workflow is intentionally absent to avoid conflicting SARIF uploads.

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
