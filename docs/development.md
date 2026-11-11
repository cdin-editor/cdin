# Developer guide

This guide is for contributors changing the Composition Root. It covers the repository layout, Registry handoff, build loop, test evidence and component release metadata.

The [Architecture](architecture.md) document describes ownership and runtime behavior. The [User guide](user-guide.md) describes the CLI from a user's point of view.

## 1. Repository layout

| Path | Responsibility |
| --- | --- |
| `AGENTS.md` | Mandatory architecture and engineering rules. |
| `deps.lock` | Immutable non-component dependencies and build-tool revisions; component versions are selected by Registry. |
| `CMakeLists.txt` | Composition Root executable, package discovery and installation rules. |
| `src/main.c` | CLI dispatch and Backend lifecycle composition. |
| `src/cli/` | Small launcher argument parser. |
| `src/diagnostics/` | CDIN logger adapter and Backend log callback. |
| `include/cdin/` | Private headers shared by launcher modules. |
| `scripts/deps.py` | Download, validate and atomically install the pinned Kernel 1.2.1 + logger 0.1.0 SDK Release package. |
| `scripts/registry.py` | Acquire the pinned Registry Release binary/Catalog by default; validate, resolve, prepare, verify and replay the component workspace. Its explicit `--source-build` switch is for Registry development only. |
| `scripts/registry_version.py` | Read package versions from the Resolved Manifest for CMake package checks. |
| `scripts/build_stack.py` | Build/test/install orchestration using Registry-collected component sources. |
| `scripts/check_boundaries.py` | Source-boundary guard plus architecture unit tests and compiler-resolved include audit. |
| `scripts/check_include_graph.py` | Trace compiler-resolved headers from `compile_commands.json`; reject private component source/build headers. |
| `src/integration/gui_sdl.c` | CDIN-owned Backend/Frontend Protocol transport and GUI-SDL process lifecycle composition. |
| `scripts/tui_pty_smoke.py` | Exercise the experimental POSIX TUI through a real pseudo-terminal. |
| `scripts/assert_cli.py` | Executable-level CLI output and exit-status check. |
| `scripts/package.py` | Source archive creation. |
| `pipeline.toml` | Shared local/CI task graph. |
| `psx.yml` | Repository structure rules. |
| `.gix/config` | Branch-flow configuration. |
| `tests/e2e/` | Executable and product E2E scope, including gaps. |
| `tests/bench/` | Resource and soak benchmark plan. |
| `docs/` | Architecture, user and contributor documentation. |

Registry prepares immutable component source units under `.deps/registry-workspace-<profile>/`. A private build staging copy is materialized under `.deps/src/`; installed build dependencies are under `.deps/install/`. All are generated and ignored. They are not copied into `src/`.

## 2. Prerequisites

The current hybrid development stack needs a C11 compiler and linker, CMake 3.22 or newer, Make, Git, `pkg-config`, PUC Lua 5.4 development files and Python 3.11 or newer. The normal Registry bootstrap uses its pinned prebuilt Release executable and does not need a local Go toolchain. Go 1.27.3 or newer is needed only for the explicit Registry source-build path (`make registry-dev`, `make stack-dev`, or `make stack-gui-dev`).

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
  mingw-w64-ucrt-x86_64-lua54 mingw-w64-ucrt-x86_64-python \
  mingw-w64-ucrt-x86_64-python-pip
