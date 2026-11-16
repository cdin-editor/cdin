# Installation and build

CDIN does not publish a user-ready installer or a complete interactive editor package yet. This page explains how to build the current pinned stack locally and what the available commands do.

## 1. Supported development environments

The CI matrix targets Linux on Ubuntu, macOS and Windows using MSYS2 UCRT64/MinGW-w64. MSVC is not claimed as supported.

Install prerequisites listed in the [Developer guide](development.md#2-prerequisites).

## 2. Build from source

```sh
git clone https://github.com/cdin-editor/cdin.git
cd cdin
make stack-dev
```

This is the explicit hybrid developer path: Registry is built from its pinned source revision, and Runtime/Frontend source delivery is enabled only for development/CI. Component sources are checked out under `.deps/src/`; build trees and installed dependencies are placed under `.deps/`.

The normal consumer command is `make install`. It is artifact-only; the current component releases are published, and the candidate lock pins Kernel 1.2.3, Runtime 1.0.0, Backend 1.2.2, Frontend 1.2.2 and the five-target SDL3 SDK 3.4.16 for GUI-SDL. However, CDIN main still consumes Registry 1.0.0, whose immutable binary has a Manifest schema-floor regression when ADR-0028 release provenance is present. Registry's schema fix is merged to its main branch, but the immutable Registry 1.0.1 Release is not yet published. CDIN PR #149 carries the updated artifact-first candidate; its clean-consumer/Product Acceptance jobs have not passed. Do not use the developer source path as evidence that artifact-first installation is complete.

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

This path is composed with the published Backend 1.2.2 package and the candidate CDIN/Runtime pins. The public command-line selection path is not a stable extension distribution or marketplace contract: the exact immutable stack still needs live Lua init/unload, capability allow/deny, failure-cleanup and recovery tests on the supported native matrix. Keep extension loading restricted to trusted administrator-controlled roots.

## 5. Experimental TUI

The POSIX TUI requires the explicit environment opt-in:

```sh
CDIN_ENABLE_EXPERIMENTAL_TUI=1 ./.deps/install/bin/cdin --frontend tui
```

This is for development and integration testing only; it is not yet a supported
end-user installation path. The Frontend ConPTY adapter fix in
[PR #16](https://github.com/cdin-editor/frontend/pull/16) is merged and its
Windows input/save/quit/restoration E2E passed in CDIN run
[42265415995](https://github.com/cdin-editor/cdin/actions/runs/42265415995).
That historical ConPTY pass does not replace current whole-product acceptance:
TUI and GUI-SDL still need to pass the exact current Registry/component pins,
clean installation and lifecycle gates before being advertised as stable.
GUI-SDL uses the published immutable SDL3 SDK 3.4.16, but its current renderer
is not production-ready: shaping, font fallback, grapheme layout, bidi and
Persian/Arabic presentation remain incomplete.

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
- complete, supported interactive TUI and GUI-SDL launch/input/shutdown acceptance across the five native targets;
- a complete application package containing a verified Frontend;
- a versioned product release workflow connected to the verified ten target/profile archives, immutable Registry Manifest, checksums and release provenance.

Do not distribute the current `--check` executable or experimental TUI as a completed interactive editor. Track the remaining work in [Integration status](development/integration-status.md) and [issue #111](https://github.com/cdin-editor/cdin/issues/111).
