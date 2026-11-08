# Registry integration

CDIN invokes the independent Registry as a build-time component resolver and source collector. Registry is never linked into the editor executable and is never a component runtime dependency.

The boundary is defined by the [Registry architecture](https://github.com/cdin-editor/spec/blob/main/docs/architecture/registry.md), [Registry data contracts 1.2.0](https://github.com/cdin-editor/spec/blob/main/docs/architecture/registry-contracts.md), [ADR-0022](https://github.com/cdin-editor/spec/blob/main/docs/adr/ADR-0022-minimal-static-release-catalog.md) and [ROOT-010](https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md#L31-L31).

## Ownership

- Kernel, Runtime, Backend and Frontend own their source, package versions and immutable Release Metadata under `registry/releases/` in their own repositories. Each Release Metadata document declares one or more source units, full immutable Git revisions, dependencies and contracts.
- The Registry repository maintains the version-controlled Catalog Index snapshot at `catalogs/cdin-components/catalog-index.json`. It references component-owned Release Metadata by immutable URI and exact SHA-256 digest. The Registry engine reads this Catalog through the same generic input path it uses for any consumer; it does not hardcode component names or repository topology.
- CDIN owns only its Product Definitions and product composition. It does not contain the Catalog Index, Release Metadata URIs, component repository URLs or component source pins.
- CDIN pins the exact Registry source commit in `deps.lock`. The Registry checkout therefore supplies both the generic engine and the Catalog snapshot associated with that immutable commit.
- Registry validates the Product Definition, Catalog and Release Metadata, resolves dependency/contract graphs, collects exact source revisions and emits a Workspace, Resolved Manifest and Resolution Report.
- CDIN consumes the prepared source units, builds the selected components, runs integration/E2E tests and packages the product.

No component imports, links or executes Registry. No Registry code is copied into a component or into the CDIN executable.

## Product profiles

- `registry/product-definition.tui.yaml` selects Backend plus Frontend `tui`.
- `registry/product-definition.gui-sdl.yaml` selects Backend plus both Frontend `tui` and `gui-sdl` variants. The GUI-SDL product retains the TUI adapter as a supported fallback.
- Backend Release Metadata declares Kernel and Runtime dependencies. It also declares Kernel ABI, Runtime Host API and Frontend Protocol contract relationships.
- Runtime and Frontend Release Metadata require the corresponding host/protocol contracts; Kernel publishes its ABI contract.

The synchronized integration candidate selects Runtime `1.0.0-rc.2`, whose immutable Release Metadata provides `org.cdin.runtime-extension-contract` version `1.0.0`. Both Frontend TUI and GUI-SDL variants resolve to `1.0.1`. The Product Definitions explicitly allow prereleases while Runtime remains an RC; this is transitional and must be tightened after a stable Runtime release is published.

## Commands

Requirements include Git and Go 1.27.3 (the Registry toolchain). The pinned Registry source revision is recorded under `[tooling.registry]` in `deps.lock`.

```sh
make deps
make registry
make stack
make check
```

`make registry` performs the real Registry CLI workflow:

1. Check out the exact Registry source commit and run its Go tests.
2. Build the Registry executable from that same checkout.
3. Validate the selected Product Definition and the Catalog Index at `<pinned-registry-checkout>/catalogs/cdin-components/catalog-index.json`.
4. Let Registry fetch and verify each immutable Release Metadata document and resolve the requested dependency/contract graph.
5. Run `prepare` so Registry collects the declared immutable Git source units.
6. Verify the Resolved Manifest.
7. Replay the Manifest into a second Workspace and verify byte-identical Manifest output.
8. Materialize only the selected source units into the private CDIN build staging directory.

The prepared workspaces are kept under `.deps/registry-workspace-<profile>` and `.deps/registry-replay-<profile>`. Registry refuses to overwrite existing destinations. Remove those directories explicitly (or use `make clean`) before preparing the same profile again.

Choose the product profile with:

```sh
CDIN_FRONTEND_VARIANT=tui make registry
CDIN_FRONTEND_VARIANT=gui-sdl make registry
CDIN_FRONTEND_VARIANT=gui-sdl make stack-gui
```

The Resolved Manifest is the authoritative record of selected component versions and source revisions. CDIN does not maintain a second component lockfile or independently discover component releases. The only component-selection data it supplies is the Product Definition.

## Catalog and release updates

A component maintainer publishes a new immutable Release Metadata document in that component's own repository. The Catalog maintainer then verifies the metadata URI and exact SHA-256 digest and updates `catalogs/cdin-components/catalog-index.json` in the Registry repository. A consumer adopts that Catalog snapshot by pinning the corresponding immutable Registry commit in its own build-tool lock.

Never edit published Release Metadata in place or reuse a digest after changing its bytes. The Catalog is data distributed with the Registry source; the generic resolver does not scan GitHub organisations or infer repositories. It follows only the Catalog entries and source units declared in verified Release Metadata.

## Verification

The Pipeline task graph runs Registry before the component build. The product test suite includes:

- Registry's own Go unit and CLI integration tests at the pinned source revision.
- Product Definition and Catalog Index schema validation.
- A real resolve/prepare/replay workflow against immutable component Release Metadata and Git commits.
- Manifest verification and source-unit existence checks.
- A CDIN E2E assertion that Backend resolves Kernel and Runtime and that the selected Frontend variant is materialized.

A successful Registry resolution is not proof that the product builds or works. Native component tests, CDIN integration tests, TUI/GUI session tests, sanitizers and the cross-platform E2E matrix remain mandatory.
