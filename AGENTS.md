# AGENTS.md — CDIN Composition Root Engineering Rules

## Mission and repository identity

Repository: https://github.com/cdin-editor/cdin

CDIN is the product Composition Root for independently maintained editor components. It assembles, verifies, configures, builds, packages, launches, upgrades and releases the product through public, versioned contracts.

CDIN is not the owner of Kernel, Runtime, Backend, Frontend, Registry or the extension catalog implementation. Do not move their responsibilities into this repository.

The product has distinct TUI and GUI-SDL profiles. A green component CI job or a successfully built preview is not proof that the complete CDIN product is usable.

These instructions apply to all work in this repository. The current default branch is `main`; do not assume a historical feature branch is still the active integration branch.

## 1. Source of truth and current architecture

Before implementation, inspect the current default branch and the latest authoritative Spec source and release. Read the relevant accepted ADRs, normative requirements, schemas, conformance fixtures and component public contracts.

Important architecture sources include:

- Spec: https://github.com/cdin-editor/spec
- Registry architecture: https://github.com/cdin-editor/spec/blob/main/docs/architecture/registry.md
- Registry data contracts: https://github.com/cdin-editor/spec/blob/main/docs/architecture/registry-contracts.md
- Immutable artifact delivery: https://github.com/cdin-editor/spec/blob/main/docs/architecture/immutable-artifact-delivery.md
- ADR-0028, GitHub Release metadata discovery: https://github.com/cdin-editor/spec/blob/main/docs/adr/ADR-0028-github-release-metadata-discovery.md

ADR-0028 was accepted through Spec PR #38. Spec issue #37 tracks its completion across Registry and component publishers. Registry implementation is separately tracked by Registry issue #53. Verify the current state of those items before relying on them; an accepted Spec contract does not prove that the Registry implementation or every publisher has shipped.

The latest stable Spec release observed on 2026-11-10 was v1.4.0. The default branch may contain newer accepted source changes than that tag. Always distinguish the latest stable tag from the default-branch source.

When requirements and implementation disagree:

1. Identify the exact requirement, implementation and public contract involved.
2. Check the current Spec source and the relevant tagged release.
3. Check the actual component source, public headers, release metadata and published assets.
4. Record the discrepancy and its owner.
5. Do not silently reinterpret a contract or claim unsupported behavior.

Use accurate implementation states: ACCEPTED, PROPOSED, IMPLEMENTED, PARTIAL, DEFERRED, NOT IMPLEMENTED and NOT VERIFIED. Documentation, a release tag, a unit test, or a merged PR alone does not establish product integration.

For each product capability, preserve traceability:

`Spec requirement → owning repository → implementation → test → exact CI evidence → published package/release identity → CDIN integration`

Do not invent requirement IDs, source anchors, test results, package versions or release identities.

## 2. Repository ownership and dependency boundaries

The repositories have separate ownership:

- **Kernel** owns canonical document bytes, editing operations, versions, snapshots, transactions, undo/redo and document-level search.
- **Runtime** owns Lua 5.4 editor policy, commands, keymaps, logical views, configuration, extension lifecycle and semantic editor state.
- **Backend** owns Kernel integration, Runtime hosting, OS services, sessions, Frontend Protocol server, transport, sequencing, queues and backpressure.
- **Frontend** owns physical input adaptation, terminal/window resources, pixel/cell geometry, text presentation, presentation caches and rendering. TUI, GUI-SDL and Headless are peer adapters.
- **Registry** owns generic component release discovery, version/dependency/contract resolution, metadata validation, immutable source/artifact delivery, cache, Resolved Manifest and replay.
- **cdin-x** owns the extension ecosystem, plugin packages, themes, fonts, bundles and manager behavior according to its extension contract.
- **Spec** owns normative requirements, architecture decisions, schemas and conformance fixtures.
- **CDIN** owns product composition, Product Definitions, environment provisioning, build/install orchestration, component integration, application lifecycle, product-level tests, final application packaging and product release workflows.

Enforce these boundaries:

