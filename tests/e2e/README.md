# End-to-end verification

This directory documents executable-level integration coverage and product E2E gates. Only results run against the recorded SHA count as PASS.

## 1. Executable test suite

The root CTest suite runs the real `cdin` executable and the integration helpers.

| Test | Expected behavior |
| --- | --- |
| `cdin_cli_help` | Exit 0 and usage text. |
| `cdin_cli_version` | Exit 0 and application version. |
| `cdin_cli_help_describes_frontend_modes` | Help advertises `headless|tui`. |
| `cdin_cli_unknown_option` | Exit 1 and invalid-argument diagnostic. |
| `cdin_cli_missing_runtime_root` | Exit 1 when `--runtime-root` has no value. |
| `cdin_cli_missing_runtime_entry` | Exit 1 when `--runtime-entry` has no value. |
| `cdin_cli_missing_frontend` | Exit 1 when `--frontend` has no value. |
| `cdin_cli_unsupported_frontend_is_gated` | Exit 3 and explicit diagnostic for unsupported GUI-SDL. |
| `cdin_cli_interactive_launch_is_gated` | Exit 3 when TUI is requested without experimental opt-in. |
| `cdin_headless_frontend_protocol_smoke` | Frontend HELLO/HELLO_ACK, ATTACH/snapshot/flush/ACK/resize, document edit/save/reopen and exact-byte readback. |
| `cdin_tui_live_pty_smoke` (POSIX only) | Real TUI launch, initial render, text input, SIGWINCH, save+quit, signal shutdown, startup failure and terminal restoration. |

The headless smoke uses the public Frontend session API and a real Backend/Runtime/Kernel instance. Kernel owns document bytes/history, Runtime owns command/keymap policy, Backend owns Host file operations and Protocol queues, and Frontend owns the semantic TUI model.

## 2. Headless document integration

The verified headless workflow exercises:

1. HELLO/HELLO_ACK and Frontend ATTACH.
2. Ordered initial UI snapshot, `ui.flush`/ACK, queue release and resize.
3. `document.new`, `document.open`, text input and binary paste.
4. Runtime undo, redo and save keymaps.
5. Atomic save, close and reopen.
6. Version-pinned `view.request_lines` and exact byte comparison between disk and the reopened document.
7. File fixtures containing NUL, invalid UTF-8, BOM, LF-only and mixed CRLF/LF/CR data.
8. Missing-file read, failed atomic commit, preservation of in-memory bytes and successful recovery save.

### Latest completed native evidence

[CDIN CI run 42117574266](https://github.com/cdin-editor/cdin/actions/runs/42117574266), candidate `dd1f5896c27756948750a1adc1770b16b4207b66):

- Windows completed the full stack and all 9/9 CDIN CTest tests. Its log explicitly confirms the document smoke, byte-fixture smoke, filesystem-failure recovery, 6 architecture unit tests and the compiler-resolved include graph over all 4 CDIN translation units.
- Linux and macOS passed the headless CDIN CTest and Frontend component suite (19/19), but failed the separate live PTY test (9/10 root CTest tests passed).
- Linux ASan/UBSan/leak job failed on the same live PTY test; no separate sanitizer issue was identified.
- The Linux/macOS include-graph task was not reached because the earlier TUI test failure stopped the stack task.

This is a real end-to-end document path, but it is headless integration coverage, not a successful interactive editor session.

## 3. Experimental POSIX TUI

The launcher supports `--frontend tui`, but requires explicit `CDIN_ENABLE_EXPERIMENTAL_TUI=1`. The CI PTY harness sets this variable. Without the opt-in, launch remains fail-closed.

The harness uses a pseudo-terminal and checks:
- terminal title and initial rendering;
- terminal-originated text input and rendered bytes;
- SIGWINCH interruption and wakeup;
- Ctrl+S followed by Ctrl+Q while UI work is pending;
- saved scratch-file bytes;
- separate SIGTERM shutdown;
- startup failure with a missing Runtime root;
- terminal mode, descriptor flags and alternate-screen/cursor/bracketed-paste restoration.

The current live PTY acceptance test fails on Linux and macOS because Frontend may clear its outstanding version-pinned `view.lines` request when a snapshot leaves the same document version/line target unchanged. The matching response then arrives without `request_pending` and is rejected. Frontend PR [#11](https://github.com/cdin-editor/frontend/pull/11) changes request-state lifecycle semantics and adds regression coverage. Its Linux, Windows and Pipeline/quality checks passed; macOS remained queued at the latest inspection. After full Frontend matrix success and merge, CDIN must update `deps.lock` to the immutable merge SHA and rerun the complete native/sanitizer matrix.

Windows does not run the POSIX PTY test. Its TUI remains fail-closed until a native Console readiness/input/restore bridge is implemented.

## 4. Remaining product E2E

The following scenarios remain release gates:

1. Pass the POSIX PTY test with the merged Frontend request-lifecycle fix.
2. Implement and test Windows Console TUI readiness and terminal restoration.
3. Add GUI-SDL launch/render/input integration.
4. Exercise plugin load, capability denial, failure isolation and unload in a live session.
5. Verify multiple Frontends, Driver/Observer promotion, detach/reattach and reconnect.
6. Exercise Backend/Runtime/transport failures and partial-startup recovery through the full executable.
7. Add long-running editor workloads for memory, leak, latency and soak measurements.
8. Test native install/upgrade/uninstall on clean Linux, macOS and Windows machines.

A mock transport or test-only editor implementation is not a substitute for these scenarios.

## 5. Test reporting

A test is PASS only when it has run against the current commit and its result has been inspected. A configured workflow, queued runner, source-level assertion or old green SHA is not a passing current-HEAD test.
