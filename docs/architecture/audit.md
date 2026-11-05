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
| Dependency source materialization | **IMPLEMENTED and VERIFIED in CI** | Linux, macOS and Windows reached the pinned component build using the immutable revisions in `deps.lock`; Windows later failed in a Backend-owned E2E test. |
| Full stack build orchestration | **IMPLEMENTED; Linux/macOS VERIFIED; Windows PARTIAL** | `scripts/build_stack.py` builds and tests logger, Kernel, Backend, Frontend and CDIN. Linux and macOS pass; Windows stops at `backend_e2e_platform_file_workflow`. |
| Protocol compatibility | **PARTIAL** | Backend/Frontend Protocol major/minor are checked at compile time; `--check` performs Frontend Core HELLO/HELLO_ACK over an in-process byte transport. |
| Backend version compatibility | **PARTIAL** | The executable compares `cdin_backend_version()` to the header version at startup. |
| Kernel document integration | **EXISTS in Backend; not a CDIN product workflow** | Backend integration tests are built by the pinned stack. CDIN does not directly call the Kernel API. |
| Runtime hosting | **IMPLEMENTED for lifecycle smoke test** | CDIN supplies Runtime root and entry to Backend; Backend creates and owns the Lua state and Host bridge. |
| Frontend Core handshake | **IMPLEMENTED for headless smoke** | CDIN creates a Frontend Core client/session, sends HELLO and validates HELLO_ACK. View attachment and a user-facing adapter are not connected. |
| Interactive TUI/GUI launch | **NOT IMPLEMENTED** | Launcher fails closed pending the FE-019 readiness/wakeup event-loop integration. |
| Document create/open/edit/save/reopen product E2E | **NOT IMPLEMENTED** | There is no connected live Frontend product path. |
| Runtime command/keymap/plugin E2E | **NOT VERIFIED** | CDIN has no live Frontend input route exercising these Runtime features. |
| Linux/macOS/Windows green CI | **PARTIAL** | Linux and macOS pass. Windows reaches Backend tests but one path workflow fails; see section 5. |
| ASan/UBSan/leak result | **PASS on Linux for the inspected HEAD** | The ASan + UBSan + leak-detection job completed successfully in run `41991189690`. |
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

## 5. CI evidence for the current HEAD