- CDIN must not implement editor-domain behavior already owned by a component.
- Kernel must not depend on Backend, Runtime or Frontend.
- Backend is the component that integrates Kernel directly.
- Runtime must access document operations through Backend's public Host API, not private Kernel APIs.
- Frontend must use the public Frontend Protocol and must not access private Backend, Runtime or Kernel implementation details.
- Registry is a build-time/delivery-plane tool. It is not linked into the running editor and is not an application runtime dependency.
- CDIN may compose public component packages and satisfy explicitly declared environment contracts. It must not copy component implementation or use private headers.
- No circular dependency, hidden source checkout, implicit ABI bypass or duplicate ownership.

The source-based stack builder may remain as an explicit developer/CI verification path while the migration is incomplete. It must not be confused with normal consumer installation or with a published installable package.

## 3. Logging and shared tooling

Use the standalone `m-mdy-m/log.c` logger through the CDIN-owned diagnostics boundary. Do not use a Kernel logger or introduce a Kernel dependency merely to log. Keep component-specific prefixes and ownership truthful; CDIN must not impersonate another component's logger.

Use the established projects according to their actual interfaces:

- Pipeline: https://github.com/m-mdy-m/pipeline — local task graph and reusable CI/release workflows.
- PSX: https://github.com/m-mdy-m/psx — repository structure and project conventions.
- GIX: https://github.com/m-mdy-m/gix — Git workflow and repository health.
- log.c: https://github.com/m-mdy-m/log.c — standalone logging.

Pipeline task definitions are the source of truth for repository tasks. CI must call the declared Pipeline tasks rather than maintaining a second, divergent list of build/test commands.

Keep tool dependencies reproducible. Honor immutable revisions in `deps.lock` for locally installed tool binaries/libraries. For reusable Pipeline workflow references, follow the repository's current policy; the project prefers tracking `m-mdy-m/pipeline@main` and passing `pipeline-ref: main` where supported. Do not silently mix a moving workflow ref with a different helper revision.

Keep the current compiler, CMake, Go, Python, Lua, SDL and platform requirements explicit and synchronized with actual code and lock files. Do not upgrade or repin dependencies without checking compatibility and updating tests/documentation.

## 4. Registry integration and metadata discovery

### 4.1 Use the accepted GitHub Release metadata contract

Do not add new tracked per-version files such as:

`registry/releases/backend-1.2.1.json`

or require a new source commit for every package version solely to add release metadata.

Under accepted Spec ADR-0028 / Registry Data Contract 1.4.0, a component publisher generates its Component Release Metadata from the exact tagged release commit and uploads it as an asset of that GitHub Release:

- Default variant: `<component-id>-<version>.json`
- Non-default variant: `<component-id>-<variant>-<version>.json`

Examples: `backend-1.2.1.json`, `frontend-tui-1.1.0.json`, `frontend-gui-sdl-1.1.0.json`.

The generated JSON is a Release Asset, not a committed source-tree file. It must describe the exact tag, full resolved commit SHA, source unit, contracts, dependencies and artifacts produced by that release. It must carry the required `publication` declaration. It must not include its own URI or digest; GitHub Release Asset API metadata supplies those values after upload.

For a metadata asset that also describes binary/module artifacts, calculate every artifact's exact final byte size and SHA-256 after packaging. Include the immutable release asset URI, filename, target, format, layout, source provenance and build/toolchain provenance required by the accepted schema. Never publish placeholder digests, guessed sizes or unverified target labels.

Existing checked-in metadata and static Catalog entries remain a backward-compatible migration path. Do not mutate previously published metadata or historical release identities. Do not create more tracked per-version metadata documents for new releases. Remove legacy files only when the migration plan, historical compatibility and all consumers have been verified.

### 4.2 Catalog Release Sources and Registry discovery

A Catalog may use either the legacy static `entries` model or the accepted `release_sources` model. A single Catalog document must not mix the two models.

A Release Source is a stable mapping declared once per component/variant/repository; versions are discovered from GitHub Releases. Do not manually add one Catalog entry for every new component version when the release-source model is available.

Registry must remain generic and consumer-independent. Do not hardcode CDIN product IDs, component repository names or product-specific policies into Registry. CDIN supplies declarative Product Definitions, exact product requirements and the configured Catalog source.

The accepted discovery contract requires complete, bounded, paginated GitHub Release enumeration. It explicitly forbids use of the floating `/releases/latest` endpoint as the resolver. Do not select a package by release publication timestamp, API page order, or whichever release happens to be returned first.

