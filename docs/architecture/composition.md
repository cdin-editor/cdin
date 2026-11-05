# Composition Root architecture

cdin is the Composition Root. It resolves immutable component pins, validates ABI/protocol compatibility, builds and packages components, launches Backend, routes diagnostics and owns reverse-order shutdown.

| Component | Owns | Composition Root responsibility |
|---|---|---|
| Kernel | canonical document bytes, edit transactions, versions, snapshots, undo/redo | never duplicates or links Kernel internals directly |
| Runtime | commands, keymaps, configuration, plugins/extensions, semantic UI policy | installs the Lua module tree and passes its root/entry to Backend |
| Backend | Kernel/Runtime hosts, sessions, protocol, queues, OS services | creates, starts, pumps and shuts down through its public API |
| Frontend | input, protocol client, semantic projection, layout and rendering | pins the Core peer; does not copy UI implementations |
| cdin | dependency graph, build, package, launch and process lifecycle | composes public contracts only |

The --check command is a headless lifecycle smoke test. Interactive TUI/GUI launch stays fail-closed until Backend readiness/wakeup and Frontend event-loop integration satisfy FE-019. The Composition Root must not create a parallel event loop or editor state to hide that missing contract.
