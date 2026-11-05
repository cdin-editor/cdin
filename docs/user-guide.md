# User guide

This guide explains what the CDIN application does in the current rewrite. CDIN is not yet an interactive editor, so the examples exercise the available command-line and lifecycle behavior only.

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
| `cdin --check` | Load Runtime, create and start Backend, pump pending work once, then shut Backend down. |
| `cdin --runtime-root PATH` | Select the root directory used to load Runtime Lua modules. |
| `cdin --runtime-entry MODULE` | Select the Lua module Backend loads as the Runtime entry point. |
| `cdin --frontend headless` | Select the only frontend value accepted by the current launcher. It does not yet attach a live Frontend adapter. |

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

A successful `--check` confirms that the current pinned Runtime can be loaded by Backend and that the Backend lifecycle can be created, started, pumped and stopped. It does not prove that:

- a TUI or GUI is connected;
- key input reaches Runtime;
- a user can create, edit, save or reopen a document;
- plugins can be used in a live Frontend session;
- a long-running application has passed memory, leak or soak testing.

Those are separate integration and release gates. Their current state is recorded in [Integration status](development/integration-status.md).