Selection must use SemVer and the existing Product Definition prerelease policy. Drafts are excluded. Prereleases are considered only when permitted. The exact metadata asset must be uniquely present and its API digest and byte size must be verified before parsing.

The Registry must validate that the tag, tag-resolved commit, metadata version, source repository and publisher source-unit revision all agree. A moved tag, mismatched prerelease flag, missing/duplicate asset, missing API SHA-256, digest/size mismatch, incomplete pagination or ambiguous equal-precedence identity must fail deterministically. Never fall back to source to hide a corrupt or unavailable artifact that was selected.

Successful resolution and replay must be immutable. The Resolved Manifest must record the exact release source, GitHub Release ID/API identity, tag, resolved commit, metadata asset name/URI/size/digest and selected component artifact identities. Replay must use those recorded identities and must not discover a newer release.

The configured discovery/cache limits must be finite. Offline resolution may use only previously verified cache data bound to the exact Catalog Release Source identity. An unavailable or stale cache must fail clearly.

Follow Spec issue #37, merged Spec PR #38 and Registry issue #53. Verify current Registry implementation and tests before enabling the dynamic Catalog model in CDIN. Do not duplicate the Spec work or assume the Registry implementation has already landed.

### 4.3 Source and artifact delivery modes

Use the Registry delivery modes defined by the selected contract:

- `source`: collect the exact immutable source revisions.
- `artifact`: require a compatible artifact for every selected component.
- `artifact-or-source`: use a compatible artifact when declared; fall back to source only if no compatible artifact is declared.

A selected artifact that fails download, size/digest validation, safe archive validation or extraction must fail closed. It must not trigger source fallback.

For native artifacts, target selection must specify exact OS, architecture and ABI. Do not substitute another architecture, libc, ABI or toolchain silently. A universal package is valid only where the contract explicitly permits the `any/any/none` target.

Registry prepares and verifies the workspace. It does not execute package scripts, build components, run their tests or decide whether the product works.

## 5. CDIN bootstrap, component installation and build

The normal consumer path must be artifact-first when the pinned release set and accepted contracts make that possible. It must not require the consumer to clone/build Registry, Runtime, Backend, Frontend or SDL3 from source. It must not install Go just to obtain the Registry executable.

Kernel and logger must use their existing published dependency artifacts and contracts. Do not create duplicate Kernel/logger packaging projects. Lua 5.4 remains an explicit Runtime environment requirement. Backend's external Kernel ABI, logger C API and Lua requirements must be declared and satisfied through their actual public contracts.

CDIN's Registry adapter and build orchestration must understand both source-delivered and artifact-delivered workspace layouts during migration:

- Source delivery is built from the exact collected source paths.
- Artifact delivery consumes the extracted package prefix and its public CMake/pkg-config exports or module layout.
- Runtime module archives are staged into the correct Lua module tree.
- Native dependencies are configured through public imported targets and explicit environment contracts.
- Common packages such as Frontend Core are resolved and installed once, even when more than one adapter is selected.
- TUI must not acquire or link SDL3.
- GUI-SDL may include the TUI fallback only when the Product Definition requires it.
- No component's private source paths may leak into an installed consumer package.

Keep separate, clearly documented paths:

1. Normal consumer installation: verified immutable component artifacts, Registry Manifest/replay, and the product-owned integration/build steps.
2. Developer/CI source build: explicit source checkout/build path for component development and verification.

Do not hide source builds behind ordinary consumer installation commands. Do not claim artifact-first installation until clean-machine, warm-cache and offline tests prove it.

Use secure staging and atomic publication. Verify artifact digest, size, target, package layout and contract identity before use. Reject traversal, absolute paths, symlink/hard-link escapes, special files, collisions, oversized archives and malformed metadata. A failed update must not overwrite a functioning installation. Keep rollback/recovery and cache identities tied to immutable digests.

## 6. Product build outputs are not source archives

A source snapshot is useful for contributors, source review and source reproducibility. It is not an installable CDIN application.

Never name a source-only archive as though it were a built target distribution. In particular, a file named like `cdin-*-linux-x86_64-tui` or `cdin-source-snapshot-Linux-tui` must not silently contain only the source tree and documents.