```

Use the `lua54` package rather than the unversioned `lua` package. The CI build selects `/ucrt64/include/lua5.4` and `/ucrt64/lib/liblua5.4.dll.a` explicitly so Lua 5.5 cannot be selected accidentally. The normal Registry binary bootstrap does not require Go. Install the UCRT64 Go package only when using the explicit Registry source-build targets. MSVC is not currently a verified build target.

## 3. Resolve, build and test the component stack

From the repository root:

```sh
make stack
```

The current stack is a **hybrid artifact/source integration candidate**, not yet a complete artifact-first consumer installation:

1. \`make deps\` downloads, verifies and safely installs the existing Kernel 1.2.1 Release package, which also contains the pinned \`m-mdy-m/log.c\` 0.1.0 SDK. The installed Kernel version and ABI are checked against the Registry Manifest before either SDK is staged into CDIN's private prefix. Kernel and logger are not cloned or compiled from source.
2. Backend 1.2.1 is selected as a native \`cmake-prefix-v1\` artifact by Registry for the detected target. CDIN verifies the selected target, package identity and required CMake/pkg-config files, then stages it into the same private prefix without overwriting Kernel/logger files.
3. Registry still resolves the component graph and collects source units for Runtime and Frontend because their current Catalog identities do not yet provide the required module/variant artifacts. These source units are kept in the immutable Manifest/workspace and staged only for the current development build.
4. GUI-SDL currently builds the checksum-pinned SDL3 3.4.16 source archive. The SDK publisher is merged, but the actual five-target SDK Release and its digests are not yet available. TUI does not build or stage SDL3.
5. CDIN configures and builds the Composition Root against the staged Kernel/logger and Backend packages, the source-delivered Runtime/Frontend development trees, and (for GUI-SDL only) SDL3. Registry replay and product E2E assertions run before the Composition Root is built.

**Registry release blocker:** the normal consumer Registry pin is deliberately missing the descriptor SHA-256/size because the corrected \`v0.2.0-dev.1\` Release has not been published. The old \`v0.1.0-dev\` target binaries are unsafe. Consequently \`make registry\`, \`make stack\` and \`make install\` fail closed at Registry acquisition until a real verified Release is available. They do not silently switch to the source path.

The explicit contributor/CI source mode is separate:

\`\`\`sh
make registry-dev
make stack-dev
make registry-gui-dev
make stack-gui-dev
\`\`\`

Those targets use the separately pinned Registry development commit, compile/test Registry from source, and run the current hybrid component integration. Pipeline's CI task graph passes the explicit source-build option for that reason. It is not evidence that ordinary consumer installation is ready.

The broader artifact-first migration remains open in CDIN #122. Runtime's platform-neutral module archive, Frontend's Core/TUI/GUI-SDL package set, SDL3's five-target SDK Release, and the corrected Registry executable/Catalog Release must be published and pinned before the normal product install can become source-free.

The Product Definition and Resolved Manifest, not `deps.lock`, are authoritative for component versions and source revisions. `deps.lock` retains non-component dependency pins and the exact Registry Release pin. See [Registry integration](development/registry.md).

To prepare a Registry workspace without compiling the stack:

```sh
make deps
make registry
```

Choose the Frontend variant with:

```sh
CDIN_FRONTEND_VARIANT=tui make registry
CDIN_FRONTEND_VARIANT=gui-sdl make registry
make stack-gui
```

On Windows PowerShell, the same Makefile entry point selects `python`. When your Python installation is exposed only through the Python launcher, use `make PYTHON="py -3" install`.

Registry source builds honor `CDIN_GOPROXY`. The default is `https://proxy.golang.org,direct`, so a broken inherited `GOPROXY` setting such as an unreliable third-party mirror does not silently break the pinned Go toolchain download. The normal binary bootstrap does not invoke Go. For a private mirror used by the developer source-build path, set `CDIN_GOPROXY` explicitly.

Registry refuses to overwrite an existing workspace or replay destination. Remove the generated `.deps/registry-workspace-<profile>` and `.deps/registry-replay-<profile>` directories (or use `make clean`) before preparing the same profile again.

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

For a release candidate, use `pipeline run pre-release`. This task depends on the complete `check` graph and reproducible `package` task, verifies the Registry Resolved Manifest and source archive checksum, and writes `dist/cdin-pre-release.json`. The GitHub pre-release workflow runs the same verification graph for `v*-rc*` tags. Its current source-only artifact is not an application installer.

Pipeline is the standard local/CI entry point. Its tasks are declared in `pipeline.toml`; GitHub Actions should set up the native toolchain and invoke Pipeline rather than implement a second build graph.

For a faster iteration after all components are installed, use CMake directly:

