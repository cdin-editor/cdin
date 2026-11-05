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
| `cdin_headless_frontend_protocol_smoke` | Runtime/Backend lifecycle plus in-process Frontend Core HELLO/HELLO_ACK handshake. |

The pinned stack builder also runs the test suites owned by the Kernel, Backend and Frontend repositories. Backend owns the current Kernel document integration scenarios.

## 2. Latest inspected evidence

On candidate commit `9dfca4d5ec8ad3ce5271d0ae59e591e4f03f2353`:

- [CI run 42023541244](https://github.com/cdin-editor/cdin/actions/runs/42023541244) passed the Linux, macOS and Windows full-stack jobs.
- All nine CDIN CTest cases passed on each native platform.
- The pinned Frontend component suite passed 16/16 tests on each native platform.
- The Windows Backend component suite passed 10/10 tests.
- The Linux sanitizer job passed ASan, UBSan and leak detection.
- The source snapshot matched across two independent builds, passed path/CRC validation and SHA-256 verification, and was uploaded for each native platform.
- [CodeQL run 42023541330](https://github.com/cdin-editor/cdin/actions/runs/42023541330) passed C/C++ traced analysis and Python analysis.

The separate GitHub-managed Default Setup workflow still fails JavaScript/TypeScript analysis because this repository has no processable JS/TS source. Its Python job passes. This is a repository security setting, not a failure of the explicit C/C++ and Python workflow.

These tests are real executable/component checks, but they do not represent a complete user-visible editing workflow.

## 3. Product E2E still required

Once readiness/wakeup and the live Frontend adapter are connected, add end-to-end scenarios through the real executable and public component interfaces:

1. Start CDIN and attach a TUI frontend.
2. Open or create a document through Runtime and Backend.
3. Send text and key input through the Frontend Protocol.
4. Verify Runtime command and keymap execution.
5. Edit, undo and redo document content through Backend/Kernel.
6. Save, close and reopen the document.
7. Compare exact bytes, including NUL, invalid UTF-8, BOM and line endings.
8. Detach and reattach a frontend without losing Backend-owned editor state.
9. Exercise multiple frontends, driver/observer permissions and reconnect.
10. Inject Runtime, Backend, transport and filesystem failures and verify cleanup/recovery.
11. Load a plugin, verify capability restrictions, then unload it.

A mock transport or test-only editor implementation is not a substitute for these scenarios.

## 4. Test reporting

A test is PASS only when it has run against the current commit and its result has been inspected. A configured workflow, a source-level assertion or a test plan is not a passing test.
