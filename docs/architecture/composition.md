# Composition Root architecture

CDIN assembles independently maintained components. It owns pins, build/install orchestration, the CLI and process composition—not editor-domain behavior.

## 1. Ownership

| Component | Owns | CDIN's role |
| --- | --- | --- |
| Kernel | Canonical document bytes, transactions, versions, snapshots and undo/redo. | Pin/build it in Backend's dependency closure; do not call its document API from the root. |
| Runtime | Lua 5.4 commands, keymaps, configuration, plugins, views and semantic UI policy. | Install Runtime assets and pass the module root/entry to Backend. |
| Backend | Kernel adapter, Runtime Host, OS services, sessions, Protocol server, queues and worker wakeups. | Create/start/pump/shutdown/destroy through the public API; compose a Frontend transport. |
| Frontend | Protocol client, input, semantic presentation model, visual layout, TUI event loop and rendering. | Consume the installed public Frontend Core/TUI package; do not copy its implementation. |
| CDIN | Pins, build, package, launcher, diagnostics and process lifecycle. | Compose public APIs and own application-level resources and teardown order. |

## 2. Executable paths

### Headless integration path

`cdin --check` is an executable-level integration test, not a fake document engine:

```text
CDIN CLI
  -> create logger
  -> configure Runtime root/entry
  -> Backend create -> start -> pump
  -> Frontend Core HELLO / HELLO_ACK
  -> ATTACH -> ordered UI snapshot -> UI_FLUSH / ACK -> resize
  -> document.new / text + binary paste / undo / redo / save
  -> close / reopen / version-pinned line readback
  -> exact byte comparisons
  -> Backend shutdown -> destroy -> close logger
```

The headless path exercises the real Backend/Runtime/Kernel stack through the public Frontend session API. It covers NUL and invalid UTF-8 data, BOM, LF-only and mixed CRLF/LF/CR fixtures, missing-file reads and failed atomic-save recovery.

### Experimental POSIX TUI path

`cdin --frontend tui` enters a separate launch path. It is fail-closed unless `CDIN_ENABLE_EXPERIMENTAL_TUI=1` is explicitly set. The current POSIX adapter:

1. Opens the terminal using the Frontend terminal API.
2. Creates a wake pipe and installs SIGWINCH/SIGTERM/SIGINT handlers.
3. Creates/starts Backend, attaches a Frontend Protocol client and applies/ACKs the initial snapshot.
4. Creates a scratch document and enters the Frontend-owned TUI event loop.
5. Waits on terminal readiness and the wake source, drains bounded work, handles resize, renders and tears down the terminal/session/backend.

This path is implemented but **not yet accepted as release-ready**. The live PTY smoke reaches the initial UI but currently fails when a version-pinned `view.lines` response is delivered after Frontend incorrectly loses its outstanding request state. Frontend PR [#11](https://github.com/cdin-editor/frontend/pull/11) contains the request-lifecycle fix and regression tests; its macOS job is still pending. CDIN must pin the immutable merged revision and rerun its own complete native/sanitizer matrix before this gate can be called PASS.

Windows TUI remains fail-closed until a native Console readiness/input/restore bridge is implemented. GUI-SDL launch is not implemented.

## 3. Compatibility checks

The current dependency versions and immutable revisions are recorded in `deps.lock`. The pinned stack builder builds the Kernel dependency closure, Backend and Frontend packages, then CDIN. The root build checks:

- the installed logger, Frontend and Backend package versions;
- Backend and Frontend Protocol major/minor compatibility at compile time;
- the loaded Backend version against its public header ABI constants;
- the Runtime-reported version against the pinned Runtime entry.

The current pinned Backend package is 1.0.2; Frontend Core is 1.0.0. These checks establish explicit package/version/Protocol compatibility, not every semantic ABI or behavioral guarantee. Component public contracts and integration tests remain authoritative.

## 4. Architecture boundaries

CDIN may coordinate lifecycle and translate application-level configuration, but must not reproduce:

- document storage, transactions or undo history (Kernel);
- command/keymap/plugin policy (Runtime);
- session ownership, protocol queues or file I/O policy (Backend);
- input parsing, semantic UI state, layout or rendering (Frontend).

`scripts/check_boundaries.py` guards against selected copied implementation calls. It also runs unit tests for the compiler-resolved include graph audit. `scripts/check_include_graph.py` uses the compiler's `-H` trace over CDIN's compile database to reject headers resolved from private component source/build trees while allowing installed public headers. The latest inspected Windows run checked all four CDIN translation units. Linux and macOS include-graph results still need to complete after the current PTY blocker is fixed.

Do not add a second editor loop or a test-only editor session to make the launcher appear interactive.

See the [Architecture audit](audit.md), [Spec traceability](traceability.md) and [Integration status](../development/integration-status.md).
