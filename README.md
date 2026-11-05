# cdin — Composition Root

CDIN assembles and launches the independently maintained Kernel, Runtime,
Backend and Frontend components. It owns dependency pins, build/package
orchestration, process lifecycle and release tooling. It is not a second editor
implementation.

## Ownership

| Component | Owns |
|---|---|
| Kernel | document bytes, edit transactions, versions, snapshots, undo/redo |
| Runtime | Lua policy, commands, keymaps, configuration, plugins/extensions |
| Backend | Kernel/Runtime hosts, sessions, Protocol server, queues and OS services |
| Frontend | input, semantic projection, layout and rendering |
| CDIN | immutable pins, build, bundle, launch and process lifecycle |

Keymaps, plugin APIs and command policy remain Runtime-owned. Document
operations remain Kernel-owned and are accessed through Backend. CDIN composes
public contracts and does not copy implementation code.

## Build

Requirements: CMake 3.22+, C11 compiler, Make, Git, Python 3.11+, PUC Lua 5.4
development files, pkg-config and Go (for pinned psx/gix tools).

```sh
make stack
make check
psx check
gix doctor
```

The stack command checks out immutable component SHAs from deps.lock, builds
and tests logger, Kernel, Backend and Frontend in dependency order, installs
them into .deps/install, builds CDIN, runs executable-level lifecycle tests,
and launches cdin --check.

For an already installed component stack:

```sh
cmake -S . -B build -DCMAKE_INSTALL_PREFIX="$PWD/.deps/install" \
  -DCDIN_RUNTIME_SOURCE_DIR="$PWD/.deps/src/runtime"
cmake --build build --parallel
ctest --test-dir build --output-on-failure
cmake --install build
```

## Runtime and current release scope

```sh
cdin --help
cdin --version
cdin --check
```

--check validates Runtime loading and Backend create/start/pump/shutdown.
Interactive TUI/GUI launch remains fail-closed until Backend readiness/wakeup
and Frontend event-loop integration satisfy FE-019. This prevents CDIN from
claiming to be a live editor before it can deliver and consume input correctly.

See docs/development/integration-status.md for implemented behavior and open
release gates. Product create/open/edit/save/reopen E2E and measured memory/soak
benchmarks are not claimed complete.
