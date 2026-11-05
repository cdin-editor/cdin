# Installation and build

CDIN does not publish a user-ready installer or a complete interactive editor package yet. This page explains how to build the current pinned stack locally and where the artifacts are placed.

## 1. Supported development environments

The current CI matrix targets Linux on `ubuntu-latest`, macOS on `macos-latest`, and Windows using MSYS2 UCRT64 and MinGW-w64. Windows/MSYS2 is the current Windows build target. MSVC is not claimed as supported.

Install the prerequisites listed in the [Developer guide](development.md#2-prerequisites).

## 2. Build from source

```sh
git clone https://github.com/cdin-editor/cdin.git
cd cdin
make stack
```

The build uses the exact revisions recorded in `deps.lock`. Component sources are checked out under `.deps/src/`; build trees and installed dependencies are placed under `.deps/`.

The installed application is:

- Linux/macOS: `.deps/install/bin/cdin`
- Windows: `.deps/install/bin/cdin.exe`

The Runtime Lua tree is installed under `.deps/install/share/cdin/lua`.

## 3. Run the current executable

```sh
./.deps/install/bin/cdin --help
./.deps/install/bin/cdin --version
./.deps/install/bin/cdin --check
```

The lifecycle check is headless. It does not attach a TUI or GUI and does not perform a document edit or save workflow. See the [User guide](user-guide.md) for the exact behavior and CLI options.

## 4. Source archive

To create a source archive for development review:

```sh
make package
```

The archive is written to `dist/cdin-composition-root-source.zip`. It is a source snapshot, not a platform installer or a release package. It does not bundle the separately built component binaries.

## 5. Release status

The following are not currently available as verified product deliverables:

- signed Linux, macOS or Windows installers;
- a complete runnable TUI or GUI editor;
- an application package containing a connected Frontend;
- a release workflow that publishes tested platform artifacts.

Do not distribute the current `--check` executable as a completed interactive editor. These release gates are tracked in [Integration status](development/integration-status.md).