The CI build must retain the real installed product output from the exact successful build. The product packaging step must package the installed prefix and every required runtime resource/library for the selected target/profile. It must not call the source snapshot packager and relabel that output as a binary.

A product distribution must contain, as appropriate to the target and approved layout:

- The real CDIN executable and any required application binaries.
- Required shared libraries or a documented, verifiable platform dependency strategy.
- Runtime modules and resources required for startup.
- TUI or GUI-SDL-specific resources.
- The extension bundle when selected by the Product Definition.
- Licenses and notices for redistributed content.
- A machine-readable build/package manifest identifying product version, exact source commit, target, profile, selected component versions, Registry Manifest digest, build workflow/run and package file inventory.
- SHA-256 checksums and provenance/attestation when supported by the release configuration.

Do not bundle development-only files, component source trees, test binaries or build-system state into a consumer distribution unless a documented package contract explicitly requires them.

For each target/profile, verify the package after downloading/extracting it into a clean directory with no repository checkout and no build tree on the search path. Test executable presence and architecture, dynamic dependency closure, version reporting, startup/smoke behavior, resource discovery, clean shutdown and checksum/manifest consistency.

Keep source archives as separately named optional assets. They must never be the only product assets when the release is presented as an installable application release.

## 7. CDIN release channels: rolling `latest` and immutable SemVer releases

There are two distinct product release channels. Do not conflate them.

### 7.1 Rolling main-branch channel

Every successful push to `main`, after all mandatory product CI and release-target gates pass, must be eligible to publish the rolling development channel:

- Git tag: exactly `latest`.
- GitHub Release: `prerelease: true`.
- Release contains the complete, current set of verified CDIN product assets for the supported target/profile matrix.
- Release metadata identifies the exact commit, workflow run, build profiles, target matrix, selected component versions and Registry Manifest identities.
- New assets replace the previous asset set for this one mutable channel; stale assets from older builds must not remain and masquerade as current.
- A failed or incomplete matrix must not move the tag, replace the Release assets or destroy the previous working `latest` release.
- Concurrent or delayed runs must not allow an older commit to overwrite a newer successful `latest` build. Serialize publication and compare the candidate commit/run against the currently published channel before moving the tag or replacing assets.
- The tag/ref update and Release asset update must be handled as one guarded publication procedure with recoverable failure behavior.

The fixed `latest` tag is intentionally mutable and is not a SemVer package identity. Its manifest must always bind the exact commit and digest of each included package.

Do not create a unique `v0.0.0-dev.<run-number>` tag for every main push as a substitute for the requested `latest` channel. Do not use GitHub's floating `/releases/latest` endpoint to retrieve this prerelease: GitHub's stable-latest release semantics exclude prereleases. Consumers must identify the rolling channel by its exact tag/release identity.

The current Pipeline SemVer release workflow may reject a literal `latest` tag. Do not bypass its validation by inventing a fake version. If it does not support a rolling channel, add a clearly separate reusable rolling-release mode/workflow to Pipeline, or make a deliberate backward-compatible Pipeline extension. Reuse the same build matrix, artifact testing, assembly, checksums and provenance mechanisms wherever possible. The source-only reusable workflow must not be used to publish the CDIN application.

### 7.2 Versioned releases

Stable and versioned prerelease releases use immutable SemVer tags, for example:

- `v1.0.0`
- `v1.1.1`
- `v1.1.1-alpha.1`
- `v1.1.1-beta.1`
- `v1.1.1-rc.1`

A versioned release must:

1. Refer to the exact source commit that passed the required gates.
2. Have a valid version/changelog section and release notes.
3. Build every required target/profile from that exact tag commit.
4. Run tests on each built package after extraction.
5. Verify checksums, build metadata, package contents and dependency closure.
6. Publish the complete asset set only after the full matrix succeeds.
7. Mark stable versions as non-prerelease; mark SemVer prereleases as prerelease.
8. Never move an existing published version tag or silently overwrite its assets with different bytes.

A component's API/ABI stability does not automatically make the CDIN product stable. Do not publish a stable product version until all mandatory product release gates pass.

### 7.3 Pipeline workflow responsibilities

