# End-to-end verification

This directory documents the executable-level test scope and product E2E work still required.

## 1. Current executable tests

The root CTest suite runs the actual `cdin` executable for:

| Test | Expected behavior |
| --- | --- |
| `cdin_cli_help` | Exit 0 and usage text. |
| `cdin_cli_version` | Exit 0 and the configured application version. |
| `cdin_cli_unknown_option` | Exit 1 and invalid-argument diagnostic. |
| `cdin_cli_missing_runtime_root` | Exit 1 when `--runtime-root` has no value. |
| `cdin_cli_missing_runtime_entry` | Exit 1 when `--runtime-entry` has no value. |
| `cdin_cli_missing_frontend` | Exit 1 when `--frontend` has no value. |
| `cdin_cli_unsupported_frontend_is_gated` | Exit 3 and an explicit message for unsupported TUI launch. |
| `cdin_cli_interactive_launch_is_gated` | Exit 3 when asked to launch without `--check`. |
| `cdin_headless_frontend_protocol_smoke` | In-process Frontend Core HELLO/HELLO_ACK, real ATTACH/snapshot/flush/ACK/resize, then document new/text/binary paste/undo/redo/save/close/open and byte-exact readback via `view.request_lines`. |

The pinned stack builder also runs the test suites owned by Kernel, Backend, Frontend and Runtime. The CDIN smoke uses their installed public interfaces; Kernel owns bytes/undo history, Runtime owns command/keymap policy, Backend owns file I/O and protocol queues, and Frontend owns the Protocol session.

## 2. Latest inspected evidence

On candidate commit `167de187af4f0d4df8a81c9afb86ba887eaf6cb4`:

- [CI run 42024750897](https://github.com/cdin-editor/cdin/actions/runs/42024750897) passed the Linux, macOS and Windows full-stack jobs.
- All nine CDIN CTest cases passed on each native platform.
- The pinned Frontend component suite passed 16/16 tests on each native platform.
- The Backend component suite passed 10/10 tests on each native platform.
- The Linux sanitizer job passed ASan, UBSan and leak detection.
- The source snapshot matched across two independent builds, passed path/CRC validation and SHA-256 verification, and was uploaded for each native platform.
- The archive digest was identical on Linux, macOS and Windows: `c1b947567abc54a48e6b86449de4d36c110ed33e745c8b54a5cb6d251c732d5d`.
- [CodeQL run 42024750919](https://github.com/cdin-editor/cdin/actions/runs/42024750919) passed C/C++ traced analysis and Python analysis.

The PR provenance job is skipped by design: pull-request builds do not receive OIDC/attestation permissions. The main-only provenance job runs after both the complete native matrix and sanitizer job succeed on a trusted push to `main`.

The separate GitHub-managed Default Setup workflow [42024744686](https://github.com/cdin-editor/cdin/actions/runs/42024744686) still fails JavaScript/TypeScript analysis because this repository has no processable JS/TS source. Its Python job passes. This is a repository security setting, not a failure of the explicit C/C++ and Python workflow.

The current `cdin_headless_frontend_protocol_smoke` implementation now covers one complete byte-exact document cycle through the real in-process Frontend/Backend/Runtime/Kernel stack. It remains a headless protocol check, not an interactive terminal or GUI session. The expanded CI result is pending; product work for the FE-019 TUI loop, GUI, plugin isolation, multiple Frontends, reconnect and soak/latency gates remains tracked in [issue #111](https://github.com/cdin-editor/cdin/issues/111).

## 3. Remaining interactive product E2E

The headless document workflow is now implemented in `src/integration/frontend_smoke.c`: it uses the public Frontend session API and a real Backend/Runtime/Kernel instance to create a document, send text and binary paste, exercise Runtime undo/redo/save bindings, close and reopen the file, and compare exact bytes from both disk and `view.request_lines`. The current CI result is pending; do not mark it PASS until the run on the current commit completes.

Once the FE-019 readiness/wakeup path is connected, the remaining E2E scenarios must cover:

1. Start CDIN and launch the installable TUI adapter in a real terminal.
2. Verify rendering, scrolling, resize, signals, terminal restore and orderly shutdown.
3. Verify Backend worker wakeups reach the native Frontend owner loop without polling-only regressions.
4. Detach and reattach a Frontend without losing Backend-owned editor state.
5. Exercise multiple Frontends, Driver/Observer permissions, promotion and reconnect.
6. Inject Runtime, Backend, transport and filesystem failures and verify cleanup/recovery.
7. Load a plugin, verify capability restrictions, failure isolation and unload.
8. Add a separate GUI-SDL launch and input/render integration path before claiming GUI support.

A mock transport or test-only editor implementation is not a substitute for these scenarios.

## 4. Test reporting

A test is PASS only when it has run against the current commit and its result has been inspected. A configured workflow, a source-level assertion or a test plan is not a passing test.
