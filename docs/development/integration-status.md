# Integration status and release gates

This document reports what the current CDIN branch actually connects. A component feature or configured CI job is not automatically a verified CDIN product feature.

The remaining interactive-product and production-release work is tracked in [issue #111](https://github.com/cdin-editor/cdin/issues/111).

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
| Backend/Frontend protocol compatibility | IMPLEMENTED; CI verification pending | Protocol major/minor guards plus `--check` HELLO/HELLO_ACK, real ATTACH, ordered initial UI snapshot delivery, UI flush/ACK and resize through Frontend Core. |
| Shared logging | IMPLEMENTED for CDIN and Backend callbacks | CDIN owns a logger instance and routes Backend log callbacks into it. |
| CLI fail-closed tests | PASS | Nine executable-level CDIN CTest cases pass on Linux, macOS and Windows, including missing values and gated launch paths. |
| Source snapshot | PASS | Deterministic ZIP, path/CRC validation, reproducibility comparison and SHA-256 verification pass on all three native platforms. |
| CI platform coverage | PASS | CI run 42024750897 passed Linux, macOS, Windows and Linux ASan/UBSan/leak detection on candidate commit `167de187af4f0d4df8a81c9afb86ba887eaf6cb4`. |
| Explicit CodeQL | PASS | CodeQL run 42024750919 passed C/C++ traced-build analysis and Python analysis on the same candidate commit. |

## 2. Not complete

| Area | Status | Missing work |
| --- | --- | --- |
| Interactive TUI | NOT IMPLEMENTED | Frontend TUI adapter is not exported as an installable supported target; Backend wakeup and FE-019 event-loop integration remain. The initial snapshot size-budget defect has a fix in Backend PR #7 and an end-to-end smoke in this branch, pending CI. |
| GUI-SDL | NOT IMPLEMENTED in CDIN | GUI adapter is not launched by the current Composition Root. |
| View attachment and UI state | IMPLEMENTED; CI verification pending | CDIN smoke performs ATTACH, verifies ordered options/style/layout and snapshot flush, ACKs the flush and sends resize. The test must pass on native CI before marking VERIFIED. |
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

- [CI run 42024750897](https://github.com/cdin-editor/cdin/actions/runs/42024750897) passed on candidate commit `167de187af4f0d4df8a81c9afb86ba887eaf6cb4`:
  - Ubuntu pinned stack + E2E: PASS.
  - macOS pinned stack + E2E: PASS.
  - Windows pinned stack + E2E: PASS.
  - Linux ASan + UBSan + leak detection: PASS.
  - Nine CDIN CTest cases passed on each native platform.
  - Pinned Frontend suite passed 16/16 and Backend suite passed 10/10 on the inspected platform logs.
  - Source-snapshot ZIP validation, reproducibility comparison, SHA-256 verification and artifact upload: PASS on all three native platforms.
  - All pinned GitHub Actions completed without the previous Node.js 20 deprecation warning.
- [CodeQL run 42024750919](https://github.com/cdin-editor/cdin/actions/runs/42024750919) passed both C/C++ traced-build analysis and Python analysis.

The previous runs validate the earlier composition/lifecycle candidate only. The new ATTACH/snapshot/ACK/resize path is added after those runs and is **not yet verified** until fresh native CI passes. Neither path proves rendering, document editing, save/reopen, input dispatch or plugin behavior.

### GitHub Code Quality language selection

The GitHub Code Quality dynamic workflow [42025677183](https://github.com/cdin-editor/cdin/actions/runs/42025677183) passed Python but failed its JavaScript/TypeScript job. Its log shows that the extractor found only YAML configuration files and no JavaScript/TypeScript source, then failed with `CodeQL could not process any code written in JavaScript/TypeScript`.

This dynamic workflow is configured independently under repository Settings → Security → Code quality, not by `.github/workflows/codeql.yml`. Deselect JavaScript/TypeScript there. The Python Code Quality job may remain enabled; the repository-owned CodeQL workflow separately covers C/C++ and Python. This is a settings change, not a source-code or workflow-file fix.

### Artifact provenance

The provenance-attestation job is intentionally skipped on pull requests. PR build jobs receive only `contents: read`. The separate job with OIDC and attestation permissions runs only on trusted pushes to `main`, after both the full native matrix and sanitizer job have passed. It recreates and validates the same reproducible source ZIP before attesting it. PR artifacts are short-lived CI evidence, not signed release artifacts. The source ZIP is not an application installer.

## 4. Compatibility findings

- Backend 1.0.0 package discovery is versioned; keep `find_package(cdinBackend 1.0.0 CONFIG REQUIRED)`.
- Runtime's version identity is verified for the pinned revision: the startup log reports `1.0.0-rc.1`, matching `deps.lock`.
- The initial ATTACH failure had two distinct Backend causes: (1) the 16 KiB per-frame cap was reused as the aggregate snapshot budget, fixed in merged Backend PR #7; (2) Backend required Runtime UI Model v1's optional `options` member, although Runtime omits it, fixed in Backend PR #9 by encoding an empty CBOR map and returns the first negotiated driver's role in HELLO_ACK for Frontend Core's local resize guard. CDIN pins PR #9's immutable candidate and tests attach/snapshot/flush/ACK/resize. This remains pending fresh CI.
- Frontend TUI target remains experimental/unexported by Frontend Core 1.0.0. CDIN must consume a supported installable adapter, not copy its implementation.

## 5. Release gates

Before describing CDIN as an interactive editor:

1. Pass fresh Backend and CDIN native CI for the corrected aggregate snapshot budget and ATTACH/flush/ACK/resize smoke.
2. Publish an installable Frontend TUI adapter package/target or select another supported adapter.
3. Connect Backend worker-completion wakeup to the Frontend event loop and implement the FE-019 readiness multiplexer.
4. Add product E2E for create/open/edit/save/close/reopen, with exact-byte comparisons for NUL, invalid UTF-8, BOM and line endings.
5. Verify Runtime command/keymap execution through real input.
6. Verify plugin loading, capability isolation, failure handling and unload.
7. Verify Frontend detach/reconnect, multi-frontend sessions and failure recovery.
8. Maintain native Linux/macOS/Windows CI, sanitizer evidence and C/C++/Python CodeQL on every release candidate.
9. Add measured process RSS, allocator peak where available, leak checks, soak workloads and latency measurements.
10. Produce reproducible platform packages/installers and signed application releases only after the interactive path is complete.

The epic and acceptance criteria are tracked in [issue #111](https://github.com/cdin-editor/cdin/issues/111). Unrun checks must be reported as NOT RUN, not PASS.
