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

This repository is in the Composition Root rewrite. The current application target is version `0.2.0`. The pinned stack builds and its component tests and Backend/Runtime lifecycle smoke test pass on Linux, macOS and Windows. Candidate commit `167de187af4f0d4df8a81c9afb86ba887eaf6cb4` passed [CI run 42024750897](https://github.com/cdin-editor/cdin/actions/runs/42024750897), including Linux ASan/UBSan/leak detection. [CodeQL run 42024750919](https://github.com/cdin-editor/cdin/actions/runs/42024750919) passed C/C++ traced analysis and Python analysis.

The executable currently supports `--help`, `--version` and `--check`. The check path loads the pinned Runtime modules, exercises Backend create/start/pump/shutdown/destroy, then performs Frontend Core HELLO/HELLO_ACK, a real ATTACH, ordered initial UI snapshot delivery, `ui.flush`/ACK and resize over an in-process byte transport. This integration path is implemented in the current candidate and awaits fresh native CI. Interactive TUI and GUI launch remain disabled until a supported adapter package, Backend readiness/wakeup and the Frontend event loop are integrated under FE-019.

This is **not yet a complete, interactive editor**. A real Frontend connection, end-to-end document editing and save/reopen workflow, measured memory/soak benchmarks, release packages and stable release process are still release gates. Track them in [issue #111](https://github.com/cdin-editor/cdin/issues/111) and see [Integration status](docs/development/integration-status.md) for current evidence. GitHub Code Quality's generated analysis is still configured to scan JavaScript/TypeScript, although this repository contains no JS/TS source. Remove that language under Settings → Security → Code quality; the Python Code Quality job and repository-owned C/C++/Python CodeQL analyses are separate and pass.

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

The `--check` command is a headless lifecycle and protocol integration check. It attaches a headless view and verifies the initial semantic snapshot/flush/ACK and resize path; it is not an interactive editing session and does not render a display, create/edit a document or open a window.

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
