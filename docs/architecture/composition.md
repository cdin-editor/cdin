# Composition Root architecture

CDIN assembles and launches independently maintained components. It owns build orchestration and process composition, not editor behavior.

## 1. Ownership

| Component | Owns | CDIN's role |
| --- | --- | --- |
| Kernel | Canonical document bytes, transactions, versions, snapshots and undo/redo. | Pin and build it as part of Backend's dependency closure. Do not call its document API from the root. |
| Runtime | Lua 5.4 commands, keymaps, configuration, plugins, views and semantic UI policy. | Install the Lua module tree and pass the root and entry module to Backend. |
| Backend | Kernel adapter, Runtime Host, OS services, sessions, Protocol server, queues and transport. | Create, start, pump, shut down and destroy through the Backend public API. |
| Frontend | Input, visual layout, text presentation and rendering. | Pin the public Frontend Core contract. A live adapter is not yet attached by CDIN. |
| CDIN | Pins, build, package, launcher and process lifecycle. | Compose public contracts and own application resources. |

## 2. Current executable path

```text
cdin CLI
  |
  +-- parse help/version/check/runtime/frontend options
  |
  +-- create CDIN logger
  |
  +-- verify Backend runtime version
  |
  +-- configure Backend with Runtime root and entry
  |
  +-- Backend create -> start -> pump -> shutdown -> destroy
  |
  +-- close CDIN logger
```

The Backend log callback is kept valid until Backend destruction. Backend therefore releases before the logger is closed.

## 3. Compatibility checks

The current build and launcher check:

- PUC Lua 5.4.x at configure time;
- Kernel package minimum version 1.2.1;
- logger package compatibility with 0.1.0;
- Frontend Core package compatibility with 1.0.0;
- Backend runtime version against the Backend header version;
- Backend and Frontend Protocol major/minor equality at compile time.

These checks do not replace a versioned Backend package configuration. The current CMake uses installed Backend header/library discovery by name; the pinned source revision is enforced by the stack build.

## 4. Current boundary

CDIN does not yet connect a Frontend client to Backend. The `--check` path validates Runtime loading and Backend lifecycle only. TUI/GUI launch remains disabled until the FE-019 readiness/wakeup and event-loop path is complete. Do not add a second editor loop or a fake Frontend session to make the launcher appear interactive.

See the [Architecture audit](audit.md), [Spec traceability](traceability.md) and [Integration status](../development/integration-status.md).
