# End-to-end verification

The Composition Root's executable-level CTest suite covers the observable CLI
contract and a real Backend + Runtime lifecycle through the public Backend API:

- help/version output and exit status;
- rejection of unknown arguments;
- Runtime module loading and Backend create/start/pump/shutdown/destroy;
- Backend's own Kernel document integration scenarios are executed by the pinned
  Backend component build in scripts/build_stack.py.

This is not yet a full user-visible edit workflow. A Product E2E test is still
required once the Backend readiness/wakeup contract and live Frontend adapters
are integrated. That test must create/open/edit/save/reopen a document through
the real Runtime + Backend + Kernel + Frontend stack, then compare exact bytes
(including NUL, invalid UTF-8, BOM and line endings). Do not replace that with a
mock transport or a test-only editor implementation.

CI runs native Linux, macOS and Windows builds; ASan/UBSan and leak detection
run on Linux. A platform result is only considered verified after its workflow
has actually completed.
