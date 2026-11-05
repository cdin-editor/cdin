# Integration status and release gates

This document reports what the current CDIN branch actually connects. A component feature or configured CI job is not automatically a verified CDIN product feature.

## 1. Implemented behavior

| Area | Status | Evidence |
| --- | --- | --- |
| Composition Root CLI | IMPLEMENTED | Help/version/check, Runtime root/entry and frontend options are parsed; unsupported frontends and interactive launch fail closed. |
| Component pinning | IMPLEMENTED | `deps.lock` records immutable source revisions. |
| Stack orchestration | IMPLEMENTED | `scripts/build_stack.py` builds, tests and installs the pinned component stack in dependency order. |
| Runtime module installation | IMPLEMENTED | CMake installs the pinned Lua module tree under `share/cdin/lua`. |
| Runtime version identity | VERIFIED | The stack smoke compares the Runtime-reported version with the version in `deps.lock`; run 42015347702 logged Runtime `1.0.0-rc.1`, matching the lock. |
| Backend lifecycle | IMPLEMENTED for smoke test | CDIN calls Backend create/start/pump/shutdown/destroy. |
| Backend package contract | IMPLEMENTED | Backend 1.0.0 exports versioned `cdinBackend` CMake package targets; CDIN consumes them with `find_package(cdinBackend 1.0.0 CONFIG REQUIRED)`. |
| Backend/Frontend protocol compatibility | PARTIAL | Protocol major/minor header constants are compared at compile time; `--check` sends Frontend Core HELLO through an in-process byte transport and validates Backend HELLO_ACK. |
| Shared logging | IMPLEMENTED for CDIN and Backend callbacks | CDIN owns a logger instance and routes Backend log callbacks into it. |
| CLI fail-closed tests | IMPLEMENTED; new cases await CI | CTest covers missing option values, unsupported frontend selection and attempts to launch without `--check`. |
| Source snapshot | IMPLEMENTED as a review artifact | `scripts/package.py` builds a sorted, fixed-metadata ZIP, rejects symlinks, verifies archive paths/CRCs, checks two builds match and writes a SHA-256 sidecar. |
| CI platform coverage | VERIFIED on preceding PR head | Run 42015347702 passed Linux, macOS, Windows and Linux ASan/UBSan/leak checks. The new action pins and reproducible archive changes require a fresh run on the updated head. |
| Explicit CodeQL | VERIFIED on preceding PR head | Run 42015347819 passed traced C/C++ analysis and Python analysis. The action-major/SHA update requires a fresh run. |

## 2. Not complete

| Area | Status | Missing work |
| --- | --- | --- |
| Interactive TUI | NOT IMPLEMENTED | Frontend TUI adapter is not exported as an installable supported target; initial UI snapshot publication previously returned `CDIN_BACKEND_LIMIT_EXCEEDED`; Backend wakeup and FE-019 event-loop integration remain. |
| GUI-SDL | NOT IMPLEMENTED in CDIN | GUI adapter is not launched by the current Composition Root. |
| View attachment and UI state | NOT VERIFIED | HELLO/HELLO_ACK is tested, but ATTACH, initial UI snapshot publication, UI flush/ACK and resize have not passed through CDIN. |
| Real editing workflow | NOT IMPLEMENTED | Create/open/edit/save/close/reopen through real Runtime, Backend, Kernel and Frontend interfaces. |
| Keymaps and commands through input | NOT VERIFIED | Feed real Frontend input into Backend and verify Runtime dispatch. |
| Plugin lifecycle and isolation | NOT VERIFIED from CDIN | Exercise plugin load, capability denial, failure isolation and unload in a live session. |
| Multi-frontend attach/detach | NOT VERIFIED from CDIN | Exercise driver/observer roles, detach and reconnect. |
| Product memory and soak measurements | NOT IMPLEMENTED | Measure RSS, allocator peak, leaks, long-running sessions and latency. |
| Application installers | NOT IMPLEMENTED | Current package task creates a source snapshot only; it is not a runnable application installer. |
| Docker image | NOT IMPLEMENTED | No verified runtime image is built or published. |
| Stable application release | NOT READY | Interactive product path and release gates below remain open. |

