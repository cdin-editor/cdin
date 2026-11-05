# Developer guide

This guide is for contributors changing the Composition Root. It covers the repository layout, build loop, test evidence and rules for changing component pins.

The [Architecture](architecture.md) document describes ownership and runtime behavior. The [User guide](user-guide.md) describes the CLI from a user's point of view.

## 1. Repository layout

| Path | Responsibility |
| --- | --- |
| `AGENTS.md` | Mandatory architecture and engineering rules. |
| `deps.lock` | Immutable source and tool revisions. |
| `CMakeLists.txt` | Composition Root executable, package discovery and installation rules. |
| `src/main.c` | CLI dispatch and Backend lifecycle composition. |
| `src/cli/` | Small launcher argument parser. |
| `src/diagnostics/` | CDIN logger adapter and Backend log callback. |
| `include/cdin/` | Private headers shared by launcher modules. |
| `scripts/deps.py` | Pinned component checkout and materialization. |
| `scripts/build_stack.py` | Build/test/install orchestration for the pinned stack. |
| `scripts/check_boundaries.py` | Static guard against copied component implementation. |
| `scripts/assert_cli.py` | Executable-level CLI output and exit-status check. |
| `scripts/package.py` | Source archive creation. |
| `pipeline.toml` | Shared local/CI task graph. |
| `psx.yml` | Repository structure rules. |
| `.gix/config` | Branch-flow configuration. |
| `tests/e2e/` | Executable and product E2E scope, including gaps. |
| `tests/bench/` | Resource and soak benchmark plan. |
| `docs/` | Architecture, user and contributor documentation. |

Pinned component source trees are materialized under `.deps/src/`; installed build dependencies are under `.deps/install/`. Both are generated and ignored. They are not copied into `src/`.

## 2. Prerequisites

The native stack needs a C11 compiler and linker, CMake 3.22 or newer, Make, Git, `pkg-config`, PUC Lua 5.4 development files, Python 3.11 or newer and Go 1.25 or newer for the repository tools.

### GNU/Linux

On Debian or Ubuntu:

```sh
sudo apt-get update
sudo apt-get install build-essential cmake git make pkg-config \
  liblua5.4-dev python3 python3-pip
```

### macOS

Install Xcode Command Line Tools, Homebrew and the build dependencies:

```sh
xcode-select --install
brew install cmake make pkg-config lua@5.4
export PATH="$(brew --prefix lua@5.4)/bin:$PATH"
export PKG_CONFIG_PATH="$(brew --prefix lua@5.4)/lib/pkgconfig:$PKG_CONFIG_PATH"
```

### Windows

Use the MSYS2 **UCRT64** environment. Install the MinGW-w64 toolchain, CMake, Make, Git, pkgconf, Lua 5.4, Python, Python pip and Go packages from the UCRT64 repository:

```sh
pacman -S --needed base-devel git mingw-w64-ucrt-x86_64-toolchain \
  mingw-w64-ucrt-x86_64-cmake mingw-w64-ucrt-x86_64-pkgconf \
  mingw-w64-ucrt-x86_64-lua mingw-w64-ucrt-x86_64-python \
  mingw-w64-ucrt-x86_64-python-pip mingw-w64-ucrt-x86_64-go
```

Run the build commands from that environment so compiler, Python, Go and pkg-config resolve to the same toolchain. MSVC is not currently a verified build target.

## 3. Build and test the pinned stack

From the repository root:

```sh
make stack
```

The stack builder checks out the revisions in `deps.lock` and runs the component build in dependency order:

1. Build and install `m-mdy-m/log.c`.
2. Build, test and install Kernel.
3. Build, test and install Backend, including its Kernel integration tests.
4. Build and test Frontend Core, Headless and the experimental TUI target.
5. Configure, build and test the CDIN executable.
6. Install CDIN and run the installed `cdin --check` smoke test.

The command can take substantially longer than a normal single-project build because it builds the pinned components from source. It is the reproducible integration path for this repository; it is not a prebuilt production package manager.

To materialize the immutable source pins without building:

```sh
python3 scripts/deps.py
```

The checked-out revision is detached at the SHA recorded in `deps.lock`. Do not edit files inside `.deps/src/` as part of a CDIN change.

## 4. Local task graph

Install the pinned developer tools:

```sh
python3 -m pip install \
  "git+https://github.com/m-mdy-m/pipeline.git@79169afc4f9f74ee46c52be2bf6974f8544c7db1"

go install github.com/m-mdy-m/psx/cmd/psx@e4f12e85725e1ebd44c7f3a4e18fcbaa893b30df
go install github.com/m-mdy-m/gix/cmd/gix@9f0867923177cef3cd36d980cc2b356a35bee507
```

Then run:

```sh
psx check
gix doctor
pipeline run check
```

Pipeline is the standard local/CI entry point. Its tasks are declared in `pipeline.toml`; GitHub Actions should set up the native toolchain and invoke Pipeline rather than implement a second build graph.

For a faster iteration after all components are installed, use CMake directly:

```sh
cmake -S . -B build/standalone \
  -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_INSTALL_PREFIX="$PWD/.deps/install" \
  -DCDIN_RUNTIME_SOURCE_DIR="$PWD/.deps/src/runtime"
cmake --build build/standalone --parallel
ctest --test-dir build/standalone --output-on-failure
```

This does not rebuild or retest the pinned component repositories. Use `make stack` or `pipeline run check` before treating a change as integration-verified.

## 5. What the tests cover

The current CDIN executable-level tests cover help and version output, rejection of unknown CLI options, and Backend/Runtime create/start/pump/shutdown/destroy through the public Backend API.

The pinned component stack additionally runs the test suites owned by Kernel, Backend and Frontend repositories. Backend owns the live Kernel document integration scenarios.

This does not yet cover the user's full editor workflow through a connected Frontend. The missing product path is create/open/edit/save/reopen through the actual Runtime, Backend, Kernel and Frontend. See [E2E verification](../tests/e2e/README.md).

## 6. Sanitizers and resource testing

The CI workflow has an Ubuntu full-stack ASan/UBSan job with leak detection. It must complete successfully before the sanitizer gate can be reported as passing.

A CDIN process memory benchmark and long-running soak test are not implemented yet. The requirements and fields to record are listed in [Resource and soak benchmarks](../tests/bench/README.md). Do not treat queue capacity or a successful lifecycle smoke test as memory measurement.

## 7. Changing a dependency pin

Before updating `deps.lock`:

1. Inspect the component's public headers, package metadata, tests and release notes.
2. Check the relevant accepted Spec and ADR requirements.
3. Select a specific commit SHA or immutable release.
4. Confirm the package version, ABI and Protocol versions from actual source.
5. Build the complete pinned stack and run the dependent integration tests.
6. Update the dependency matrix and traceability notes in the same change.

Do not use a floating branch, assume a version from a repository name or silently keep an older package after a pin change.

## 8. C code and resource ownership

New native code uses C11 and the warning set in the root CMake configuration: `-Wall -Wextra -Wshadow -Wconversion -Wstrict-prototypes -Wformat=2 -Wpedantic -Werror` (or the MSVC equivalent).

Keep Composition Root code small. A resource created by CDIN must have one cleanup path. Preserve the logger callback's context until Backend has been destroyed. Do not add document, session, queue or rendering state here.

## 9. Git and pull requests

The active branch is `feature/complete-composition-root-rewrite`. Use Gix according to `.gix/config`. Keep commits focused and descriptive. Do not force-push or merge the PR without explicit authorization.

Before submitting a change, record the actual commands run and their results. List unavailable platform checks, benchmarks and workflows as `NOT RUN`, with a reason.