```sh
cmake -S . -B build/standalone \
  -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_INSTALL_PREFIX="$PWD/.deps/install" \
  -DCDIN_RUNTIME_SOURCE_DIR="$PWD/.deps/src/runtime" \
  -DCDIN_REGISTRY_PROFILE=tui \
  -DCDIN_BACKEND_PACKAGE_VERSION="$(python3 scripts/registry_version.py backend)" \
  -DCDIN_FRONTEND_PACKAGE_VERSION="$(python3 scripts/registry_version.py frontend --variant tui)" \
  -DCDIN_ENABLE_GUI_SDL=OFF
cmake --build build/standalone --parallel
ctest --test-dir build/standalone --output-on-failure
```

This does not rebuild or retest the pinned component repositories. Use `make stack` or `pipeline run check` before treating a change as integration-verified.

## 5. What the tests cover

The root CTest suite checks CLI help/version, invalid/missing values and fail-closed modes. The headless integration test uses the public Frontend session API to negotiate, attach, verify the initial snapshot/flush/ACK and resize, then create/edit/paste/undo/redo/save/close/open and compare exact bytes through the real Backend/Runtime/Kernel stack. The TUI Product Definition runs the headless and POSIX TUI/PTY coverage without SDL. The GUI-SDL Product Definition resolves the TUI base plus GUI-SDL adapter and runs `cdin_gui_sdl_live_session_smoke` with SDL dummy video, deterministic text input, Runtime Ctrl+S and exact-byte save.

The file-fixture smoke covers NUL, invalid UTF-8, BOM, LF-only and mixed CRLF/LF/CR data. The filesystem-failure smoke covers missing-file read, failed atomic save, preservation of in-memory bytes and successful recovery.

The TUI PTY smoke exercises the opt-in experimental TUI, rendered input, signal/resize handling and terminal restoration. Both product profiles run in the six-way Linux/macOS/Windows matrix; the sanitizer job runs the GUI-SDL superset profile, including the TUI fallback. The current Registry-enabled head's CI is pending, so these tests are not marked PASS until the complete matrix finishes successfully.

See [E2E verification](../tests/e2e/README.md) for per-platform evidence and remaining scenarios.

## 6. Sanitizers and resource testing

The CI workflow has an Ubuntu full-stack ASan/UBSan job with leak detection. In the latest fully completed CDIN candidate run inspected, this job failed on the same live TUI PTY acceptance test as the Linux native job. Do not call the current sanitizer gate green; rerun after the Frontend request-lifecycle fix is merged and pinned.

A CDIN process memory benchmark and long-running soak test are not implemented. The real headless document workflow is integration coverage, not a performance measurement. See [Resource and soak benchmarks](../tests/bench/README.md). Do not treat queue capacity or a short smoke as memory measurement.

## 7. Publishing or selecting a component release

Component maintainers own their `registry/releases/*.json` documents. A release metadata document must declare the stable component/variant identity, SemVer package version, dependencies, contract declarations and full immutable source commit. Publish metadata at an immutable URL and calculate SHA-256 over the exact bytes.

The Catalog Index publisher adds an entry with the metadata URI and digest. CDIN changes its Product Definition or Catalog Index input only after checking the component release and its compatibility evidence. Never add a component source revision to `deps.lock` or let CDIN independently discover a release.

After a selection change:

1. Validate the Product Definition and Catalog Index with the pinned Registry.
2. Run resolve, prepare, manifest verify and replay.
3. Build and test the complete product from the prepared workspace.
4. Update the dependency matrix, Registry documentation and traceability evidence.
5. Keep old Manifests immutable for reproducibility.

Do not use a floating branch, invent a package version or update a published metadata document in place.

## 8. C code and resource ownership

New native code uses C11 and the warning set in the root CMake configuration: `-Wall -Wextra -Wshadow -Wconversion -Wstrict-prototypes -Wformat=2 -Wpedantic -Werror` (or the MSVC equivalent).

Keep Composition Root code small. A resource created by CDIN must have one cleanup path. Preserve the logger callback's context until Backend has been destroyed. Do not add document, session, queue or rendering state here. Use the compiler-resolved include audit alongside source-level boundary checks; neither replaces component ownership review.

## 9. Git and pull requests

The active branch is `feature/complete-composition-root-rewrite`. Use Gix according to `.gix/config`. Keep commits focused and descriptive. Do not force-push or merge the PR without explicit authorization.

Before submitting a change, record the actual commands run and their results. List unavailable platform checks, benchmarks and workflows as `NOT RUN`, with a reason.
