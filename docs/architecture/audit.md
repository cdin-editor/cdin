# Architecture audit

**Audit baseline:** CDIN branch `feature/complete-composition-root-rewrite`, component revisions recorded in `deps.lock`, and the Spec revision inspected on 2026-11-05.

This audit separates source that exists from behavior that has actually been exercised. It is not a claim that the complete editor is implemented.

## 1. Target architecture

CDIN is the composition root. Kernel, Runtime, Backend and Frontend remain separately maintained components with independent responsibilities. CDIN owns their pins, build and package orchestration, launcher and process lifecycle. The normative starting points are [ARCH-001](https://github.com/cdin-editor/spec/blob/main/docs/architecture/overview.md#L113-L113), [ARCH-040–046](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L65-L71) and [ROOT-001](https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md#L22-L22).

## 2. Current repository inventory

| Area | Current files | Finding |
| --- | --- | --- |
| Launcher | `src/main.c`, `src/cli/options.c` | Small Composition Root CLI and Backend lifecycle path. |
| Diagnostics | `src/diagnostics/log.c`, `include/cdin/log.h` | CDIN logger setup and Backend callback adapter using the pinned logger. |
| Launcher headers | `include/cdin/options.h` | Internal option contract; not a component API. |
| Build | `CMakeLists.txt`, `Makefile` | Builds the application against installed component interfaces and exposes stack tasks. |
| Dependencies | `deps.lock`, `scripts/deps.py` | Immutable source revisions; dependency materialization is performed by the stack task. |
| Orchestration | `scripts/build_stack.py`, `pipeline.toml` | Build, test and install the pinned stack; Pipeline is the local/CI task graph. |
| Static boundaries | `scripts/check_boundaries.py`, `psx.yml` | Mechanical checks against copied implementation and repository layout. |
| CLI E2E | `scripts/assert_cli.py`, root CTest entries | Verifies CLI output/exit codes and the Backend/Runtime lifecycle. |
| Product E2E | `tests/e2e/README.md` | Scope is documented; full live edit/save E2E is not implemented. |
| Benchmarks | `tests/bench/README.md` | Measurement plan only; no product memory or soak benchmark is implemented. |
| Technical documentation | `docs/` | Architecture, development and status documents; website content is not part of CDIN. |
| Website | Separate repository | `website/` and the website deployment workflow are removed from this repository. |

The current top-level tree contains no legacy SDL renderer, embedded editor policy, website project, website assets or website deployment job.

## 3. Implementation status

| Capability | Status | Evidence and limitation |
| --- | --- | --- |
| Composition Root boundary | **IMPLEMENTED (partial product)** | Current native source is limited to launcher, CLI parsing and diagnostics. The full user-facing editor remains incomplete. |
| Immutable component source pins | **IMPLEMENTED** | Revisions are recorded in `deps.lock`. |
| Dependency source materialization | **IMPLEMENTED in the current change; NOT VERIFIED by CI yet** | `scripts/deps.py` explicitly checks out the locked SHA after clone/fetch. |
| Full stack build orchestration | **IMPLEMENTED; current CI fix NOT VERIFIED** | `scripts/build_stack.py` drives logger, Kernel, Backend, Frontend and CDIN builds and tests. |
| Protocol compatibility | **PARTIAL** | Backend/Frontend Protocol major/minor are checked at compile time. No live protocol transport connection is created by CDIN. |
| Backend version compatibility | **PARTIAL** | The executable compares `cdin_backend_version()` to the header version at startup. |
| Kernel document integration | **EXISTS in Backend; not a CDIN product workflow** | Backend integration tests are built by the pinned stack. CDIN does not directly call the Kernel API. |
| Runtime hosting | **IMPLEMENTED for lifecycle smoke test** | CDIN supplies Runtime root and entry to Backend; Backend creates and owns the Lua state and Host bridge. |
| Live Frontend connection | **NOT IMPLEMENTED** | CDIN does not create a Frontend client or attach TUI/GUI to Backend. |
| Interactive TUI/GUI launch | **NOT IMPLEMENTED** | Launcher fails closed pending the FE-019 readiness/wakeup event-loop integration. |
| Document create/open/edit/save/reopen product E2E | **NOT IMPLEMENTED** | There is no connected live Frontend product path. |
| Runtime command/keymap/plugin E2E | **NOT VERIFIED** | CDIN has no live Frontend input route exercising these Runtime features. |
| Linux/macOS/Windows green CI | **NOT VERIFIED** | The inspected CI run failed before compilation; see section 5. |
| ASan/UBSan/leak result | **NOT VERIFIED** | The inspected sanitizer job failed before compilation. |
| Product memory/soak benchmarks | **NOT IMPLEMENTED / NOT RUN** | The current benchmark document is a plan, not a benchmark executable. |
| Production installers and release artifacts | **NOT IMPLEMENTED** | The package task currently creates a source archive only. |
| Docker image | **NOT IMPLEMENTED** | No Dockerfile or container workflow exists in the current tree. |

## 4. Compatibility and ownership findings

- Backend owns the Kernel integration and Runtime host. CDIN calls Backend's public lifecycle API.
- CDIN links the Kernel package as part of the static link closure. The root source does not include Kernel headers or invoke Kernel functions; Backend remains the component that owns the Kernel integration.
- Runtime is a pinned Lua module tree. CDIN installs the tree and passes its root and entry name to Backend.
- Frontend Core is a pinned package and Protocol version constants are compared with Backend at compile time. This is not equivalent to starting a Frontend adapter.
- Logger is built from an immutable revision and used by CDIN diagnostics. Backend records are relayed through a callback and mapped to the logger's severity enum.

Potential compatibility improvement still needed: the lock file records the Backend commit and version, but CMake currently discovers the installed Backend headers/libraries by name rather than through a versioned Backend package config. The runtime version comparison catches a mismatch at startup, but dependency discovery should become a package-level contract.

## 5. CI evidence at the audit baseline

Workflow run [41985097875](https://github.com/cdin-editor/cdin/actions/runs/41985097875) failed on all four jobs before the actual CDIN build:

- Linux and macOS: the dependency script cloned source repositories with `--no-checkout` and could leave their working trees empty even when `HEAD` matched the pin.
- Windows: the MSYS2 Python package was installed without its pip package, so Pipeline could not be installed.
- macOS/Linux Gix diagnostics also found a detached HEAD/no configured local mainline identity/base branch during the original workflow. The workflow now prepares the expected branch and commit identity before Gix checks.

The dependency materialization script, CI environment and Gix configuration have been corrected in the current working tree. These corrections remain **NOT VERIFIED** until a new workflow run completes.

## 6. Main gaps before an interactive release

1. Implement and verify Backend readiness/wakeup integration with the Frontend event loop.
2. Start and attach the TUI through the public Frontend Core/Protocol boundary.
3. Add a real product E2E that creates or opens a document, edits it, saves it, reopens it and compares exact bytes.
4. Verify keymaps, commands, plugin loading, capability denial and unload through real frontend input.
5. Add multi-frontend, disconnect/reconnect and failure-recovery workflows.
6. Add measured process RSS, allocator peak where available, leak, soak and latency benchmarks.
7. Produce and verify platform-specific application installers and release workflows.
8. Complete the native CI matrix and sanitizer run on the updated branch.

Until these gates pass, the accurate project description is “Composition Root with a headless Backend/Runtime lifecycle smoke test,” not “complete editor.”
