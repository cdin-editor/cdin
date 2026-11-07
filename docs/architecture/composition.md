# Composition Root architecture

CDIN assembles independently maintained components. Registry resolves component releases and collects immutable source; CDIN owns Product Definitions, the pinned Catalog Index input, build/install orchestration, CLI and process composition—not editor-domain behavior.

## 1. Ownership

| Component | Owns | CDIN's role |
| --- | --- | --- |
| Kernel | Canonical document bytes, transactions, versions, snapshots and undo/redo. | Pin/build it in Backend's dependency closure; do not call its document API from the root. |
| Runtime | Lua 5.4 commands, keymaps, configuration, plugins, views and semantic UI policy. | Install Runtime assets and pass the module root/entry to Backend. |
| Backend | Kernel adapter, Runtime Host, OS services, sessions, Protocol server, queues and worker wakeups. | Create/start/pump/shutdown/destroy through the public API; compose a Frontend transport. |
| Frontend | Protocol client, input, semantic presentation model, visual layout, TUI event loop and rendering. | Consume the installed public Frontend Core/TUI package; do not copy its implementation. |
| Registry | Validate Product Definitions/Catalogs, resolve component and contract graphs, collect immutable sources, emit Workspace and Resolved Manifest. | Build-time tooling only; never linked into the editor or a component. |
| CDIN | Product Definitions, pinned Catalog Index input, build, package, launcher, diagnostics and process lifecycle. | Consume the Registry Workspace/Manifest, compose public APIs and own application-level resources and teardown order. |

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

Windows TUI remains fail-closed until a native Console readiness/input/restore bridge is implemented. GUI-SDL launch is implemented behind the Registry `gui-sdl` product profile and the experimental GUI gate; the profile includes the TUI base adapter as a fallback. It remains experimental until the current native and sanitizer matrix passes.

## 3. Registry build-time handoff

CDIN's component graph is selected by Registry Product Definitions, not by component source pins in `deps.lock`.

- Kernel, Runtime, Backend and Frontend own immutable Release Metadata in their respective repositories.
- The CDIN Catalog Index references those metadata documents by immutable raw-content URL and exact SHA-256 digest.
- The TUI Product Definition selects Backend plus Frontend/TUI. The GUI-SDL Product Definition selects Backend plus both Frontend/TUI and Frontend/GUI-SDL variants; the latter is a superset product that preserves TUI fallback.
- Backend's metadata declares Kernel and Runtime dependencies. Its contract declarations provide Runtime Host API and Frontend Protocol and require Kernel ABI. Runtime and Frontend require the corresponding contracts; Kernel provides its ABI.
- The pinned Registry CLI validates the Product Definition/Catalog, resolves the graph, prepares immutable source units, verifies the Resolved Manifest and replays it into a second Workspace.
- CDIN's stack builder uses only the collected source units and obtains package versions from the Resolved Manifest. `deps.lock` retains non-component dependencies and build-tool revisions only.

Registry is not part of the executable dependency graph. It is not linked, loaded, or called at runtime. Catalog publication is a separate responsibility; the committed Catalog Index is a reproducible product input, not a Registry-hosted Catalog.

The current Runtime release is `1.0.0-rc.1`, so both Product Definitions explicitly allow prereleases. This is transitional and must be disabled after a stable Runtime release is published. Registry source is pinned at an immutable commit and built/tested as a host tool.

The current branch includes Registry Go tests, Product Definition/Catalog validation, resolve/prepare/replay, Manifest verification, source-unit checks and product E2E assertions. This implementation is **NOT VERIFIED** until the current TUI and GUI-SDL profiles pass the Linux/macOS/Windows matrix and sanitizer job.

## 4. Compatibility checks

The root build checks package versions passed from the Resolved Manifest, Backend and Frontend Protocol major/minor compatibility, the loaded Backend version against its public header ABI constants, and the Runtime-reported version against the selected Runtime release. These checks establish explicit package/version/Protocol compatibility, not every semantic ABI or behavioral guarantee. Component public contracts and integration tests remain authoritative.

## 5. Architecture boundaries

CDIN may coordinate lifecycle and translate application-level configuration, but must not reproduce:

- document storage, transactions or undo history (Kernel);
- command/keymap/plugin policy (Runtime);
- session ownership, protocol queues or file I/O policy (Backend);
- input parsing, semantic UI state, layout or rendering (Frontend).

`scripts/check_boundaries.py` guards against selected copied implementation calls. It also runs unit tests for the compiler-resolved include graph audit. `scripts/check_include_graph.py` uses the compiler's `-H` trace over CDIN's compile database to reject headers resolved from private component source/build trees while allowing installed public headers. The latest inspected Windows run checked all four CDIN translation units. Linux and macOS include-graph results still need to complete after the current PTY blocker is fixed.

Do not add a second editor loop or a test-only editor session to make the launcher appear interactive.

See the [Architecture audit](audit.md), [Spec traceability](traceability.md) and [Integration status](../development/integration-status.md).
