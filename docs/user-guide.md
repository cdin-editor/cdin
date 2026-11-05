# User guide

This guide describes the current CDIN Composition Root candidate. CDIN can run a verified headless document integration workflow and contains an experimental POSIX TUI launch path. It is **not yet a release-ready interactive editor**.

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

Unknown options and missing option values are rejected. GUI-SDL is not a supported launcher target.

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

This opt-in is for integration testing, not general use. The live PTY acceptance test currently fails because Frontend can clear a pending version-pinned line request before the matching `view.lines` response arrives. Frontend PR [#11](https://github.com/cdin-editor/frontend/pull/11) contains a request-lifecycle fix and regression tests; its complete native matrix must pass and be merged before CDIN updates the immutable pin and reruns the full stack.

The experimental TUI currently targets POSIX. Windows remains fail-closed until the native Console readiness/input/restore bridge is implemented. GUI-SDL is not implemented.

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
- successful interactive TUI input/render/resize/shutdown on POSIX;
- a native Windows TUI;
- GUI-SDL;
- live plugin capability isolation and failure containment;
- multiple Frontends, detach/reconnect and recovery;
- measured memory, latency, leak, soak and performance budgets;
- platform installers and stable application releases.

Do not distribute the current executable as a completed interactive editor.
