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

## 4. Trusted Runtime extensions (integration candidate)

The Composition Root branch adds explicit local extension selection. It does not
scan an extension directory or load everything it finds. Each selected extension
must be a trusted child directory below an administrator-controlled root and
must provide an `init.lua` entry point.

For a headless lifecycle check:

```sh
./.deps/install/bin/cdin --check \
  --extension-root "$HOME/.local/share/cdin/extensions" \
  --load-extension sample
```

To use the same selection during an experimental TUI session:

```sh
CDIN_ENABLE_EXPERIMENTAL_TUI=1 ./.deps/install/bin/cdin --frontend tui \
  --extension-root "$HOME/.local/share/cdin/extensions" \
  --load-extension sample
```

`--load-extension` may be repeated. Extension names are bounded dotted
namespace identifiers, not filesystem paths. CDIN passes the selected names
to Backend on the Runtime owner thread and unloads successfully loaded
extensions in reverse order during controlled shutdown. The management calls
are local embedding APIs; there is no Frontend Protocol command for loading
code. Do not point the root at a user-writable download/cache directory or
untrusted code. Host sandboxing is defense in depth, not process isolation.

This path depends on Backend 1.2.0 candidate [PR #16](https://github.com/cdin-editor/backend/pull/16)
and remains an integration candidate until the pinned build, live Lua init/unload
smoke, capability allow/deny and failure-cleanup tests pass on the current
native matrix. It is not yet a stable extension distribution/marketplace
contract.

## 5. Experimental TUI

The POSIX TUI requires the explicit environment opt-in:

```sh
CDIN_ENABLE_EXPERIMENTAL_TUI=1 ./.deps/install/bin/cdin --frontend tui
```

This is for development and integration testing only. It is not a supported
end-user installation path. The merged Frontend request-lifecycle fix
[PR #11](https://github.com/cdin-editor/frontend/pull/11) is pinned by its
immutable merge commit `e29df5118e7b822912724b15c0c963b0b99f2f8a`. A separate
ConPTY adapter fix is under Draft [Frontend PR #16](https://github.com/cdin-editor/frontend/pull/16).
The last inspected Windows run reached the initial render but did not yet
observe edited text in the rendered output. Keep Windows TUI fail-closed until
the input/ACK/redraw path passes the ConPTY acceptance test. GUI-SDL launch
is not available.

## 6. Source archive

## 6. Source archive

To create a source archive for development review:

```sh
make package
```

The archive is written to `dist/cdin-composition-root-source.zip`. It is a source snapshot, not a platform installer or release package; it does not bundle the separately built component binaries.

## 7. Release status

The following are not currently available as verified product deliverables:

- signed Linux, macOS or Windows application installers;
- a release-ready interactive TUI or GUI editor;
- a verified Windows Console/ConPTY TUI input and restoration path;
- a complete application package containing a verified Frontend;
- a stable release workflow that publishes tested platform artifacts.

Do not distribute the current `--check` executable or experimental TUI as a completed interactive editor. Track the remaining work in [Integration status](development/integration-status.md) and [issue #111](https://github.com/cdin-editor/cdin/issues/111).
