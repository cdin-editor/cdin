# End-to-end verification

This directory documents the executable-level test scope and product E2E work still required.

## 1. Current executable tests

The root CTest suite runs the actual `cdin` executable for:

- `--help`: expected exit status and usage text;
- `--version`: expected exit status and application version;
- unknown option: expected failure status and diagnostic text;
- `--check`: real Backend/Runtime create, start, pump, shutdown and destroy through the Backend public API.

The pinned stack builder also runs the test suites owned by the Kernel, Backend and Frontend repositories. Backend owns the current Kernel document integration scenarios.

These are real executable/component tests, but they do not represent a complete user-visible editing workflow.

## 2. Product E2E still required

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

## 3. Test reporting

A test is PASS only when it has run against the current commit and its result has been inspected. A configured workflow, a source-level assertion or a test plan is not a passing test.

The inspected workflow run 41985097875 failed before compilation, so it gives no CDIN E2E result. The corrected dependency and CI changes are pending a new run.