The CI-tested implementation baseline (before the audit-only documentation commits) was `c7b50b87034968a083c6fa2d52bee05babdea337`. Workflow run [41991189690](https://github.com/cdin-editor/cdin/actions/runs/41991189690) completed on 2026-11-05:

| Job | Result | Evidence |
| --- | --- | --- |
| Ubuntu pinned stack | **PASS** | Dependencies, component builds/tests, CDIN build, CLI E2E, lifecycle smoke and boundary check completed. |
| macOS pinned stack | **PASS** | Same Pipeline task graph completed. |
| Linux ASan + UBSan + leak detection | **PASS** | Instrumented `pipeline run check` completed successfully. |
| Windows pinned stack | **FAIL** | Backend built, but 8/9 Backend CTest cases passed. `backend_e2e_platform_file_workflow` failed at `tests/e2e/scenarios/platform_file_workflow.c:56`, comparing the result of `cdin_path_join` with the scenario helper's path string. The failure is in the Backend-owned test and must be fixed in the Backend repository, not by duplicating Backend path logic in CDIN. |
| CodeQL Python | **PASS** | Python analysis completed. |
| CodeQL JavaScript/TypeScript | **CONFIGURATION FAILURE** | CodeQL found no JavaScript/TypeScript source in this repository and could not finalize that language database. This is not evidence of a source vulnerability; the language selection needs to match the repository's languages. |

The passing Linux and macOS jobs verify the pinned component stack, CLI/lifecycle smoke and (on the current head) Frontend Core HELLO/HELLO_ACK handshake. They do **not** verify view attachment, UI snapshot delivery, rendering, document editing, persistence, keymap dispatch or plugin workflows. The sanitizer pass likewise covers the configured stack checks, not the missing interactive product path.

The CI log also reports Runtime startup with Host API `1.0.0` and Kernel ABI `1.1.0`, but the Runtime self-reported version is `0.2.1-beta.10.next.17+gc7b50b8`. This conflicts with the Spec status page and Runtime status document, which identify the package candidate as `1.0.0-rc.1`. Resolve the version-source discrepancy before publishing a component version matrix or release.

Historical runs `41985097875` and `41987494172` record earlier dependency checkout, toolchain and package-version failures. They are superseded as evidence for the current HEAD by run `41991189690`; retain them only as history, not as the current CI status.

## 6. Main gaps before an interactive release

1. Resolve why Backend initial Runtime UI snapshot publication returns `CDIN_BACKEND_LIMIT_EXCEEDED`; verify ATTACH, UI snapshot/flush/ACK and resize.
2. Publish an installable Frontend TUI adapter package/target, or choose another supported adapter.
3. Connect Backend worker-completion wakeup to the Frontend readiness-driven event loop.
3. Add a real product E2E that creates or opens a document, edits it, saves it, reopens it and compares exact bytes.
4. Verify keymaps, commands, plugin loading, capability denial and unload through real frontend input.
5. Add multi-frontend, disconnect/reconnect and failure-recovery workflows.
6. Add measured process RSS, allocator peak where available, leak, soak and latency benchmarks.
7. Produce and verify platform-specific application installers and release workflows.
8. Complete the native CI matrix and sanitizer run on the updated branch.

Until these gates pass, the accurate project description is “Composition Root with a headless Backend/Runtime lifecycle smoke test,” not “complete editor.”

## 7. Cross-source discrepancies found during this audit

1. **Frontend Protocol version documentation is internally stale.** The pinned Backend public header declares Backend `1.0.0` and Protocol `1.0.0` at [backend.h](https://github.com/cdin-editor/backend/blob/322a3e95e669541e63f5a5c10a16b76823c45200/include/cdin/backend.h#L11-L19). However, the Spec's [frontend-protocol.md](https://github.com/cdin-editor/spec/blob/main/docs/architecture/frontend-protocol.md#L3-L3) still says the Backend implementation is `0.2.0`, and [module-boundaries.md](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L19-L19) repeats that stale value. The accepted ADR-0020 and Spec v1.4.0 status page identify Protocol `1.0.0`; synchronize the descriptive pages.
2. **The Spec Frontend overview has stale decision text.** [components/frontend.md](https://github.com/cdin-editor/spec/blob/main/docs/components/frontend.md#L3-L3) says serialized wire encoding and a shared protocol client remain open, while accepted ADR-0018/ADR-0020 and the pinned Frontend repository provide the Protocol 1.0.0 wire contract and client API. Update the component overview without changing accepted decisions.
3. **Runtime package version does not match its documented candidate.** Spec status [line 27](https://github.com/cdin-editor/spec/blob/main/docs/reference/status.md#L27-L27) and Runtime status [line 3](https://github.com/cdin-editor/runtime/blob/fda2db69d8e0ab90c854c3a74efa1dd80d9714cc/docs/status.md#L3-L3) say `1.0.0-rc.1`; the current CDIN CI log reports `0.2.1-beta.10.next.17+gc7b50b8`. Runtime derives its package version from Git metadata in [version.lua](https://github.com/cdin-editor/runtime/blob/fda2db69d8e0ab90c854c3a74efa1dd80d9714cc/lua/cdin/runtime/core/version.lua#L159-L159). Confirm the intended release identity and ensure the packaged Runtime metadata is deterministic.
4. **Backend package discovery is weaker than the lock contract.** CDIN pins Backend commit/version but CMake finds Backend headers and libraries by unversioned names; only a runtime version string is compared. Add a versioned package/config or another explicit public ABI contract before treating the installed Backend as a reproducible production package.
5. **The readiness gap is at composition time.** The pinned Frontend TUI exposes a readiness-driven event-loop callback contract, but CDIN does not supply the wait/readiness bridge or connect a Frontend session. Backend exposes in-process Frontend queue/codec APIs, while its own readiness audit says concrete out-of-process transports are not implemented. Do not treat the presence of the TUI event-loop header or a successful Backend lifecycle smoke test as a connected frontend.

These discrepancies are findings, not accepted design changes. Component-owned issues must be corrected in their owning repositories; CDIN must consume the corrected released interfaces rather than copy their implementations.
