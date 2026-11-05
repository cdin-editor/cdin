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
| Backend package contract | IMPLEMENTED | Backend 1.0.2 exports versioned `cdinBackend` CMake package targets and the optional bounded/binary-safe Lua Host `fs.read_file`; CDIN now requires `find_package(cdinBackend 1.0.2 CONFIG REQUIRED)`. |
| Backend/Frontend protocol compatibility | VERIFIED on Linux/macOS/Windows | Protocol guards plus `--check` HELLO/HELLO_ACK, real ATTACH, ordered initial UI snapshot, `ui.flush`/ACK, queue release and resize through the merged Frontend Core package. The expanded document workflow also passes in CI run 42074655322. |
| Shared logging | IMPLEMENTED for CDIN and Backend callbacks | CDIN owns a logger instance and routes Backend log callbacks into it. |
| CLI fail-closed tests | PASS | Nine executable-level CDIN CTest cases pass on Linux, macOS and Windows, including missing values and gated launch paths. |
| Source snapshot | PASS | Deterministic ZIP, path/CRC validation, reproducibility comparison and SHA-256 verification pass on all three native platforms. |
| CI platform coverage | PASS | CI run 42074655322 passed the pinned stack and expanded document smoke on Linux, macOS and Windows, plus Linux ASan/UBSan/leak detection, on candidate `006263f89f1c1c5352807b00544c8944e131a2dd`. |
| CodeQL scanning | DEFAULT SETUP ACTIVE | GitHub repository CodeQL Default Setup is enabled. The custom advanced workflow is not included in this branch because its SARIF uploads are rejected while Default Setup is enabled. |

## 2. Not complete

| Area | Status | Missing work |
| --- | --- | --- |
| Interactive TUI | PARTIAL / NOT LAUNCHABLE | Frontend PR #2 now installs and exports `cdin::frontend_ui_tui` and its public headers, with a clean-prefix consumer test. CDIN still does not run the TUI app: Backend worker wakeup wiring, native readiness bridge, FE-019 multiplexing and terminal restore/recovery remain. |
| GUI-SDL | NOT IMPLEMENTED in CDIN | GUI adapter is not launched by the current Composition Root. |
| View attachment and UI state | VERIFIED on Linux/macOS/Windows | CDIN smoke performs ATTACH, verifies the ordered six-message initial snapshot including options/style/layout, validates snapshot flush, ACKs it, verifies queue release and sends resize. CI run 42051385717 passed on all three platforms plus Linux sanitizers. |
| Real editing workflow | VERIFIED — HEADLESS / LINUX-MACOS-WINDOWS | `src/integration/frontend_smoke.c` sends `document.new/open/close`, `input.text`, binary `input.paste`, Runtime undo/redo/save keymaps and version-pinned `view.request_lines` through a real Frontend session into Backend/Runtime/Kernel; it compares disk and reopened bytes. All three native jobs passed in CI run 42074655322. The 6-byte fixture covers NUL, invalid UTF-8 and CRLF; it does not yet constitute the full BOM/LF/mixed-EOL release matrix. |
| Keymaps and commands through input | VERIFIED — HEADLESS / LINUX-MACOS-WINDOWS | Typed `request.command`, text/paste and Ctrl+Z/Ctrl+Shift+Z/Ctrl+S are sent over the public Frontend session API and dispatched by Runtime. All three native jobs passed in run 42074655322. Physical terminal key parsing remains part of FE-019. |
| Plugin lifecycle and isolation | NOT VERIFIED from CDIN | Exercise plugin load, capability denial, failure isolation and unload in a live session. |
| Multi-frontend attach/detach | NOT VERIFIED from CDIN | Exercise driver/observer roles, detach and reconnect. |
| Product memory and soak measurements | NOT IMPLEMENTED | Measure RSS, allocator peak, leaks, long-running sessions and latency. |
| Application installers | NOT IMPLEMENTED | Current package task creates a source snapshot only; it is not a runnable application installer. |
| Docker image | NOT IMPLEMENTED | No verified runtime image is built or published. |
| Stable application release | NOT READY | Interactive product path and release gates below remain open. |

## 3. CI and security evidence

### Explicit workflows