Use the compiled/build release workflow from `m-mdy-m/pipeline` for versioned binary/product releases, with explicit build matrix, artifact testing and E2E hooks. Use the rolling-release workflow/mode for the fixed `latest` channel. Use `source-release.yml` only for clearly identified source-only releases.

The release workflow must collect actual build artifacts from every configured matrix target. Do not supply a source archive as the only `artifact-path` for a product build. The configured artifact test must inspect the actual downloaded/extracted distribution.

The shared Pipeline workflow reference should follow the current CDIN policy for `m-mdy-m/pipeline@main` and `pipeline-ref: main` where compatible. Validate the shared workflow contract before changing callers. Do not locally reimplement Pipeline's generic release orchestration in CDIN.

GitHub Actions credentials must be explicit and least-privileged. If tag/ref updates or Release publication require a dedicated repository secret/token, report the exact required permissions and fail early when missing. Never expose credentials in logs. Do not treat a successful CI build as successful publication.

## 8. Product profiles and supported targets

Maintain separate product profiles:

- **TUI:** no SDL3 download, configure, link or runtime dependency.
- **GUI-SDL:** the selected GUI-SDL adapter and its required prebuilt SDL3 SDK/runtime dependencies; include TUI fallback only where the Product Definition requires it.

Validate the actual supported target matrix against current component and SDK releases. The observed native matrix has included:

- Linux x86_64.
- Linux ARM64.
- macOS x86_64.
- macOS ARM64.
- Windows x86_64 UCRT64.

Do not claim support for a target that has no compatible component packages, SDK, compiler/runtime closure and successful product test. Keep architecture, OS, ABI/libc and Windows toolchain identity explicit.

The GUI-SDL profile must consume the exact, verified prebuilt SDL3 SDK package where the accepted integration is ready. Normal consumer installation must not build SDL3 from source. An explicitly named developer-only source build may remain for SDK development.

## 9. Product behavior and verification

The Composition Root must verify real cross-component behavior through public interfaces. A mock, preview executable, source-only CI snapshot, or isolated component unit test is not sufficient evidence for product readiness.

Prioritize the accepted product issues and dependencies. Recheck current issue/PR status before acting. Relevant tracked work includes:

- CDIN #111 — overarching live product integration/release gates.
- CDIN #118 — live IME and PaneTree integration.
- CDIN #121 — prebuilt/pinned Registry executable distribution.
- CDIN #122 — artifact-first component installation.
- CDIN #124 — prebuilt SDL3 SDK consumption.
- Registry #53 — GitHub Release metadata discovery implementation.
- Runtime #16 — Runtime module release asset and metadata publication.
- Frontend #40 — Core/TUI/GUI-SDL package variants and metadata publication.
- Backend #25 — Backend target packages and dependency contracts; verify its current state before doing work.
- Spec #37 / PR #38 — accepted GitHub Release metadata discovery contract.

Do not duplicate completed or merged work. A closed issue or merged publisher PR does not prove that CDIN consumes the resulting package.

The product-level verification matrix must include, as applicable:

- TUI and GUI-SDL on supported operating systems/architectures.
- Startup, shutdown, terminal restoration and GUI resource cleanup.
- Real document open/create/edit/save/reopen.
- Exact document-byte preservation, including NUL, BOM, invalid UTF-8, LF, CRLF, lone CR, final empty line, emoji and combining characters.
- Undo/redo and Runtime command/keymap flow.
- Frontend protocol/session lifecycle and failure recovery.
- IME start/update/cancel/commit, with exactly-once commit and no preedit document mutation.
- PaneTree splitter authorization, drag preview, commit, cancellation and stale revision rejection.
- Byte-anchored visible-line windows and stale response rejection.
- Extension lifecycle, trust/capabilities, resource limits and failure cleanup.
- Unicode shaping, bidi and mixed-script text; Persian and Arabic are required acceptance cases for GUI rendering.
- Clean-machine package install and launch.
- Warm-cache and offline install/replay.
- Upgrade, failed-upgrade rollback, uninstall and user-data preservation.
- Archive security and checksum/identity failures.
- ASan, UBSan, leak detection and TSan where supported.
- Product performance workloads and documented measured budgets.