## 3. CI and security evidence

### Explicit workflows

- [CI run 42015347702](https://github.com/cdin-editor/cdin/actions/runs/42015347702) passed on PR head `b1a0a4af6e976996aaaba05182efbfdc0403c75e`:
  - Ubuntu pinned stack + E2E: PASS.
  - macOS pinned stack + E2E: PASS.
  - Windows pinned stack + E2E: PASS.
  - Linux ASan + UBSan + leak detection: PASS.
  - Source-snapshot ZIP validation and artifact upload: PASS on all three native platforms.
- [CodeQL run 42015347819](https://github.com/cdin-editor/cdin/actions/runs/42015347819) passed both C/C++ traced-build analysis and Python analysis.
- These runs predate the current continuation commit. The latest action-pin, archive reproducibility and extra CLI test changes must pass a new run before they are considered verified.

The passing stack jobs include a Frontend Core HELLO/HELLO_ACK protocol smoke over an in-process transport, component tests, CLI checks and Backend/Runtime startup/shutdown. They do **not** prove view attachment, UI snapshot delivery, rendering, document editing, save/reopen, input dispatch or plugin behavior.

### GitHub Default Setup CodeQL

The separate GitHub-managed dynamic workflow [42015339040](https://github.com/cdin-editor/cdin/actions/runs/42015339040) passed Python but failed its JavaScript/TypeScript job. Its log says CodeQL found only empty or syntactically invalid JavaScript/TypeScript files (the repository has no JS/TS source) and then reported that it could not process any JS/TS code.

This dynamic workflow is configured by GitHub repository security settings, not by `.github/workflows/codeql.yml`. The repository-owned workflow adds successful C/C++ and Python analysis, but cannot disable the unrelated Default Setup language selection. Set Default Setup to the languages actually present (C/C++ and Python), or disable its unsupported JS/TS selection in GitHub settings.

### Action/runtime update

The preceding CI log emitted Node.js 20 deprecation warnings for the old Actions versions. The current change pins updated Node 24-compatible action releases by full commit SHA. The new versions and provenance step require fresh CI verification on the current PR head.

## 4. Compatibility findings

- Backend 1.0.0 package discovery is versioned; keep `find_package(cdinBackend 1.0.0 CONFIG REQUIRED)`.
- Runtime's version mismatch is **resolved for the pinned revision**: `build_stack.py` asserts that Backend's startup log reports the Runtime version from `deps.lock`; CI run 42015347702 confirmed `1.0.0-rc.1`.
- Initial UI snapshot publication previously returned `CDIN_BACKEND_LIMIT_EXCEEDED`; the headless handshake was intentionally kept narrow instead of increasing message limits or claiming snapshot coverage.
- Frontend TUI target remains experimental/unexported by Frontend Core 1.0.0. CDIN must consume a supported installable adapter, not copy its implementation.

## 5. Release gates

Before describing CDIN as an interactive editor:

1. Resolve Backend initial Runtime UI snapshot publication and verify ATTACH, UI flush/ACK and resize end-to-end.
2. Publish an installable Frontend TUI adapter package/target or select another supported adapter.
3. Connect Backend worker-completion wakeup to the Frontend event loop and implement the FE-019 readiness multiplexer.
4. Add product E2E for create/open/edit/save/close/reopen, with exact-byte comparisons for NUL, invalid UTF-8, BOM and line endings.
5. Verify Runtime command/keymap execution through real input.
6. Verify plugin loading, capability isolation, failure handling and unload.
7. Verify Frontend detach/reconnect, multi-frontend sessions and failure recovery.
8. Maintain native Linux/macOS/Windows CI, sanitizer evidence and C/C++/Python CodeQL on the latest commit.
9. Add measured process RSS, allocator peak where available, leak checks, soak workloads and latency measurements.
10. Produce reproducible platform packages/installers and signed release artifacts only after the interactive path is complete.

Unrun checks must be reported as NOT RUN, not PASS.
