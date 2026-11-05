# Integration status and release gates

This document reports what the current CDIN branch actually connects. A component feature or configured CI job is not automatically a verified CDIN product feature.

## 1. Implemented behavior

| Area | Status | Evidence |
| --- | --- | --- |
| Composition Root CLI | IMPLEMENTED | Help/version/check, Runtime root/entry and frontend options are parsed; unsupported frontends and interactive launch fail closed. |
| Component pinning | IMPLEMENTED | `deps.lock` records immutable source revisions. |
| Stack orchestration | IMPLEMENTED | `scripts/build_stack.py` builds, tests and installs the pinned component stack in dependency order. |
| Runtime module installation | IMPLEMENTED | CMake installs the pinned Lua module tree under `share/cdin/lua`. |
| Runtime version identity | VERIFIED | The stack smoke compares the Runtime-reported version with the version in `deps.lock`; CI log confirms Runtime `1.0.0-rc.1`. |
| Backend lifecycle | IMPLEMENTED for smoke test | CDIN calls Backend create/start/pump/shutdown/destroy. |
| Backend package contract | IMPLEMENTED | Backend 1.0.0 exports versioned `cdinBackend` CMake package targets; CDIN consumes them with `find_package(cdinBackend 1.0.0 CONFIG REQUIRED)`. |
| Backend/Frontend protocol compatibility | PARTIAL | Protocol major/minor header constants are compared at compile time; `--check` sends Frontend Core HELLO through an in-process byte transport and validates Backend HELLO_ACK. |
| Shared logging | IMPLEMENTED for CDIN and Backend callbacks | CDIN owns a logger instance and routes Backend log callbacks into it. |
| CLI fail-closed tests | PASS | Nine executable-level CDIN CTest cases pass on Linux, macOS and Windows, including missing values and gated launch paths. |
| Source snapshot | PASS | Deterministic ZIP, path/CRC validation, reproducibility comparison and SHA-256 verification pass on all three native platforms. |
| CI platform coverage | PASS | CI run 42023541244 passed Linux, macOS, Windows and Linux ASan/UBSan/leak detection on candidate commit `9dfca4d5ec8ad3ce5271d0ae59e591e4f03f2353`. |
| Explicit CodeQL | PASS | CodeQL run 42023541330 passed C/C++ traced-build analysis and Python analysis on the same candidate commit. |

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

- [CI run 42023541244](https://github.com/cdin-editor/cdin/actions/runs/42023541244) passed on candidate commit `9dfca4d5ec8ad3ce5271d0ae59e591e4f03f2353`:
  - Ubuntu pinned stack + E2E: PASS.
  - macOS pinned stack + E2E: PASS.
  - Windows pinned stack + E2E: PASS.
  - Linux ASan + UBSan + leak detection: PASS.
  - Nine CDIN CTest cases and all pinned component test suites passed.
  - Source-snapshot ZIP validation, reproducibility comparison, SHA-256 verification and artifact upload: PASS on all three native platforms.
  - All pinned GitHub Actions completed without the previous Node.js 20 deprecation warning.
- [CodeQL run 42023541330](https://github.com/cdin-editor/cdin/actions/runs/42023541330) passed both C/C++ traced-build analysis and Python analysis.

These runs validate the composition/lifecycle and component tests. They do **not** prove view attachment, UI snapshot delivery, rendering, document editing, save/reopen, input dispatch or plugin behavior.

### GitHub Default Setup CodeQL

The separate GitHub-managed dynamic workflow [42023531270](https://github.com/cdin-editor/cdin/actions/runs/42023531270) passed Python but failed its JavaScript/TypeScript job. Its log says CodeQL found only empty or syntactically invalid JavaScript/TypeScript files (the repository has no JS/TS source) and then reported that it could not process any JS/TS code.

This dynamic workflow is configured by GitHub repository security settings, not by `.github/workflows/codeql.yml`. The repository-owned workflow covers C/C++ and Python successfully, but cannot disable the unrelated Default Setup language selection. Set Default Setup to the languages actually present (C/C++ and Python), or disable its unsupported JS/TS selection in GitHub settings.

### Artifact provenance

The provenance-attestation step is intentionally skipped on pull requests. It runs only for a trusted push to `main`, using GitHub artifact attestations. PR artifacts are short-lived CI evidence, not signed release artifacts. The source ZIP is not an application installer.

## 4. Compatibility findings

- Backend 1.0.0 package discovery is versioned; keep `find_package(cdinBackend 1.0.0 CONFIG REQUIRED)`.
- Runtime's version identity is verified for the pinned revision: the startup log reports `1.0.0-rc.1`, matching `deps.lock`.
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
8. Maintain native Linux/macOS/Windows CI, sanitizer evidence and C/C++/Python CodeQL on every release candidate.
9. Add measured process RSS, allocator peak where available, leak checks, soak workloads and latency measurements.
10. Produce reproducible platform packages/installers and signed application releases only after the interactive path is complete.

Unrun checks must be reported as NOT RUN, not PASS.
