# Installation and build

CDIN does not publish a user-ready installer or a complete interactive editor package yet. This page explains how to build the current pinned stack locally and what the available commands do.

## 1. Supported development environments

The CI matrix targets Linux on Ubuntu, macOS and Windows using MSYS2 UCRT64/MinGW-w64. MSVC is not claimed as supported.

Install prerequisites listed in the [Developer guide](development.md#2-prerequisites).

## 2. Build from source

```sh
git clone https://github.com/cdin-editor/cdin.git
cd cdin
make stack
```

The build uses immutable revisions in `deps.lock`. Component sources are checked out under `.deps/src/`; build trees and installed dependencies are placed under `.deps/`.

The installed executable is:

- Linux/macOS: `.deps/install/bin/cdin`
- Windows: `.deps/install/bin/cdin.exe`

The Runtime Lua tree is installed under `.deps/install/share/cdin/lua`.

## 3. Run the current executable

```sh
./.deps/install/bin/cdin --help
./.deps/install/bin/cdin --version
./.deps/install/bin/cdin --check
```

The `--check` path is a headless integration workflow. It attaches Frontend Core to Backend, validates the initial snapshot/flush/ACK and resize path, then exercises document create/edit/paste/undo/redo/save/close/open and exact-byte readback. It also exercises BOM and EOL variants and filesystem failure recovery. It does not launch a terminal or GUI renderer.

## 4. Experimental POSIX TUI

An experimental POSIX TUI path is available only with an explicit environment opt-in:

```sh
CDIN_ENABLE_EXPERIMENTAL_TUI=1 ./.deps/install/bin/cdin --frontend tui
```

This is for development and integration testing only. It is not a supported end-user installation path. The live PTY acceptance test currently fails due to Frontend's pending `view.lines` request lifecycle; Frontend PR [#11](https://github.com/cdin-editor/frontend/pull/11) contains the fix and regression tests. Wait for its complete native CI matrix, merge it, update CDIN's immutable Frontend pin and pass the CDIN PTY/sanitizer matrix before treating the POSIX TUI as usable.

Windows TUI remains fail-closed until a native Console readiness/input/restore bridge is implemented. GUI-SDL launch is not available.

## 5. Source archive

To create a source archive for development review:

```sh
make package
```

The archive is written to `dist/cdin-composition-root-source.zip`. It is a source snapshot, not a platform installer or release package; it does not bundle the separately built component binaries.

## 6. Release status

The following are not currently available as verified product deliverables:

- signed Linux, macOS or Windows application installers;
- a release-ready interactive TUI or GUI editor;
- a Windows Console TUI adapter;
- a complete application package containing a verified Frontend;
- a stable release workflow that publishes tested platform artifacts.

Do not distribute the current `--check` executable or experimental TUI as a completed interactive editor. Track the remaining work in [Integration status](development/integration-status.md) and [issue #111](https://github.com/cdin-editor/cdin/issues/111).