Do not advertise IME, splitter, Unicode, extension or artifact-first capabilities until the exact selected immutable component versions pass the complete live path.

## 10. Documentation and source comments

Write source comments, project documentation, READMEs and this file in English.

Explain purpose, ownership, invariants and non-obvious decisions. Important architecture implementation comments should cite the exact Spec requirement and actual source location. Inspect the current Spec before adding an ID or line anchor; never guess.

Keep current documentation honest about:

- Latest stable Spec tag versus newer default-branch Spec source.
- Component package versions versus API/ABI/Protocol versions.
- Published release assets versus development candidates.
- Source archive versus installable artifact.
- Source-based developer build versus artifact-first consumer installation.
- Rolling `latest` channel versus immutable SemVer release.
- Component-level verification versus full product-level verification.

Keep README, CHANGELOG, release notes, dependency/version matrices, Product Definitions and status documents synchronized with actual code and published assets. Preserve historical changelog entries and published identities.

## 11. GitHub issues, branches and pull requests

Before editing, inspect the current branch, commit, Git status, issue/PR history, review threads and affected tests. Preserve owner changes and generated-file conventions.

- Never commit directly to protected `main`.
- Create a focused branch from the current default-branch head.
- Do not force-push or rewrite public history.
- Do not move immutable version tags.
- Do not amend or retarget historical published metadata/assets.
- Keep independent repository ownership and unrelated fixes in separate PRs.
- Link the owning issue, Spec requirement and dependent repository work.
- Update issue acceptance criteria and post evidence-backed completion comments.
- Do not mass-close issues.
- Close an issue only when its actual requirements are implemented, merged and verified with exact-head evidence.
- Merge only when the PR's checks and repository merge requirements are satisfied and the task/owner authorization permits it. Do not merge a failing or unreviewed PR.

Use semantic commit messages, for example:

- `build(cdin): package verified TUI distributions`
- `fix(cdin): preserve previous latest release on matrix failure`
- `feat(cdin): consume artifact-delivered frontend packages`
- `docs(cdin): document product release channels`

Every commit message must describe the actual change.

## 12. Required execution discipline

Work autonomously within the accepted architecture. Do not stop after an audit or a plan when implementation work is authorized. Do not repeatedly ask for clarification when the next safe step is determined by the Spec, issue acceptance criteria and repository ownership.

For each work slice:

1. Recheck current repository/issue/PR state and exact source SHA.
2. Read relevant Spec, public component contract, current code and tests.
3. Write down the owning repository and compatibility requirements.
4. Implement the smallest complete change.
5. Add or update meaningful positive and negative tests.
6. Run the actual Pipeline task and relevant direct verification.
7. Inspect produced packages/assets, not just filenames or job summaries.
8. Update documentation, traceability and release metadata.
9. Open/update a focused PR and link exact CI evidence.
10. Report unresolved blockers honestly.

Do not remove tests, weaken validation, use fake success data, bypass ABI/protocol checks, or silently fall back to source builds. Do not claim an unrun check passed. If external permissions, secrets, native runners or hardware are unavailable, make the maximum verifiable progress and identify the exact blocker.

## 13. Completion criteria

CDIN is not release-ready merely because CI is green or individual components have releases.

The product work is complete only when:

- The Composition Root uses public, compatible component contracts.
- Registry executable and Catalog inputs are pinned and verified.
- Registry release-source discovery follows ADR-0028 and its implementation is available.
- Component releases publish generated metadata Release Assets and real installable packages.
- Product Definitions resolve exact component/variant versions and target artifacts.
- CDIN consumes package layouts correctly and does not require normal consumer source builds.
- TUI and GUI-SDL work through real integration paths.
- Product packages contain executable application outputs, runtime resources and valid dependency closure.
- Package extraction and clean-machine startup tests pass.
- The rolling `latest` release is a prerelease tied to the newest successful main commit and cannot be overwritten by stale/failed runs.
- Versioned SemVer releases are immutable, correctly classified and fully verified.
- Documentation, changelogs, release metadata and issue states match reality.
- Every mandatory product gate has exact-head passing evidence.

Report actual repository commits, changed files, commands, test results, workflow URLs, package/release identities and remaining blockers. Never present planned or unrun checks as results.