- [CI run 42074655322](https://github.com/cdin-editor/cdin/actions/runs/42074655322) passed on current candidate commit `006263f89f1c1c5352807b00544c8944e131a2dd`:
  - Ubuntu pinned stack + E2E: PASS.
  - macOS pinned stack + E2E: PASS.
  - Windows pinned stack + E2E: PASS.
  - Linux ASan + UBSan + leak detection: PASS.
  - Nine CDIN CTest cases passed on each native platform.
  - Pinned Frontend suite passed 16/16 and Backend suite passed 10/10 on the inspected platform logs.
  - Source-snapshot ZIP validation, reproducibility comparison, SHA-256 verification and artifact upload: PASS on all three native platforms.
  - All pinned GitHub Actions completed without the previous Node.js 20 deprecation warning.
- Linux, macOS and Windows logs each explicitly record `Frontend document smoke passed: text/paste, undo/redo, atomic save, close/open and 6 exact bytes`, followed by `Frontend attach smoke passed: snapshot revision=0 messages=6 ordered flush/ACK and resize`. All nine CDIN CTest cases passed on each platform; Backend and Frontend component suites passed 11 and 17 tests respectively. This verifies the headless protocol/document path, not rendering, terminal launch or plugin behavior.
- The custom CodeQL advanced workflow failed in [run 42051385905](https://github.com/cdin-editor/cdin/actions/runs/42051385905) because GitHub CodeQL Default Setup is enabled. The custom workflow file has been removed from this branch to avoid the incompatible advanced upload; Default Setup remains the repository scanner.

### GitHub Code Quality language selection

The GitHub Code Quality dynamic workflow [run 42052219702](https://github.com/cdin-editor/cdin/actions/runs/42052219702) passes Python but fails its JavaScript/TypeScript job. Its log shows the extractor found only YAML workflow/issue-template files and no JS/TS source, then failed with `CodeQL could not process any code written in JavaScript/TypeScript`.

This dynamic workflow is configured independently under repository Settings → Security → Code quality, not by `.github/workflows/codeql.yml`. Deselect JavaScript/TypeScript there. The Python Code Quality job may remain enabled. Separately, verify that the repository CodeQL Default Setup has the intended C/C++ and Python language selection. Both are settings tasks, not source-code fixes.

### Artifact provenance

The provenance-attestation job is intentionally skipped on pull requests. PR build jobs receive only `contents: read`. The separate job with OIDC and attestation permissions runs only on trusted pushes to `main`, after both the full native matrix and sanitizer job have passed. It recreates and validates the same reproducible source ZIP before attesting it. PR artifacts are short-lived CI evidence, not signed release artifacts. The source ZIP is not an application installer.

- [CI run 42074655322](https://github.com/cdin-editor/cdin/actions/runs/42074655322) passed the expanded headless document smoke on Linux, macOS and Windows. The Linux ASan/UBSan/leak-detection job passed too. The log on each native platform confirms `Frontend document smoke passed: text/paste, undo/redo, atomic save, close/open and 6 exact bytes`. The PR provenance-attestation job was skipped as designed because this is a pull request.

## 4. Compatibility findings

- Backend 1.0.2 package discovery is versioned; CDIN requires `find_package(cdinBackend 1.0.2 CONFIG REQUIRED)`. CDIN pins post-merge test-fix commit `f816b9cdbd6b97f7c70a4772a0d8f1e63c47eb9e`; Backend CI including ASan/UBSan/TSan passed after that fix. The optional `host.fs.read_file` keeps file I/O Backend-owned and returns exact bytes with structured error identities.
- Runtime's version identity is verified for the pinned revision: the startup log reports `1.0.0-rc.1`, matching `deps.lock`.
- The initial ATTACH failure had three Backend integration causes: (1) the 16 KiB per-frame cap was reused as the aggregate snapshot budget, fixed in merged Backend PR #7; (2) runtime version reporting remained hard-coded at 1.0.0 after the package bump, fixed in merged PR #8; (3) Backend required Runtime UI Model v1's optional `options` member and advertised the driver role too late for Frontend Core, fixed in merged PR #9 by encoding an empty CBOR map and reserving the first negotiated driver before HELLO_ACK. CDIN pins PR #9's immutable revision and the full ATTACH/snapshot/flush/ACK/resize smoke passes on Linux/macOS/Windows.
- Frontend PR #2 is merged at `94643adada76cb3d056baf0b6ad475451d56ab0f`; `cdinFrontend` now installs/exports `cdin::frontend_ui_tui` when enabled and exposes a typed `request.command` session API. CDIN consumes the package; FE-019 remains the interactive launch gate.
- Runtime PR #2 is Ready for review at tested head `84379cb7f837d1df95edd296e7ccec838f664fba`; it starts from the exact prior CDIN Runtime pin and adds lifecycle commands/keymaps plus FakeHost persistence tests. It is not merged yet. CDIN pins this tested commit while the PR awaits maintainer merge.

## 5. Release gates

Before describing CDIN as an interactive editor:

1. Preserve the verified Backend and CDIN native CI for the aggregate snapshot budget and ATTACH/flush/ACK/resize smoke.
2. Connect the already-published `cdin::frontend_ui_tui` package target to a supported launch path; complete its FE-019 readiness/wakeup/restore integration.
3. Connect Backend worker-completion wakeup to the Frontend event loop and implement the FE-019 readiness multiplexer.
4. Extend the verified headless document smoke with BOM, LF-only and mixed-EOL fixtures plus full-CDIN filesystem failure/interrupted-save injection; current smoke verifies NUL, invalid UTF-8 and CRLF across the real Frontend/Backend/Runtime/Kernel path.
5. Complete terminal-originated key/text input verification after FE-019; headless protocol command/keymap dispatch is already verified.
6. Verify plugin loading, capability isolation, failure handling and unload.
7. Verify Frontend detach/reconnect, multi-frontend sessions and failure recovery.
8. Maintain native Linux/macOS/Windows CI and sanitizer evidence; verify the CodeQL Default Setup language selection and remove JavaScript/TypeScript from the separate Code Quality settings.
9. Add measured process RSS, allocator peak where available, leak checks, soak workloads and latency measurements.
10. Produce reproducible platform packages/installers and signed application releases only after the interactive path is complete.

The epic and acceptance criteria are tracked in [issue #111](https://github.com/cdin-editor/cdin/issues/111). Unrun checks must be reported as NOT RUN, not PASS.
