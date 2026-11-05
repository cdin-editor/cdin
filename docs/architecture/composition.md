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

The current build enforces these public package requirements in `CMakeLists.txt`:

- `find_package(m-mdy-m-log 0.1.0 CONFIG REQUIRED)`;
- `find_package(cdinFrontend 1.0.0 CONFIG REQUIRED)`;
- `find_package(cdinBackend 1.0.0 CONFIG REQUIRED)`.

The pinned stack build also builds the Kernel dependency closure and checks PUC Lua 5.4.x. At runtime, CDIN checks the Backend version reported by the loaded library against the version constants in the Backend headers. The compile checks require Backend and Frontend Protocol major/minor constants to agree. The stack smoke additionally checks the Runtime-reported version against the exact version declared in `deps.lock`.

These are explicit package/version/Protocol guards, not a proof of every semantic ABI or behavioral compatibility guarantee. Component public contracts and integration tests remain authoritative.

## 4. Current boundary

CDIN does not yet connect a live Frontend client to Backend. The `--check` path validates Runtime loading, Backend lifecycle and a headless Frontend Core HELLO/HELLO_ACK protocol smoke. It does not attach a view, publish a UI snapshot, render, dispatch input or edit documents. TUI/GUI launch remains disabled until the FE-019 readiness/wakeup and event-loop path is implemented and verified.

Do not add a second editor loop or a fake Frontend session to make the launcher appear interactive.

See the [Architecture audit](audit.md), [Spec traceability](traceability.md) and [Integration status](../development/integration-status.md).
