# Registry integration

CDIN uses the independent Registry as its build-time component resolver and source collector. Registry is not linked into the editor executable and is never a runtime dependency.

The accepted boundary is defined by the [Registry architecture](https://github.com/cdin-editor/spec/blob/main/docs/architecture/registry.md), [Registry data contracts 1.2.0](https://github.com/cdin-editor/spec/blob/main/docs/architecture/registry-contracts.md), and [ROOT-010](https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md#L31-L31).

## Ownership

- Kernel, Runtime, Backend and Frontend own their release metadata under `registry/releases/` in their own repositories.
- Each metadata document identifies the logical component, variant, package version, declared dependencies/contracts and immutable full Git source revision.
- CDIN owns the product profiles and pins a Catalog Index snapshot as a build input. The Catalog Index points to immutable metadata commits; its SHA-256 values cover the exact metadata bytes. The catalog publisher remains a separate responsibility and is not implemented by Registry or by the CDIN resolver.
- Registry validates the public documents, resolves the dependency/contract graph, collects the exact source revisions and emits a Workspace, Resolved Manifest and Resolution Report.
- CDIN consumes the prepared source units, builds the selected components, runs integration/E2E tests and packages the product.

No component imports, links or executes Registry. No Registry code is copied into a component or into the CDIN executable.

## Product profiles

- `registry/product-definition.tui.yaml` selects Backend plus Frontend `tui`.
- `registry/product-definition.gui-sdl.yaml` selects Backend plus Frontend `gui-sdl`.
- Backend release metadata declares Kernel and Runtime dependencies. It also declares the Kernel ABI, Runtime Host API and Frontend Protocol contracts that it provides or requires.
- Runtime and Frontend release metadata require the corresponding host/protocol contracts; Kernel publishes its ABI contract.

The current Runtime release is `1.0.0-rc.1`, so the candidate Product Definitions explicitly allow prereleases. This is a transitional release policy and must be tightened when a stable Runtime release is published.

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
2. Build the Registry executable.
3. Validate the selected Product Definition and Catalog Index.
4. Run `resolve` and inspect the command's success/failure result.
5. Run `prepare` against the immutable catalog metadata and Git source commits.
6. Verify the Resolved Manifest.
7. Replay the Manifest into a second Workspace and verify byte-identical Manifest output.
8. Materialize only the selected source units into the private build staging directory.

The prepared workspaces are kept under `.deps/registry-workspace-<profile>` and `.deps/registry-replay-<profile>`. Registry refuses to overwrite existing destinations. Remove those directories explicitly (or use `make clean`) before preparing the same profile again.

Choose the product profile with:

```sh
CDIN_FRONTEND_VARIANT=tui make registry
CDIN_FRONTEND_VARIANT=gui-sdl make registry
```

The Resolved Manifest is the authoritative record of selected component versions and source revisions. CDIN does not maintain a second component lockfile or independently discover component releases.

## Verification

The Pipeline task graph runs Registry before the component build. The product test suite includes:

- Registry's own Go unit and CLI integration tests at the pinned source revision.
- Product Definition and Catalog Index schema validation.
- A real resolve/prepare/replay workflow against the component release metadata.
- Manifest verification and source-unit existence checks.
- A CDIN E2E assertion that Backend resolves Kernel and Runtime and that the selected Frontend variant is materialized.

A successful Registry resolution is not proof that the product builds or works. The existing native component tests, CDIN integration tests, TUI/GUI session tests, sanitizers and cross-platform E2E matrix remain mandatory.

## Release metadata updates

A component maintainer must publish a new immutable metadata document for each new component release. The document must point to the full Git commit that contains the release source, not a branch name or shortened SHA. After the metadata is published, the Catalog Index is updated with the metadata URI and SHA-256 digest. Never edit a published metadata document in place; publish a new immutable metadata identity and update the Catalog Index.

The current Catalog Index is committed as an immutable CDIN product input; this does not make CDIN the Catalog publisher. A separate catalog-publication workflow/owner remains to be established. Registry itself does not publish component releases or host the Catalog.
