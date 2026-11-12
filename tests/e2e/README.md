# End-to-end verification

## Current native matrix evidence — 2026-11-12

CDIN PR #138 is merged at `bb49dc9939477d892cfd3d9d6d9c2c6c2d889998`. Its exact tested head was `cfeac2dfe890d8ebe721e2e38fe39c4db3473548`; [CI run 43246685141, attempt 2](https://github.com/cdin-editor/cdin/actions/runs/43246685141) passed all ten native target/profile jobs:

- Linux x86_64: TUI and GUI-SDL.
- Linux ARM64: TUI and GUI-SDL.
- macOS x86_64: TUI and GUI-SDL.
- macOS ARM64: TUI and GUI-SDL.
- Windows x86_64 UCRT64: TUI and GUI-SDL.

Each job checked its actual runner OS/architecture before building; Windows also verified the UCRT64 environment. Artifact names include explicit target and profile. The Linux ASan/UBSan/leak-detection job passed. The first macOS ARM64 GUI-SDL attempt was cancelled; only that job was rerun, and attempt 2 passed.

This is native build/integration-matrix evidence, not proof that every packaged UI is a supported live product. The remaining gates below still apply: Windows Console TUI launch/input/restore, GUI-SDL launch/render/input and cleanup, extension lifecycle, transport/process-failure recovery, soak/performance baselines, clean-machine installation and published immutable/rolling product assets. Do not treat this matrix run as PRODUCT READY.

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

### Current multi-platform evidence

[CDIN CI run 42182694691](https://github.com/cdin-editor/cdin/actions/runs/42182694691) passed on exact candidate SHA `6166fd2034194c3a8b5b13d4baa1d81adce3b14d`.

- Linux and macOS each passed 19/19 Frontend tests and 11/11 root CDIN CTest cases, including `cdin_tui_live_pty_smoke`. Windows passed 18/18 Frontend tests and 11/11 root CDIN CTest cases; the POSIX-only PTY test is not run on Windows.
- All three native logs confirmed the two-session scenario: `Frontend multi-session smoke passed: Driver/Observer, negotiated promotion, detach/reattach lease reacquisition and input`.
- All three platforms passed the document edit/save/reopen path, exact-byte fixtures (NUL, invalid UTF-8, BOM, LF-only and mixed CRLF/LF/CR), and missing-file/failed-atomic-save recovery.
- Compiler-resolved include audit passed on all three platforms for all four CDIN translation units, with no private component source/build headers. The architecture policy tests passed.
- Linux ASan/UBSan/leak-detection job passed. Backend PR #13's tested head also passed Live Runtime, ASan/UBSan, ThreadSanitizer and bounded resource stress on Linux/macOS/Windows; PR #13 is now merged at `3764128a13051c1a16683ef201a391b026a93e6f`, and CDIN has refreshed `deps.lock` to that merge commit (a new full-stack run verifies the merged pin).
- Native source archives passed path/CRC validation and SHA-256 verification. This is source-distribution evidence, not a runnable application installer.

The smoke proves a real headless document path and a real POSIX experimental TUI path on Linux/macOS. It does not make TUI a supported default launch mode: the experimental opt-in remains required, and Windows Console TUI/GUI-SDL are not implemented.

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

The earlier PTY defect was owned and fixed by Frontend PR [#11](https://github.com/cdin-editor/frontend/pull/11), merged at `e29df5118e7b822912724b15c0c963b0b99f2f8a`. The current candidate's CDIN PTY test passes on Linux and macOS in run [42182694691](https://github.com/cdin-editor/cdin/actions/runs/42182694691), including render, terminal input, SIGWINCH, save/quit, signal shutdown, startup failure and restoration. The later Frontend role lifecycle follow-up PR [#14](https://github.com/cdin-editor/frontend/pull/14) is also merged at `eaadc442e04020b0dd209f89c1b94cdb1d3aa7b3`; it allows the granted role to be observed during `ATTACH_SENT` without opening mutating APIs before `ATTACHED`.

Windows does not run the POSIX PTY test. Its TUI remains fail-closed until a native Console readiness/input/restore bridge is implemented.

## 4. Remaining product E2E

The following scenarios remain release gates:

1. Implement and test Windows Console TUI readiness, input/resize and terminal restoration.
2. Add GUI-SDL launch/render/input integration.
3. Exercise plugin load, capability grants/denials, failure isolation and unload in a live session; Runtime's provisional extension manager is not yet connected to a reviewed live CDIN module-resolution and grant path.
4. Verify transport disconnect/reconnect with work pending, document/session continuity under transport loss, Backend/Runtime process failure recovery, partial startup and repeated shutdown.
5. Define named editing workloads and collect allocator peak where available, input-to-visible/save latency, p50/p95/p99, raw cross-platform results and long-running soak/leak measurements. The current short headless benchmark is not a product baseline.
6. Build native install/upgrade/uninstall packages and test clean Linux, macOS and Windows machines; sign release artifacts and verify contents/licenses.

A mock transport or test-only editor implementation is not a substitute for these scenarios.

## 5. Test reporting

A test is PASS only when it has run against the current commit and its result has been inspected. A configured workflow, queued runner, source-level assertion or old green SHA is not a passing current-HEAD test.
