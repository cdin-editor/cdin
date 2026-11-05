# User guide

This guide explains what the CDIN application does in the current rewrite. CDIN is not yet an interactive TUI/GUI editor, but `--check` now exercises a headless end-to-end document workflow through the public component interfaces.

## 1. What CDIN does

CDIN assembles separately maintained components:

- Kernel owns document data and editing operations.
- Runtime owns editor policy and runs on Lua 5.4.
- Backend hosts Runtime, integrates Kernel and provides sessions and operating-system services.
- Frontend handles input, visual layout and rendering.

The Composition Root pins compatible component revisions, builds and installs them, then starts Backend through its public C API. It does not provide another document model, keymap engine or renderer.

## 2. Current capabilities

| Command | Behavior |
| --- | --- |
| `cdin --help` or `cdin -h` | Print the supported command-line options. |
| `cdin --version` | Print the CDIN application version. |
| `cdin --check` | Load Runtime, create/start Backend, negotiate and attach a Frontend Protocol session, validate the UI snapshot/flush/ACK and resize path, then exercise document new/text/paste/undo/redo/save/close/open and exact-byte readback before Backend shutdown. |
| `cdin --runtime-root PATH` | Select the root directory used to load Runtime Lua modules. |
| `cdin --runtime-entry MODULE` | Select the Lua module Backend loads as the Runtime entry point. |
| `cdin --frontend headless` | Select the headless protocol verification path; it does not launch a terminal renderer. |

Unknown options and missing option values are rejected. Interactive launch currently exits with status 3 and an explanation. This is deliberate: the readiness/wakeup and event-loop contract is not complete.

## 3. Build the application

The full build is documented in [Installation](installation.md). From the repository root, the standard development command is:

```sh
make stack
```

It checks out the pinned sources from `deps.lock`, builds and tests the component stack, installs it into `.deps/install`, builds CDIN and runs the lifecycle check.

After a successful build:

```sh
./.deps/install/bin/cdin --help
./.deps/install/bin/cdin --version
./.deps/install/bin/cdin --check
```

On Windows, run the commands from MSYS2 UCRT64 and use `cdin.exe`.

## 4. Runtime location

The installed executable looks for Runtime under the configured install data directory. To test a different Runtime tree, pass an explicit path:

```sh
./.deps/install/bin/cdin --check \
  --runtime-root "$PWD/.deps/src/runtime/lua"
```

The default module entry is `cdin.runtime`. The entry can be overridden with `--runtime-entry`, but it must match a module available in the selected Runtime tree.

## 5. What this check does not prove

A successful `--check` is intended to verify the headless Frontend Protocol path through Backend and Runtime, including document lifecycle, text/paste, undo/redo, save, close/reopen and byte-exact reads. The expanded smoke currently passes Linux and Windows, with Linux ASan/UBSan/leak detection; macOS validation remains queued. A green component suite is not the same as a complete interactive TUI. It does not prove that:

- a terminal or GUI renderer is running or usable;
- the native FE-019 readiness loop, worker wakeups and terminal restoration are complete;
- plugins can be used safely in a live TUI session;
- multiple Frontends, detach/reconnect and Observer/Driver promotion work end-to-end;
- a long-running application has passed memory, leak, soak or latency testing.

Those are separate integration and release gates. Their current state is recorded in [Integration status](development/integration-status.md).
