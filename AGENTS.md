# AGENTS.md — CDIN Product Composition Root: Architecture, Contracts and Engineering Rules

> **Purpose:** These instructions define how an engineering agent must inspect, modify, test, package and release the CDIN product. They are repository-specific operating rules, not a replacement for the normative CDIN Specification. When this file and an accepted Spec contract disagree, the accepted Spec contract wins; update this file in the same change that resolves the discrepancy.

## 0. Repository identity and mission

- Product repository: [`cdin-editor/cdin`](https://github.com/cdin-editor/cdin)
- Default branch: `main`
- Product role: Composition Root for independently maintained CDIN components.
- Product interfaces: TUI and GUI-SDL, with any additional profile explicitly defined by the Product Definition and supported implementation.
- Primary product integration epic: [CDIN #111](https://github.com/cdin-editor/cdin/issues/111).

CDIN assembles, configures, verifies, builds, packages, launches, upgrades and releases the editor through public, versioned component contracts.

CDIN is **not** the owner of Kernel, Runtime, Backend, Frontend, Registry or cdin-x implementation. It must not duplicate those components' logic. Registry is a build-time dependency-resolution and delivery tool, not a library or service embedded in the running editor.

The objective is a usable, reproducible, installable editor. A passing component test suite, a successful CI build, a source archive, a merged PR or a published GitHub Release by itself is not proof that the integrated CDIN product is ready.

## 1. Authority, source hierarchy and change discipline

### 1.1 Normative authority

Use sources in this order:

1. Latest accepted normative requirements, accepted ADRs, public contracts, schemas and conformance fixtures in [`cdin-editor/spec`](https://github.com/cdin-editor/spec).
2. Public APIs, headers, package contracts and implementation of the owning component at its exact selected revision.
3. CDIN Product Definitions, generated Resolved Manifest, dependency/tool locks and product-owned integration code.
4. Component and product documentation, release notes and issue acceptance criteria.
5. This file and other implementation notes.

A proposal, open decision, draft ADR, issue discussion or unmerged PR is not an accepted contract. Do not promote a proposed requirement merely because some code happens to implement it. Conversely, an accepted requirement is not proof that its owning repository has implemented it.

The Spec default branch can contain accepted changes newer than its latest stable tag. At the start of each task, inspect both the current default branch and the latest stable Spec release. Record which exact source/tag was used. Do not hard-code a remembered Spec version as permanently current.

### 1.2 Required inspection before editing

Before modifying files:

1. Fetch the current repository default branch, head SHA and relevant tags.
2. Inspect the current branch and all existing uncommitted changes available to the environment.
3. Read the relevant issue, PR body, review comments and linked work in the owning repositories.
4. Read the exact Spec requirement, ADR, contract, schema and fixtures.
5. Read the current implementation, public headers, package metadata and tests.
6. Identify the code owner and the downstream consumer that proves the contract works.
7. Identify generated files and the generator/task that owns them.

Preserve owner changes. Do not replace an existing file with a duplicate, delete historical evidence, rewrite published release identities, or introduce a second source of truth.

### 1.3 Status vocabulary

Use the following terms precisely:

- `ACCEPTED`: approved normative contract or ADR.
- `PROPOSED`: not yet an accepted contract.
- `IMPLEMENTED`: implementation exists in its owning repository.
- `PARTIAL`: only some required behavior is implemented.
- `NOT IMPLEMENTED`: no sufficient implementation exists.
- `NOT VERIFIED`: implementation may exist, but required tests/evidence are missing.
- `INTEGRATED`: the exact compatible versions are exercised together by the consumer.
- `RELEASED`: immutable or explicitly rolling release assets have actually been published.
- `PRODUCT READY`: the complete product acceptance and distribution gates have passed.

Do not infer one status from another. In particular, ACCEPTED does not imply IMPLEMENTED; IMPLEMENTED does not imply RELEASED; RELEASED does not imply INTEGRATED; and INTEGRATED does not imply PRODUCT READY.

For each change preserve this traceability chain:

`Spec requirement / ADR → owner repository → implementation → test → exact CI run and SHA → package / release identity → CDIN Manifest and Product Definition → product E2E evidence`

Do not invent requirement IDs, source-line anchors, versions, checksums, release assets, test outcomes or CI evidence.

## 2. Repository and ownership reference map

These repositories are separate authorities. Work in the repository that owns the behavior; link to it rather than copying its implementation into CDIN.

| Repository | Ownership in the CDIN architecture | Primary references |
|---|---|---|
| [`cdin-editor/spec`](https://github.com/cdin-editor/spec) | Normative architecture, requirements, ADRs, public contracts, JSON Schemas and conformance fixtures. | [Module boundaries](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md), [Frontend Protocol](https://github.com/cdin-editor/spec/blob/main/docs/architecture/frontend-protocol.md), [Registry contracts](https://github.com/cdin-editor/spec/blob/main/docs/architecture/registry-contracts.md), [ADR index](https://github.com/cdin-editor/spec/tree/main/docs/adr) |
| [`cdin-editor/kernel`](https://github.com/cdin-editor/kernel) | Canonical document bytes, document lifecycle, edits, transactions, snapshots, versions, undo/redo and document-level search through the public C ABI. | [Kernel ABI documentation](https://github.com/cdin-editor/kernel/blob/main/docs/abi.md), [architecture](https://github.com/cdin-editor/kernel/blob/main/docs/architecture.md), [installation/package documentation](https://github.com/cdin-editor/kernel/blob/main/docs/installation.md), [Release workflow](https://github.com/cdin-editor/kernel/blob/main/.github/workflows/release.yml) |
| [`cdin-editor/runtime`](https://github.com/cdin-editor/runtime) | Lua 5.4 editor policy: commands, keymaps, logical views, selection, configuration, semantic UI model and extension lifecycle. | [Runtime Host API contract copy](https://github.com/cdin-editor/runtime/blob/main/docs/contracts/runtime-host-api.md), [Extension API](https://github.com/cdin-editor/runtime/blob/main/docs/contracts/extension-api.md), [module package](https://github.com/cdin-editor/runtime/blob/main/docs/module-package.md), [Release workflow](https://github.com/cdin-editor/runtime/blob/main/.github/workflows/release.yml), [Runtime #16](https://github.com/cdin-editor/runtime/issues/16) |
| [`cdin-editor/backend`](https://github.com/cdin-editor/backend) | Backend sessions, OS services, Kernel adapter, Runtime hosting, Host API implementation, Frontend Protocol server, transport, sequencing, queues and backpressure. | [Host API](https://github.com/cdin-editor/backend/blob/main/docs/host-api.md), [Protocol contract notes](https://github.com/cdin-editor/backend/blob/main/docs/contracts/protocol-1.0.0.md), [artifact packages](https://github.com/cdin-editor/backend/blob/main/docs/artifact-packages.md), [Release workflow](https://github.com/cdin-editor/backend/blob/main/.github/workflows/release.yml), [Backend #25](https://github.com/cdin-editor/backend/issues/25) |
| [`cdin-editor/frontend`](https://github.com/cdin-editor/frontend) | Frontend Core plus peer TUI, GUI-SDL and Headless adapters; input adaptation, device/window ownership, cell/pixel geometry, text presentation, caches and rendering. | [Frontend Protocol contract](https://github.com/cdin-editor/frontend/blob/main/docs/contracts/frontend-protocol.md), [semantic model](https://github.com/cdin-editor/frontend/blob/main/docs/contracts/semantic-model.md), [text presentation](https://github.com/cdin-editor/frontend/blob/main/docs/contracts/text-presentation.md), [event loop and I/O](https://github.com/cdin-editor/frontend/blob/main/docs/contracts/event-loop-and-io.md), [Release workflow](https://github.com/cdin-editor/frontend/blob/main/.github/workflows/release.yml), [Frontend #15](https://github.com/cdin-editor/frontend/issues/15), [Frontend #40](https://github.com/cdin-editor/frontend/issues/40) |
| [`cdin-editor/registry`](https://github.com/cdin-editor/registry) | Generic Catalog ingestion, GitHub Release discovery, metadata validation, SemVer/dependency/contract resolution, source/artifact retrieval, safe extraction, cache, Manifest and replay. | [Catalogs](https://github.com/cdin-editor/registry/blob/main/docs/catalogs.md), [artifact delivery](https://github.com/cdin-editor/registry/blob/main/docs/artifact-delivery.md), [using Registry](https://github.com/cdin-editor/registry/blob/main/docs/using-registry.md), [release workflow](https://github.com/cdin-editor/registry/blob/main/.github/workflows/release.yml), [Registry #53](https://github.com/cdin-editor/registry/issues/53) |
| [`cdin-editor/cdin-x`](https://github.com/cdin-editor/cdin-x) | Extension catalog, plugin packages, themes, fonts, bundles and extension-manager content under its published contract. | [Build documentation](https://github.com/cdin-editor/cdin-x/blob/main/docs/building/README.md), [plugin installation](https://github.com/cdin-editor/cdin-x/blob/main/docs/installing-plugins.md), [bundle workflow](https://github.com/cdin-editor/cdin-x/blob/main/.github/workflows/bundle.yml), [Release workflow](https://github.com/cdin-editor/cdin-x/blob/main/.github/workflows/release.yml) |
| [`cdin-editor/cdin`](https://github.com/cdin-editor/cdin) | Product Definitions, dependency provisioning, Composition Root, integration/build orchestration, launcher, product E2E, final application packaging and release lifecycle. | [CDIN README](https://github.com/cdin-editor/cdin/blob/main/README.md), [traceability](https://github.com/cdin-editor/cdin/blob/main/docs/architecture/traceability.md), [Registry integration](https://github.com/cdin-editor/cdin/blob/main/docs/development/registry.md), [integration status](https://github.com/cdin-editor/cdin/blob/main/docs/development/integration-status.md), [E2E plan](https://github.com/cdin-editor/cdin/blob/main/tests/e2e/README.md) |
| [`m-mdy-m/pipeline`](https://github.com/m-mdy-m/pipeline) | Shared task execution and reusable CI/release orchestration. | [Compiled/build release workflow](https://github.com/m-mdy-m/pipeline/blob/main/.github/workflows/release.yml), [source-only release workflow](https://github.com/m-mdy-m/pipeline/blob/main/.github/workflows/source-release.yml) |
| [`m-mdy-m/log.c`](https://github.com/m-mdy-m/log.c) | Standalone C logger consumed through the appropriate owner-owned boundary. | [Repository](https://github.com/m-mdy-m/log.c) |
| [`m-mdy-m/psx`](https://github.com/m-mdy-m/psx) | Repository/project convention and structure validation. | [Repository](https://github.com/m-mdy-m/psx) |
| [`m-mdy-m/gix`](https://github.com/m-mdy-m/gix) | Git branch/workflow conventions. | [Repository](https://github.com/m-mdy-m/gix) |

The website is maintained separately in [`cdin-editor/cdin-editor.github.io`](https://github.com/cdin-editor/cdin-editor.github.io). Do not add website source, assets, deployment workflows or website dependencies to this repository.

## 3. Normative Spec references for CDIN work

Use the documents below as the contract map. Read the full relevant document, not only the cited heading. The `main` links are convenient navigation; for a release or compatibility claim, pin the actual Spec commit/tag used by the build.

### 3.1 Repository boundaries and ownership

- [Spec module boundaries](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L63-L102) defines dependency direction, state ownership and communication paths.
- [ARCH-040](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L65-L71), [ARCH-042](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L65-L71) and [ARCH-043](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L65-L71) are ACCEPTED in the currently inspected Spec source. ARCH-041, ARCH-044, ARCH-045 and ARCH-046 are marked PROPOSED there; do not describe those proposed requirements as accepted without checking a newer Spec revision.
- [State ownership](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L73-L90): Kernel owns canonical document state/history; Runtime owns view selection and logical editor state; Frontend owns visual layout and physical input/window state.
- [Runtime Host API 1.0.0](https://github.com/cdin-editor/spec/blob/main/docs/contracts/runtime-host-api.md#L1-L15) states that it is the only route from Runtime to Backend and forbids Runtime from loading or calling the Kernel directly.
- [Frontend Protocol architecture](https://github.com/cdin-editor/spec/blob/main/docs/architecture/frontend-protocol.md#L1-L40) establishes semantic state ownership and frontend visual responsibilities.

### 3.2 Frontend Protocol and UI model

- [Frontend Protocol](https://github.com/cdin-editor/spec/blob/main/docs/architecture/frontend-protocol.md) is the accepted Backend-to-Frontend wire contract.
- [PROTO-001 through PROTO-004](https://github.com/cdin-editor/spec/blob/main/docs/architecture/frontend-protocol.md#L34-L41): Backend/Runtime own semantic editor state and keymap policy; Frontend owns visual layout and sends raw input/request events.
- [Handshake and capabilities](https://github.com/cdin-editor/spec/blob/main/docs/architecture/frontend-protocol.md#L42-L87): every session negotiates version/capabilities; multiple Frontends may attach; one attached frontend holds the Driver lease and others are Observers.
- [Atomic updates and backpressure](https://github.com/cdin-editor/spec/blob/main/docs/architecture/frontend-protocol.md#L128-L130) and [protocol wire](https://github.com/cdin-editor/spec/blob/main/docs/architecture/protocol-wire.md) define message ordering, flush boundaries and protocol-level authority.
- [Runtime UI Model v1](https://github.com/cdin-editor/spec/blob/main/docs/architecture/ui-model-v1.md) is the semantic UI state contract; it is not a pixel/cell renderer API.

### 3.3 Accepted capability ADRs

- [ADR-0023 — IME composition](https://github.com/cdin-editor/spec/blob/main/docs/adr/ADR-0023-ime-composition-contract.md#L1-L35): preedit is local to the originating Frontend; it does not mutate canonical document bytes; commit is tied to captured view/version/selection and is applied once; capability must be negotiated.
- [ADR-0024 — PaneTree splitter resize](https://github.com/cdin-editor/spec/blob/main/docs/adr/ADR-0024-pane-tree-splitter-resize.md#L1-L35): Frontend owns hit-testing, pointer capture and local drag preview; Backend enforces capability/Driver/revision and ordered publication; Runtime owns semantic ratio mutation; CDIN tests the live product flow.
- [ADR-0025 — Immutable target-specific artifact delivery](https://github.com/cdin-editor/spec/blob/main/docs/adr/ADR-0025-immutable-target-artifact-delivery.md): Registry downloads, verifies and safely stages publisher-built packages; Registry does not build or test component code; the Composition Root performs product-specific linking, tests, packaging and launch.
- [ADR-0026 — Semantic UI presentation](https://github.com/cdin-editor/spec/blob/main/docs/adr/ADR-0026-ui-presentation-contract.md#L1-L36): Runtime owns semantic styles/panel/widget meaning and command policy; Backend validates/projects; Frontend presents; snapshots are atomic; widget actions use the normal Runtime command path; negotiated capability is required.
- [ADR-0027 — Byte-anchored visible line windows](https://github.com/cdin-editor/spec/blob/main/docs/adr/ADR-0027-byte-anchored-visible-line-windows.md#L1-L30): byte anchors remain canonical, Backend resolves the anchor and line bytes from the same Kernel snapshot, and Frontend must not derive byte positions from glyph/grapheme counts.
- [Spec conformance index](https://github.com/cdin-editor/spec/blob/main/docs/testing/conformance.md) and the associated [IME](https://github.com/cdin-editor/spec/tree/main/docs/testing/vectors), [PaneTree](https://github.com/cdin-editor/spec/tree/main/docs/testing/vectors), [UI presentation](https://github.com/cdin-editor/spec/blob/main/docs/testing/vectors/ui-presentation-v1.json) and [byte-anchored line](https://github.com/cdin-editor/spec/blob/main/docs/testing/vectors/byte-anchored-lines-v1.json) fixtures describe shared cases. A Spec JSON fixture is not proof that a component runner has executed it.

### 3.4 Registry contracts and accepted release metadata discovery

- [ADR-0022 — Generic Consumer-Independent Registry](https://github.com/cdin-editor/spec/blob/main/docs/adr/ADR-0022-minimal-static-release-catalog.md#L1-L67): Registry understands requirements, not consumer identity. Product Definitions are declarative; Registry is generic; CDIN owns product integration, build, tests and packaging.
- [ADR-0025 — Immutable target-specific artifact delivery](https://github.com/cdin-editor/spec/blob/main/docs/adr/ADR-0025-immutable-target-artifact-delivery.md): the publisher owns package build/test/publication; Registry owns generic resolution/retrieval/verification/extraction/Manifest/replay; the Composition Root owns product integration.
- [Registry data contracts](https://github.com/cdin-editor/spec/blob/main/docs/architecture/registry-contracts.md#L1-L32) defines the current data-contract baseline, schemas, SemVer identity and deterministic resolution.
- [Catalog and GitHub Release Sources](https://github.com/cdin-editor/spec/blob/main/docs/architecture/registry-contracts.md#L119-L139) defines the static `entries` model and dynamic `release_sources` model.
- [Immutable artifact delivery](https://github.com/cdin-editor/spec/blob/main/docs/architecture/immutable-artifact-delivery.md#L1-L37) defines artifact kind, target, format, filename, immutable URI, SHA-256, size, layout, source provenance and build provenance.
- [ADR-0028 — GitHub Release metadata discovery](https://github.com/cdin-editor/spec/blob/main/docs/adr/ADR-0028-github-release-metadata-discovery.md#L1-L50) is ACCEPTED. Its publisher contract and resolver requirements are mandatory when the dynamic release-source model is used.

#### Mandatory ADR-0028 behavior

The old pattern of committing one tracked file such as `registry/releases/backend-1.2.1.json` for every version is not the required publication model for new releases.

Each component publisher must generate its Component Release Metadata from the exact tagged commit **after** the package assets and their checksums have been built. It uploads that generated JSON as an asset on the matching GitHub Release. Do not commit the generated per-version JSON to the source repository and do not require a new tracked per-version metadata file.

Canonical metadata Release Asset names:

- Default variant: `<component-id>-<version>.json` — for example `backend-1.2.1.json`.
- Non-default variant: `<component-id>-<variant>-<version>.json` — for example `frontend-tui-1.1.0.json` and `frontend-gui-sdl-1.1.0.json`.

The generated document must satisfy the current Component Release Metadata schema. Its `publication` declaration must identify provider `github-releases-v1`, exact GitHub repository URI, exact release tag, full tag-resolved commit SHA and exact metadata asset filename. Exactly one source unit must identify the publisher repository and its revision must equal the tag-resolved commit. The metadata must not contain its own URI or digest; GitHub Release Asset API metadata provides the metadata asset URI, size and SHA-256 digest.

The release tag must be the configured tag prefix (normally `v`) plus the metadata SemVer. The GitHub Release prerelease flag must agree with the SemVer prerelease status. Package version, Git tag, component API/ABI version, Protocol version and Spec version are separate identities and must be checked independently.

A Catalog using the dynamic model declares one stable `release_sources` record per logical component/variant/repository, not one record per version. The provider is `github-releases-v1`. A Catalog document must use exactly one model: legacy static `entries` **or** `release_sources`; it must not mix them. Existing static Catalogs and historical metadata remain backward-compatible during migration. If a migration needs both models simultaneously, use separate valid Catalog inputs only where the Registry contract supports that arrangement; do not create an invalid hybrid document.

Registry must enumerate the complete eligible GitHub Release inventory using bounded pagination. It must not call GitHub's floating `/releases/latest` endpoint for component resolution. It must not choose by `published_at`, API page order or first result. It validates SemVer/tag prefix, draft/prerelease policy, exact metadata asset name, uniqueness, Git tag target, source revision, API digest and byte size. Missing/duplicate assets, missing digest, mismatch, moved tag, incomplete pagination, rate-limit exhaustion and ambiguity fail deterministically and closed.

Validated candidates enter the existing SemVer/dependency/contract resolver. The highest compatible SemVer wins under the Product Definition prerelease policy. Equal-precedence but different identities are ambiguous; publication time is not a tie-breaker.

The Resolved Manifest must preserve exact Release Source identity, repository, Release ID/API URI, tag, tag commit, metadata asset name/URI/size/digest and selected component artifact identity. Replay uses only the recorded immutable URI/digest and must not discover a newer release or substitute another asset. Offline discovery is permitted only from previously verified cache data for the exact Release Source identity.

Never simplify this contract to "download whichever GitHub Release is most recently published". Dynamic discovery means discovering and validating all eligible releases; SemVer resolution remains deterministic. Never substitute the product's rolling `latest` channel for a component's versioned SemVer release source.

Related work to inspect rather than duplicate:

- [Spec #37](https://github.com/cdin-editor/spec/issues/37) — original requirement; still requires implementation/rollout evidence even though the Spec contract was merged.
- [Spec PR #38](https://github.com/cdin-editor/spec/pull/38) — merged implementation of ADR-0028 and Registry Data Contract 1.4.0.
- [Registry #53](https://github.com/cdin-editor/registry/issues/53) — generic Registry implementation.
- [Runtime #16](https://github.com/cdin-editor/runtime/issues/16) — Runtime release metadata/module package publication.
- [Backend #25](https://github.com/cdin-editor/backend/issues/25) — Backend package publication; always re-check its current state before acting.
- [Frontend #40](https://github.com/cdin-editor/frontend/issues/40) — Frontend Core/TUI/GUI-SDL package publication.

### 3.5 Product-specific requirements and open decisions

- [CDIN component description in Spec](https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md) defines the product Composition Root role.
- [Spec open decisions register](https://github.com/cdin-editor/spec/blob/main/docs/decisions/open-decisions.md) must be checked before treating unresolved proposals as fixed architecture.
- [Spec status/reference documents](https://github.com/cdin-editor/spec/tree/main/docs/reference) and [Spec README](https://github.com/cdin-editor/spec/blob/main/README.md) provide status/navigation. Regenerate generated reports through their owner scripts; do not manually edit computed counts.

## 4. Component and contract rules

### 4.1 Kernel

Kernel owns canonical document bytes, versions, snapshots, transactions, edit history and undo/redo. CDIN must never implement a second document store or edit engine. The Backend-owned adapter is the component that calls the public Kernel ABI.

Use the actual selected Kernel package and public ABI compatibility declaration. Do not infer ABI from package SemVer. Validate the package and its external link dependencies using the exact package/Manifest identity.

Reference: [Kernel repository](https://github.com/cdin-editor/kernel), [Kernel ABI docs](https://github.com/cdin-editor/kernel/blob/main/docs/abi.md), [Spec module boundaries](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L73-L90).

### 4.2 Runtime

Runtime owns command and keymap interpretation, logical view/selection state, Lua editor policy, plugin lifecycle and semantic UI model. CDIN and Frontend must not implement duplicate command/keymap engines.

Runtime is hosted by Backend using the versioned Runtime Host API. Do not link Runtime directly to Kernel, load Kernel symbols from Lua or duplicate document bytes/history in Runtime.

Lua 5.4 is an explicit host/runtime dependency; do not assume it is provided by an arbitrary system interpreter without checking the Product Definition/environment contract.

Reference: [Runtime repository](https://github.com/cdin-editor/runtime), [Spec Runtime Host API](https://github.com/cdin-editor/spec/blob/main/docs/contracts/runtime-host-api.md#L1-L15), [Runtime extension API](https://github.com/cdin-editor/runtime/blob/main/docs/contracts/extension-api.md).

### 4.3 Backend

Backend owns sessions, OS services, Runtime hosting, the public Host API implementation, Kernel integration, transport and Frontend Protocol server behavior. It must not own terminal, SDL or other display-toolkit rendering.

Backend's public Host API and Protocol versions are separate compatibility dimensions. The package must declare Kernel ABI, logger C API and Lua 5.4/environment requirements as specified by the package contract. Backend must not privately vendor Kernel, logger or Lua when those are separately declared dependencies.

Reference: [Backend repository](https://github.com/cdin-editor/backend), [Host API docs](https://github.com/cdin-editor/backend/blob/main/docs/host-api.md), [Spec Protocol](https://github.com/cdin-editor/spec/blob/main/docs/architecture/frontend-protocol.md), [Backend artifact package docs](https://github.com/cdin-editor/backend/blob/main/docs/artifact-packages.md).

### 4.4 Frontend

Frontend owns physical input, native window/terminal resources, text shaping/presentation, rendering, cell/pixel geometry, hit-testing and disposable presentation caches. It consumes semantic Runtime state through the public Frontend Protocol. It must not interpret keymaps, own editor commands, mutate canonical document bytes directly, or include private Kernel/Runtime/Backend headers.

Core is a shared Frontend package and must be resolved/installed only once. TUI and GUI-SDL are peer adapter variants. TUI must not acquire SDL3. GUI-SDL may include TUI fallback only when the selected product definition explicitly requires it. GUI-SDL must not depend on TUI-private headers or internals.

Reference: [Frontend repository](https://github.com/cdin-editor/frontend), [Spec Protocol ownership](https://github.com/cdin-editor/spec/blob/main/docs/architecture/frontend-protocol.md#L34-L41), [Spec module boundaries](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L73-L90).

### 4.5 cdin-x

cdin-x owns the catalog and extension bundles it publishes. CDIN may select and bundle the correct cdin-x release/package, but must not create a second plugin manager, duplicate extension discovery/resolution or take ownership of extension package semantics.

Do not mistake cdin-x's bundle for a CDIN application binary. It is a data/module asset consumed by the product.

Reference: [cdin-x repository](https://github.com/cdin-editor/cdin-x), [bundle workflow](https://github.com/cdin-editor/cdin-x/blob/main/.github/workflows/bundle.yml), [plugin installation guide](https://github.com/cdin-editor/cdin-x/blob/main/docs/installing-plugins.md).

## 5. Registry integration in CDIN

### 5.1 Registry is a host tool, not a product runtime dependency

CDIN uses Registry during dependency preparation/build/installation. Do not link Registry into the application, start a Registry daemon as an application prerequisite, or add Registry-specific behavior to components.

Normal consumer bootstrap must use the target-correct, immutable Registry executable artifact. It must not clone Registry, install Go, execute `go test ./...` or build the Registry Go project on the consumer machine.

Registry executable identity and Catalog source identity must be pinned and verifiable. The target architecture declared by the asset must match the binary format actually inside it. Never trust filenames alone. Verify checksum, version, release tag, source commit and target architecture before execution.

Current relevant work: [CDIN #121](https://github.com/cdin-editor/cdin/issues/121), [Registry PR #43](https://github.com/cdin-editor/registry/pull/43). Do not consume the historically incorrect old `v0.1.0-dev` ARM mappings; verify the fresh corrected release actually exists before updating pins.

### 5.2 Product Definitions

CDIN owns its declarative TUI and GUI-SDL Product Definitions:

- [TUI Product Definition](https://github.com/cdin-editor/cdin/blob/main/registry/product-definition.tui.yaml)
- [GUI-SDL Product Definition](https://github.com/cdin-editor/cdin/blob/main/registry/product-definition.gui-sdl.yaml)

Product Definitions declare logical component IDs, variants, version constraints, environment contracts, prerelease policy and delivery policy. They must not duplicate Catalog release metadata, repository URLs or package maps when those belong to Registry/component release sources.

Check the exact schema version and schema from the pinned Spec/Registry contracts. Product Definitions are data, never executable product-specific resolver logic.

TUI must not select SDL3. GUI-SDL selects the GUI-SDL adapter and any TUI fallback required by its declared product composition. Common Core must be resolved exactly once.

### 5.3 Source and artifact workspace handling

The Registry workspace can contain source-delivered component trees and/or artifact-delivered package prefixes. CDIN's Registry adapter and build system must understand the delivery mode actually selected; do not assume every component lives under a source-unit path.

- `source`: build from the exact collected immutable source revision. This remains useful for an explicit developer/CI source-build path.
- `artifact`: require one compatible target-specific package for every selected component. A missing or ambiguous package is a hard error.
- `artifact-or-source`: use a compatible package when it is declared; source fallback is allowed only when no compatible package exists under the contract.

A chosen artifact that fails download, digest, size, package-layout or safe-extraction validation must fail closed. Do not silently replace a corrupt artifact with source.

For native packages, use the exact OS/architecture/ABI target tuple. Do not infer libc/ABI compatibility from a platform label or compiler name. For Runtime, use the declared universal Lua module archive layout rather than inventing a platform binary. Use CMake/pkg-config exports and declared dependencies, not private component source paths.

The Resolved Manifest is the authoritative record of the selected component versions, source revisions, metadata identities and package artifacts for one build. `deps.lock` is not a second component lockfile. Do not hand-maintain component version lists in scripts or duplicate the Manifest in another lock file.

Reference: [Spec immutable artifact delivery](https://github.com/cdin-editor/spec/blob/main/docs/architecture/immutable-artifact-delivery.md), [Registry workspace documentation](https://github.com/cdin-editor/registry/blob/main/docs/using-registry.md), [CDIN Registry integration](https://github.com/cdin-editor/cdin/blob/main/docs/development/registry.md).

### 5.4 Package security, cache and replay

Validate exact bytes before extraction/use. Reject path traversal, absolute paths, links/escapes, special files, duplicate/normalized path collisions, unsafe platform names, malformed archives, excessive entry count/expanded size/path depth and metadata/target mismatches.

Use private staging, verify the complete workspace and Manifest, and publish atomically. A failed install or upgrade must not replace a functioning installation. Rollback must restore the previous known-good state.

Cache identity must include immutable metadata/artifact identity, target and digest. Never trust a cache entry merely because its filename exists. Test cold, warm, partial, corrupt and offline caches. Offline replay must use the exact previously verified Manifest identities; it must not discover a newer component version.

SHA-256 establishes byte integrity relative to the trusted digest; it is not, by itself, publisher authentication or proof of a trusted build. Use attestations/signatures where the release contract supports them, and never claim signature verification unless it is actually performed.

## 6. SDL3 SDK

SDL3 is a GUI-SDL-only dependency. TUI must not download, configure, build, link or ship SDL3.

CDIN #126 produced the SDL3 SDK publisher workflow, but a merged producer PR is not proof that target-specific Release assets have been published or that CDIN consumes them. [CDIN #124](https://github.com/cdin-editor/cdin/issues/124) tracks the prebuilt SDK consumer path.

The normal consumer path must acquire an exact verified SDK package for the selected OS/architecture/toolchain ABI. The SDK must contain the headers, CMake package/imported targets and libraries required by the actual Frontend consumer. Verify extracted SDK layout and run an out-of-tree consumer configure/link test without access to an SDL source checkout.

Do not build SDL from source as part of ordinary GUI-SDL consumer installation. An explicitly named SDK producer/developer path may build the pinned SDL source in CI. Never mislabel an upstream source tarball or host-only archive as a ready-to-consume cross-platform SDK.

References: [CDIN #124](https://github.com/cdin-editor/cdin/issues/124), [CDIN #126](https://github.com/cdin-editor/cdin/pull/126), [SDL3 source-build implementation](https://github.com/cdin-editor/cdin/blob/main/scripts/build_stack.py), [Spec immutable artifact delivery](https://github.com/cdin-editor/spec/blob/main/docs/architecture/immutable-artifact-delivery.md).

## 7. Product build and application distributions

### 7.1 Build output versus source snapshot

A source snapshot is for contributors and source review. It is not a CDIN application distribution and must never be named or presented as a target-specific executable build.

The current source package helper and pre-release metadata are separate from the installed product output:

- [Source package script](https://github.com/cdin-editor/cdin/blob/main/scripts/package.py)
- [Pre-release metadata script](https://github.com/cdin-editor/cdin/blob/main/scripts/pre_release.py)
- [Stack build script](https://github.com/cdin-editor/cdin/blob/main/scripts/build_stack.py)
- [Product CI](https://github.com/cdin-editor/cdin/blob/main/.github/workflows/ci.yml)

A real product build must package the installed prefix/output of the exact successful target/profile build. Do not call a source-only package script and relabel its output as a binary distribution. Do not include only `src/`, `include/`, `CMakeLists.txt`, docs and tests in a file named as a Linux/Windows/macOS application asset.

### 7.2 Application package contents

The actual distribution layout must be defined by the product packaging implementation and platform needs. It must include, as applicable:

- The real CDIN executable for the target (for example `bin/cdin` or the platform executable).
- Required dynamic libraries or a verified system-dependency strategy.
- Runtime/Lua modules and resources needed after installation.
- The selected TUI or GUI-SDL runtime resources.
- The selected cdin-x bundle/assets.
- License and third-party redistribution notices.
- A machine-readable product package manifest.
- Per-asset/package SHA-256 checksums and release provenance.

The package manifest must identify product version, exact product source commit, target OS/architecture/ABI, profile, component versions, Registry source/Catalog/Manifest identity, workflow run and payload inventory. Values must be generated from the actual build/Manifest, not manually guessed.

Do not include development source trees, test binaries, compiler outputs, intermediate object files or build-system state unless a documented product package contract explicitly requires them.

### 7.3 Test the downloaded package, not merely the build directory

For every target/profile:

1. Download the exact release candidate package.
2. Verify its checksum and manifest inventory.
3. Extract it into a clean directory outside the source checkout and build tree.
4. Verify executable format and CPU architecture.
5. Verify all required dynamic dependencies.
6. Run the version command and supported product smoke check.
7. Start the application with only the extracted package and documented system dependencies available.
8. Verify runtime/resource discovery and the TUI or GUI-SDL startup path.
9. Verify clean shutdown, terminal restoration or GUI resource cleanup.
10. Confirm the package's product/component/Manifest identities match the workflow run.

A build-directory executable passing a test is not equivalent to testing the downloaded package. A package being non-empty or having a SHA sidecar is not proof that it is runnable.

## 8. Product release channels

CDIN has two intentionally different product release channels. These are product distribution policies; they do not change Registry's immutable component version rules.

### 8.1 Rolling development channel: fixed tag `latest`

Every successful push to `main` that passes the complete required product release matrix is eligible to update the rolling channel:

- Git tag/ref is exactly `latest`.
- The associated GitHub Release is marked `prerelease: true`.
- It contains the complete current set of real, verified TUI/GUI-SDL application packages for the targets the release declares supported.
- The release manifest identifies exact source commit, run, build profile, OS/architecture/ABI, component package versions, Registry Manifest identity, asset names, sizes and digests.
- The release represents one complete successful source commit. It must not contain a mixture of assets from multiple commits/runs.

The latest channel is mutable by design. It must not be confused with an immutable SemVer component release or with GitHub's "latest stable release" selection. Consumers that need this rolling product channel must use its exact tag/Release identity. Do not rely on GitHub's `/releases/latest` endpoint to find a prerelease channel.

A source push that has not passed every required target/profile gate must not move `latest`. A partial matrix must not publish a partial product. Preserve the previous known-good latest release if a new build, package inspection, upload, checksum, manifest validation or publication step fails.

Concurrent or delayed runs must not allow an older commit to overwrite a newer successful one. Serialize channel publication and check the candidate commit/run against the currently published channel before moving the tag or replacing assets. A fixed tag requires explicit safe ref-update logic; do not create a unique `v0.0.0-dev.<run>` tag as a substitute for the required `latest` channel.

GitHub Release asset replacement is not a single atomic multi-file operation. Design publication as a guarded transaction: finish and verify all target assets first; stage/upload the candidate asset set without deleting the prior working set; make the new release manifest the authoritative complete inventory only after every asset is present and verified; update the `latest` ref/release identity under a serialized freshness check; then perform safe cleanup of obsolete assets. Partial failures must leave a recoverable release state and must never advertise a mixed set as complete. Document how retry/repair handles each interruption point.

The existing Pipeline SemVer build-release helper may reject the literal tag `latest`. Inspect its actual reusable workflow interface. If there is no supported rolling mode, add a separate generic reusable rolling-release workflow/mode to [Pipeline](https://github.com/m-mdy-m/pipeline) or a deliberate backward-compatible extension there. Do not fake a SemVer tag, weaken SemVer version validation for stable releases or build CDIN's product through the source-only workflow.

### 8.2 Immutable versioned releases

Versioned releases use real SemVer tags, for example:

- `v1.0.0`
- `v1.1.0`
- `v1.1.1`
- `v1.1.1-alpha.1`
- `v1.1.1-beta.1`
- `v1.1.1-rc.1`

The tag must identify the exact source commit tested by the release workflow. Release notes must match the version's CHANGELOG section. Every declared build target/profile must succeed and every published package must pass post-download/extraction tests before publication.

Stable versions are non-prereleases; SemVer suffix versions are prereleases. A published version tag and its assets are immutable. Never move a version tag or overwrite the same version identity with different bytes. If a package or product changes, publish a new version according to SemVer and the release policy.

Do not publish CDIN stable just because component APIs are stable. Product stability requires all mandatory product gates to pass.

### 8.3 Choose the correct Pipeline workflow

- Use [Pipeline `release.yml`](https://github.com/m-mdy-m/pipeline/blob/main/.github/workflows/release.yml) for compiled/build product releases, with an explicit target matrix, artifact tests and E2E hooks.
- Use a separately supported rolling-release workflow/mode for the fixed `latest` tag/channel.
- Use [Pipeline `source-release.yml`](https://github.com/m-mdy-m/pipeline/blob/main/.github/workflows/source-release.yml) only for clearly labelled source-only releases.

CDIN's product release must pass actual build outputs to the compiled release workflow. A source archive may be published as an additional contributor asset, but it must not be the only asset of an application release.

Pipeline reusable workflow ref and helper-code ref must remain aligned. Follow the repository's current Pipeline pinning policy and the declared interfaces. Where the policy selects `m-mdy-m/pipeline@main`, use `pipeline-ref: main` consistently; do not combine different revisions unknowingly. Local developer tool revisions in `deps.lock` remain explicit and reproducible.

### 8.4 Credentials and permissions

Use explicit least-privilege GitHub Actions permissions and repository/organization secrets. Fail early if the required write credential is absent or cannot create/update the required tag and release assets. Do not log tokens. Do not infer write access from a YAML `permissions` declaration alone; inspect actual workflow logs and repository/organization Actions policy when GitHub reports 403 or integration permission errors.

A successful build is not a successful release. Report tag creation, Release publication, asset verification and actual download verification as separate outcomes.

## 9. Product capabilities and integration gates

CDIN owns product-level integration tests and capability gating. It does not reimplement component behavior. The exact component versions used by each test must be pinned in the Registry Manifest.

### 9.1 Product integration epic and priority work

Recheck live status and dependencies before each task. The primary tracked work includes:

- [CDIN #111 — Complete live editor integration and product release gates](https://github.com/cdin-editor/cdin/issues/111).
- [CDIN #118 — Live IME and PaneTree end-to-end tests](https://github.com/cdin-editor/cdin/issues/118).
- [CDIN #121 — Consume pinned Registry executable artifacts](https://github.com/cdin-editor/cdin/issues/121).
- [CDIN #122 — Artifact-first component installation](https://github.com/cdin-editor/cdin/issues/122).
- [CDIN #124 — Consume a pinned prebuilt SDL3 SDK](https://github.com/cdin-editor/cdin/issues/124).
- [Registry #53 — GitHub Release metadata discovery implementation](https://github.com/cdin-editor/registry/issues/53).
- [Runtime #16 — Runtime module package and release metadata](https://github.com/cdin-editor/runtime/issues/16).
- [Frontend #40 — Core/TUI/GUI-SDL package variants](https://github.com/cdin-editor/frontend/issues/40).
- [Backend #25 — Target-specific Backend packages](https://github.com/cdin-editor/backend/issues/25).

These links identify work items, not guaranteed current states. Query GitHub before starting or closing any issue. Some work may already be merged/closed or superseded. Do not recreate an existing issue or PR; update/cross-link the existing owner issue.

### 9.2 IME

Follow [Spec ADR-0023](https://github.com/cdin-editor/spec/blob/main/docs/adr/ADR-0023-ime-composition-contract.md) and its [shared conformance vectors](https://github.com/cdin-editor/spec/tree/main/docs/testing/vectors).

The live product path is:

`native input → Frontend composition state → negotiated Protocol messages → Backend validation/Driver and version checks → Runtime selection/commit → Kernel document mutation`

Verify start, update, local preedit, cancel, commit, exactly-once behavior, captured view/version/selection, focus loss, Escape, view/document switch, stale version, Driver revocation, detach/reconnect and shutdown. Preedit must not mutate canonical document bytes, document version or undo history. Only a successful committed text operation reaches Runtime/Kernel.

Do not advertise `ime-composition/1` unless Backend explicitly negotiates it and the exact selected Frontend/Backend/Runtime candidates pass shared conformance and CDIN live E2E. A capability declaration in source or metadata is not enough.

### 9.3 PaneTree splitter resize

Follow [Spec ADR-0024](https://github.com/cdin-editor/spec/blob/main/docs/adr/ADR-0024-pane-tree-splitter-resize.md) and its [shared vectors](https://github.com/cdin-editor/spec/tree/main/docs/testing/vectors).

Frontend owns divider hit-testing, pointer capture, pixel-to-basis-point conversion and local-only drag preview. Backend validates negotiated capability, Driver role, request bounds and exact layout revision. Runtime owns the semantic split ratio and revision update. Backend publishes the result and matching full UI snapshot/flush in the ordered bounded stream.

Test commit, cancellation, Escape, pointer/focus loss, observer rejection, stale revision, missing capability, unknown split, invalid ratio, nested split, duplicate/out-of-order result and layout replacement. A drag preview is not a committed semantic mutation.

Do not advertise `pane-splitter-resize/1` before the exact selected stack passes.

### 9.4 Semantic UI presentation

Follow [Spec ADR-0026](https://github.com/cdin-editor/spec/blob/main/docs/adr/ADR-0026-ui-presentation-contract.md), [UI Model v1](https://github.com/cdin-editor/spec/blob/main/docs/architecture/ui-model-v1.md) and [presentation vectors](https://github.com/cdin-editor/spec/blob/main/docs/testing/vectors/ui-presentation-v1.json).

Runtime owns style meaning, semantic panel/widget values and command policy. Backend validates and projects the model. Frontend renders it. Every message in a snapshot group must match the root revision and must be committed atomically at the matching `ui.flush`. Malformed/stale groups leave the previous valid snapshot intact. Widget activation uses the normal command path, with Backend Driver authorization and Runtime command validation; Frontend must not execute editor commands itself.

### 9.5 Byte-anchored visible line windows

Follow [Spec ADR-0027](https://github.com/cdin-editor/spec/blob/main/docs/adr/ADR-0027-byte-anchored-visible-line-windows.md) and [byte-anchored vectors](https://github.com/cdin-editor/spec/blob/main/docs/testing/vectors/byte-anchored-lines-v1.json).

Runtime owns byte scroll anchors. Backend resolves anchors and reads the actual returned bytes from the same immutable Kernel snapshot. Frontend uses byte metadata to maintain its bounded cache and must not infer byte positions by counting UTF-8 code points, graphemes or rendered glyphs. Preserve LF/CRLF/CR, NUL, invalid UTF-8, EOF and trailing-empty-line semantics. Reject stale responses.

### 9.6 Unicode and Persian/Arabic

The product UI must not claim Unicode support merely because it can display basic UTF-8 or ASCII. Validate real shaping, grapheme handling, combining marks, wide characters, font fallback, bidi, hit-testing, cursor stops, selection, wrapping and scrolling. Persian, Arabic and mixed-direction content are required product acceptance cases. Rendering must not normalize or alter canonical document bytes.

Select/pin any text shaping or font dependency only after assessing cross-platform support, reproducibility, licensing, ABI and package availability. Do not add unrelated GUI frameworks or unnecessary dependencies.

### 9.7 Lifecycle, editing and recovery

Use the actual product E2E suite: [CDIN tests/e2e](https://github.com/cdin-editor/cdin/tree/main/tests/e2e). Verify startup/shutdown, terminal restoration, GUI resource cleanup, document create/open/edit/save/reopen, undo/redo, keymaps, paste, search/navigation, multiple views, panes, Driver/Observer roles, detach/reattach, reconnect, Backend/Runtime failure, extension lifecycle and recovery.

Document fixtures must cover embedded NUL, BOM, invalid UTF-8, LF, CRLF, lone CR, final newline/no final newline, combining characters, emoji, Persian/Arabic and mixed direction. Compare exact bytes after save/close/reopen. No renderer may silently rewrite canonical document data.

## 10. Cross-platform target policy

Verify the actual supported target set against the current releases, SDKs, compilers, ABI and component packages before enabling a matrix target. The currently maintained native target family has included:

- Linux x86_64.
- Linux ARM64.
- macOS x86_64.
- macOS ARM64.
- Windows x86_64 using the UCRT64 toolchain.

TUI and GUI-SDL are separate product profiles. A target is supported only when every required component package/SDK exists for that exact OS/architecture/ABI, the final product package has the correct dependency closure, and the extracted package passes its product tests.

Do not infer ABI compatibility from `linux`, `windows`, `x86_64` or a compiler label alone. Preserve the exact libc/deployment baseline and Windows toolchain identity required by each package contract.

Run applicable strict compiler warnings, ASan, UBSan, leak detection and TSan on the supported runners. Clearly mark tests that cannot run on a particular OS/runner. A skipped job is not a pass.

## 11. Tooling, task graph and logging

Use the established tooling:

- [Pipeline](https://github.com/m-mdy-m/pipeline) for project task definitions and shared CI/release workflows.
- [PSX](https://github.com/m-mdy-m/psx) for repository structure/project convention checks.
- [GIX](https://github.com/m-mdy-m/gix) for Git branch workflow.
- [log.c](https://github.com/m-mdy-m/log.c) for standalone C logging through the correct CDIN-owned integration boundary.

Pipeline task definitions are the source of truth. CI workflows should invoke Pipeline-defined tasks instead of duplicating build/test commands. Keep local and workflow task names aligned. Run the same checks locally where the environment supports them.

Keep tool identities pinned in `deps.lock` unless the repository's explicit shared-workflow policy says otherwise. A moving reusable workflow ref and a different helper-code ref must never be combined accidentally.

Use CDIN's own truthful log prefix (for example `[CDIN]`). Do not emit fake Backend/Runtime/Frontend/Kernel events under their names, and do not introduce Kernel logger dependencies. Never log credentials, full document content or sensitive file contents. Follow the actual logger contract and configured redaction policy.

## 12. Documentation and source references

All source comments, AGENTS instructions, repository documentation, README and CHANGELOG content in this project are written in English.

When implementing an architectural rule, cite the exact normative Spec URL and requirement/ADR. Use precise links including section anchors or line anchors where available. Verify the current target file and line range before adding a source comment; do not invent a line number or point at a stale filename.

Update the documentation that owns the change:

- Product architecture and ownership: [CDIN traceability](https://github.com/cdin-editor/cdin/blob/main/docs/architecture/traceability.md).
- Product dependencies and package selection: [dependency matrix](https://github.com/cdin-editor/cdin/blob/main/docs/development/dependency-matrix.md).
- Registry invocation and workspace handoff: [Registry integration](https://github.com/cdin-editor/cdin/blob/main/docs/development/registry.md).
- Current cross-repository readiness: [integration status](https://github.com/cdin-editor/cdin/blob/main/docs/development/integration-status.md).
- Product test inventory: [E2E README](https://github.com/cdin-editor/cdin/blob/main/tests/e2e/README.md).
- User installation: [installation guide](https://github.com/cdin-editor/cdin/blob/main/docs/installation.md).
- Developer workflow: [development guide](https://github.com/cdin-editor/cdin/blob/main/docs/development.md).

Keep README, CHANGELOG, package/release docs, dependency matrices, Product Definitions and status docs synchronized with the current implementation. Preserve historical records. Do not manually edit generated reports; fix their source or generator and regenerate them.

Documentation must clearly distinguish:
- Product version, component package version, ABI/API/Protocol version, Spec version and Registry Data Contract version.
- Latest stable Spec tag versus newer Spec default-branch changes.
- Source archive versus installable component package versus final CDIN application distribution.
- Component release versus product release.
- Rolling CDIN `latest` prerelease versus immutable SemVer release.
- CI build success versus release publication success versus clean-install/product E2E success.
- Accepted capability contract versus capability actually implemented and negotiated.

## 13. Git, issues and pull requests

- Work on a focused feature/docs/fix branch created from the current default branch head.
- Do not commit directly to protected `main`.
- Do not force-push, rewrite shared history, or move an immutable SemVer tag.
- Keep component-owned changes in their component repository; CDIN-only composition/packaging/integration work belongs here.
- Split independent concerns into separate reviewable commits/PRs.
- Use semantic commit messages describing the actual diff, for example:
  - `build(cdin): package verified TUI distributions`
  - `fix(cdin): preserve latest release on matrix failure`
  - `feat(cdin): consume artifact-delivered frontend packages`
  - `docs(cdin): document product release channels`
- Link relevant Spec requirements/ADRs, owner issues, dependent issues and exact CI evidence in PRs.
- Update issue acceptance criteria with real evidence. Do not close an issue because its PR merged unless all acceptance criteria have passed.
- Do not mass-close historical issues. Close only completed or genuinely superseded issues, using the correct closure reason and a useful completion comment.
- Merge only a complete, reviewed PR whose required checks and repository merge requirements pass, and only when the current task's authorization permits merging. Never merge a failing/incomplete PR simply to clear a queue.

Before creating an issue or PR, search the owning repository for existing issues/PRs and inspect open/closed history. Reuse and update an existing tracking item where appropriate. Avoid duplicate Specs, ADRs or component tasks.

## 14. Implementation and test discipline

For every implementation slice:

1. Reconfirm current SHA, issue state and dependency versions.
2. Read the accepted Spec contract and relevant component public interface.
3. Make the smallest complete owner-correct change.
4. Add positive, negative and failure-path tests.
5. Run the declared Pipeline task(s) and relevant direct tests.
6. Inspect the actual generated binaries/packages/manifests/assets; do not trust filenames alone.
7. Verify the exact package from a clean extracted directory.
8. Update documentation, lock/Manifest inputs, traceability and issue acceptance criteria.
9. Open or update a focused PR.
10. Report the exact tested SHA and workflow links.

Never remove a regression test to make CI green. Never weaken schema validation, ABI/protocol checks, archive safety, cache verification or failure handling. Do not silently suppress errors or fall back to a different version/source after a selected artifact fails.

A workflow being defined, queued, skipped or successful on an older SHA is not evidence that the current SHA passed. Record actual run IDs, conclusions and tested head SHA. If the runner, credentials, permissions, signing keys or hardware are unavailable, report that exact blocker and do not simulate a passing result.

## 15. Definition of done

A CDIN product change is complete only when the appropriate subset of all these conditions is satisfied:

- The implementation is in the correct owning repository.
- The exact accepted Spec requirement/contract is followed.
- Public component identities and compatibility constraints are accurate.
- Product Definitions and the Resolved Manifest identify the exact selected components/artifacts.
- Artifact and source delivery behavior matches the declared Registry mode.
- Product build consumes the intended source/package paths without private component interfaces.
- The real application package contains the executable and required runtime files.
- Extracted-package tests pass outside the source checkout/build directory.
- TUI and GUI-SDL target/profile behavior is verified as applicable.
- Product E2E, security, failure/recovery and cross-platform checks pass.
- Release notes, checksums, metadata, tag and asset contents match the exact tested commit.
- Documentation and issues accurately describe what is and is not complete.

For product-wide readiness, use [CDIN #111](https://github.com/cdin-editor/cdin/issues/111) as the overarching acceptance gate. Do not close it until every mandatory product gate has exact-head evidence.

## 16. Prohibited shortcuts

Never:

1. Move Kernel, Runtime, Backend, Frontend, Registry or cdin-x implementation into CDIN.
2. Add private component includes or link to private component build directories.
3. Duplicate the document model, undo/redo, Runtime command/keymap policy, Backend session/Protocol authority, Frontend rendering or cdin-x manager.
4. Link Registry into the running application.
5. Clone/build Registry or component sources in the normal consumer installation path once artifact delivery is available and required.
6. Build SDL3 from source during normal GUI-SDL consumer installation.
7. Make TUI depend on SDL3.
8. Use floating component versions or floating Catalog identity in a reproducible Manifest.
9. Use GitHub `/releases/latest` as the ADR-0028 component metadata discovery algorithm.
10. Use publication time/API order instead of SemVer resolution.
11. Add new tracked `registry/releases/<component>-<version>.json` documents for component version metadata after migration to ADR-0028. Generate and upload metadata Release Assets instead.
12. Mix static Catalog `entries` with `release_sources` in one Catalog document.
13. Mutate historical metadata, published SemVer tags or immutable artifact identities.
14. Publish a source-only archive under a filename/description that claims to be an executable product distribution.
15. Publish a partial target matrix as a complete `latest` or versioned release.
16. Let a delayed older run overwrite the newer `latest` release.
17. Enable optional capabilities before the exact compatible component stack passes shared conformance and product E2E.
18. Claim Persian/Arabic/Unicode rendering from ASCII/basic UTF-8 smoke tests.
19. Delete tests, weaken validation or hide skipped/failed CI jobs.
20. Close unrelated issues or advertise stable product readiness without evidence.

## 17. Required engineering report

For every substantial task, report:

- Repository, branch, exact source SHA and issue/PR.
- Spec source/tag, relevant requirement IDs, ADRs and contract/schema versions.
- Files/modules changed and ownership rationale.
- Commands/Pipeline tasks and tests actually executed.
- Exact CI run links, conclusions and tested SHA.
- Component package/Registry Manifest/Product Definition identities affected.
- Actual release tags/assets and whether the downloaded package was inspected.
- Remaining failures, skipped gates, permissions or runner blockers.

Keep the final status separated into IMPLEMENTED, TESTED, RELEASED, INTEGRATED and PRODUCT READY. Do not convert plans, source-level behavior or old CI results into completion claims.
