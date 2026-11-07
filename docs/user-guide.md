# User guide

This guide describes the CDIN Composition Root candidate. The headless document path is verified on an earlier native candidate; POSIX TUI is experimental. GUI-SDL composition and a live-session smoke are present in the current feature branch, but the current CDIN native run stops at compile time before GUI runtime verification. CDIN is **not yet a release-ready interactive editor**.

## 1. What CDIN does

CDIN assembles separately maintained components:

- Kernel owns document data, edits, versions and undo/redo.
- Runtime owns Lua 5.4 editor policy, commands, keymaps, configuration and plugins.
- Backend hosts Runtime, integrates Kernel and provides sessions, file I/O and operating-system services.
- Frontend owns input, semantic presentation, visual layout and rendering.

The Composition Root pins compatible revisions, builds and installs them, then connects their public interfaces. It does not provide another document model, keymap engine, session implementation or renderer.

## 2. Current capabilities

| Command | Behavior |
| --- | --- |
| `cdin --help` or `cdin -h` | Print supported command-line options. |
| `cdin --version` | Print application version. |
| `cdin --check` | Run the headless Frontend Protocol/document integration path: attach, snapshot/flush/ACK, resize, create/edit/paste/undo/redo/save/close/open and exact-byte readback. |
| `cdin --runtime-root PATH` | Select the Lua module root passed to Backend. |
| `cdin --runtime-entry MODULE` | Select the Runtime entry module passed to Backend. |
| `cdin --frontend headless --check` | Explicitly select the headless verification path. |
| `cdin --frontend tui` | Request the POSIX TUI adapter; requires explicit experimental opt-in and is not yet release-ready. |
| `cdin --frontend gui-sdl --check` | Run the GUI-SDL live-session test with SDL dummy video: attach, create a Runtime document, send SDL text input, dispatch Ctrl+S and verify exact saved bytes. The current CDIN CI head has not yet reached this CTest. |
| `cdin --frontend gui-sdl` | Launch the experimental SDL3 window; requires `CDIN_ENABLE_EXPERIMENTAL_GUI_SDL=1`. |

Unknown options and missing option values are rejected. GUI-SDL is an experimental candidate path, not a supported release target.

## 3. Build the application

From the repository root:

```sh
make stack
```

The stack task checks out immutable revisions from `deps.lock`, builds and tests the component stack, installs it into `.deps/install`, builds CDIN and runs the executable-level tests.

After a successful build:

```sh
./.deps/install/bin/cdin --help
./.deps/install/bin/cdin --version
./.deps/install/bin/cdin --check
```

On Windows, run from MSYS2 UCRT64 and use `cdin.exe`.

## 4. Experimental POSIX TUI

The POSIX TUI path is deliberately gated. To attempt it from a POSIX terminal:

```sh
CDIN_ENABLE_EXPERIMENTAL_TUI=1 ./.deps/install/bin/cdin --frontend tui
```

This opt-in is for integration testing, not general use. Frontend PR [#11](https://github.com/cdin-editor/frontend/pull/11) has merged the request-lifecycle fix and regression tests as `e29df5118e7b822912724b15c0c963b0b99f2f8a`, and CDIN's `deps.lock` pins that immutable commit. The current CDIN native matrix run [42122228431](https://github.com/cdin-editor/cdin/actions/runs/42122228431) is queued. The POSIX TUI remains experimental until CDIN's live PTY and sanitizer tests pass on this merged pin.

The experimental TUI currently targets POSIX. Windows remains fail-closed until the native Console readiness/input/restore bridge is implemented. GUI-SDL is built by `make stack` from the pinned SDL3 3.4.16 archive and Frontend PR #17 candidate; run its current CI check only after the Composition Root compile issue is fixed. To open the interactive window during development, set `CDIN_ENABLE_EXPERIMENTAL_GUI_SDL=1`. The Frontend renderer remains a debug ASCII baseline, so this is not a product-ready desktop editor.

## 5. Runtime location

The installed executable uses the Runtime tree selected by the build/install configuration. To test a different source tree:

```sh
./.deps/install/bin/cdin --check \
  --runtime-root "$PWD/.deps/src/runtime/lua"
```

The default module entry is `cdin.runtime`. Override it with `--runtime-entry` only when the selected Runtime tree contains that module.

## 6. What the current checks prove

The headless `--check` workflow negotiates a real Frontend Protocol session, attaches a view, receives and acknowledges the ordered UI snapshot, and verifies resize. It then uses public component APIs to create and edit a document, send text and binary paste, execute Runtime undo/redo/save keymaps, atomically save, close and reopen, and compare exact bytes. Fixtures include NUL, invalid UTF-8, BOM, LF-only and mixed CRLF/LF/CR data. Missing-file reads and failed atomic saves are also exercised, with in-memory state preserved and a subsequent save recovered.

This workflow does not prove that the terminal renderer or GUI is release-ready. The POSIX PTY smoke is a separate, currently failing gate. The current native CDIN CI evidence is summarized in [Integration status](development/integration-status.md).

The following remain unverified or unimplemented:
- supported, non-experimental TUI launch and full Windows Console TUI;
- the CDIN GUI-SDL live-session smoke on the current candidate (the current native run is blocked at compile);
- production GUI text rendering, IME, bidi/Persian layout and multi-pane rendering;
- live plugin capability isolation and failure containment;
- multiple Frontends, detach/reconnect and recovery;
- measured memory, latency, leak, soak and performance budgets;
- platform installers and stable application releases.

Do not distribute the current executable as a completed interactive editor.
