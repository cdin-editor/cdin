## Current integration update — 2026-11-11 (post-merge release gate audit)

**Authoritative product status: DEVELOPMENT.** This section supersedes earlier 2026-11-11 snapshots. It records the state after the Runtime, Backend, Frontend and SDL3 publisher-preparation changes merged to their default branches. Publisher implementation and green component CI are not equivalent to a published immutable release, an artifact-first product install, or a usable application distribution.

### Current repository heads and release state

| Owner | Current `main` head | Immutable release state relevant to CDIN |
|---|---|---|
| Spec | `274f84f0ca08378db9c4a5cf6820065256f31d5a` | Latest stable tag remains Spec `v1.4.0`; current `main` contains subsequent Data Contract 1.4.0 clarification for withdrawn-release history and provenance-gated Resolution Report 1.2.0. |
| Kernel | `94e01ea0c6cf1c7ba6b796251bcf8ecd58d57a0f` | Kernel `v1.2.2` is published with Linux x86_64/ARM64, macOS x86_64/ARM64 and Windows x86_64 packages. |
| Runtime | `e7655862fc6d15fa8546e2bc6d6c792ce742903c` | Runtime PR [#25](https://github.com/cdin-editor/runtime/pull/25) merged RC3 preparation and canonical ADR-0028 publisher changes. No `v1.0.0-rc.3` tag/Release exists; RC2 is immutable and its old metadata asset name is non-canonical. Runtime [#16](https://github.com/cdin-editor/runtime/issues/16) remains open. |
| Backend | `1b07e4ebf1bbb1870167327b03ff18891490d1d7` | Backend PR [#38](https://github.com/cdin-editor/backend/pull/38) merged 1.2.2 release preparation, external consumer/version checks and ADR-0028 metadata generation. Published `v1.2.1` predates canonical metadata publication; no `v1.2.2` Release/metadata asset exists. Backend [#35](https://github.com/cdin-editor/backend/issues/35) remains open. Backend [#25](https://github.com/cdin-editor/backend/issues/25) is closed as completed based on its earlier package evidence; that does not complete #35. |
| Frontend | `688c981c31b4f891982b7a468470be6e2811a5b4` | Frontend PR [#49](https://github.com/cdin-editor/frontend/pull/49) merged Core/TUI/GUI-SDL variant release preparation for 1.1.1. Published `v1.1.0` remains a source-only release; no 1.1.1 target/variant packages or three canonical metadata assets exist. Frontend [#40](https://github.com/cdin-editor/frontend/issues/40) remains open/reopened. |
| Registry | `ff317e458a57dd9d8b8a2be8f7439ba860c99f10` | Generic ADR-0028 discovery is implemented and Registry [#53](https://github.com/cdin-editor/registry/issues/53) is closed. The only published executable Release is still `v0.1.0-dev`; Linux AMD64/ARM64 and macOS AMD64/ARM64 assets have duplicate digests and cannot be trusted as target-specific executables. Main identifies `0.2.0-dev.1`, but no matching Release exists. Registry [#58](https://github.com/cdin-editor/registry/issues/58) remains open for the five-target executable + same-commit Catalog/descriptor Release. |
| CDIN | `ea95b548f885a00d77bdc63bda13b6ae462924e5` | CDIN PR [#129](https://github.com/cdin-editor/cdin/pull/129) merged SDL3 SDK target ABI, static-link, license and real linked-version consumer verification. The five-target SDK matrix passed on its PR head; `sdl3-sdk-v3.4.16` tag/Release and SDK assets remain absent. CDIN [#124](https://github.com/cdin-editor/cdin/issues/124) remains open. |
| cdin-x | `bac35ff6ae25acad74875470a6feb24e7605cd0e` | `0.3.0` breaking-change documentation is on main; the published bundle release remains `v0.2.0`. |

### Product integration blockers

- **Registry executable (#121):** CDIN `deps.lock` still pins the old Registry source revision `cdcf86ed6a8788bf20fa0bcd821bb91242ba09a4`. `scripts/registry.py` clones Registry, requires Git and Go, runs `go test ./...` and builds the executable locally. It has no verified immutable Registry CLI/Catalog release pin. Do not replace this with the broken `v0.1.0-dev` assets or point at an unpublished `0.2.0-dev.1`.
- **Artifact-first components (#122):** `scripts/build_stack.py` still builds Kernel/Backend/Frontend from collected source and builds the CDIN composition root. The normal `make install` graph is therefore not yet a consumer artifact-first install. Runtime, Backend and Frontend canonical release metadata assets and artifacts must be published and consumed before product pins can move.
- **SDL3 SDK (#124):** the SDK producer is hardened and its five target-native build/consumer matrix passed on the PR head, but there are no published SDK Release assets. The current GUI developer build still downloads and builds the SDL source archive. TUI remains SDL-free.
- **Live IME/PaneTree (#118):** Product Definitions still pin Backend 1.2.0 and Frontend 1.0.2, and no RC3 Runtime or compatible immutable component set has been published. Keep IME composition and PaneTree splitter capabilities disabled/unadvertised until exact release metadata is pinned and live Driver/Observer E2E passes.
- **Product distribution (#111):** CDIN Releases are still the older `0.2.1-beta.*` series. There is no fixed `latest` rolling prerelease with verified runnable TUI and GUI-SDL product packages, nor a new immutable SemVer product release. Existing source snapshots are not application distributions.
- **User-facing editor readiness (#111):** the E2E documentation still records experimental TUI and GUI-SDL smokes, not supported release-ready interfaces. Full Unicode shaping, bidi and Persian/Arabic editing; complete multi-pane rendering; live extension permission/failure isolation; reconnect/process recovery; representative performance/soak baselines; and clean-machine install/upgrade/uninstall remain open.

### Current work in progress

- CDIN PR [#130](https://github.com/cdin-editor/cdin/pull/130) replaces the developer SDL3 source path's unrestricted `tarfile.extractall()` with the existing bounded extractor and adds traversal regression tests. It is a source-archive security fix, not completion of the prebuilt SDK consumer or #124.
- CDIN PR [#128](https://github.com/cdin-editor/cdin/pull/128) updates this status record; its status must remain synchronized with the merged release-preparation work and current CI evidence.

**Do not close #111, #118, #121, #122 or #124 on the basis of merged publisher code or a successful component CI run.** Each issue requires its own exact release, integration and acceptance evidence.

---

## Current integration update — 2026-11-10

**Authoritative current state:** the Composition Root foundation is on `main`; the component/asset merges below expand that foundation but do not complete the product/release epic.

- Composition Root PR #110 merged at `e2ea9f74bf247a1b1104cded53255ac4a34551a0`.
- Backend UI-presentation/1 validation PR [Backend #33](https://github.com/cdin-editor/backend/pull/33) merged at `785aedc1fc7d649e1e702bbaa700142683b5d1e6`. Its exact-head Linux/macOS/Windows protocol CI, Runtime integration, native stress (ASan/UBSan/TSan), quality and docs checks passed.
- Frontend byte-anchored line-window PR [Frontend #46](https://github.com/cdin-editor/frontend/pull/46) merged at `abcd1b087718b9c9fc866d38121c31222a7bc4f7`. This is a narrow transport/model capability, not completion of Frontend #15.
- CDIN SDL3 SDK producer PR [#126](https://github.com/cdin-editor/cdin/pull/126) merged at `f12f1fca4ca1d4fb5060a802549596085e3172d2`. On exact tested head `0e1a074311e0489662e6a2896d0c5aef6c459372`, all five target-native SDK builds and clean CMake consumer links passed; CDIN's seven CI jobs, seven pre-release product jobs, CodeQL and Pipeline quality passed. The main-branch push CI is separately running; the PR evidence is complete.
- SDL3 SDK release is **not yet published**. The publisher expects tag `sdl3-sdk-v3.4.16`; CDIN #124 remains open and `scripts/build_stack.py::install_sdl3` still downloads/extracts/builds the SDL source tarball.
- The artifact-first migration #122 remains **OPEN**. Registry #121 is blocked by the existing `v0.1.0-dev` executable assets having incorrect ARM mappings. Runtime #16 needs an immutable source/package identity decision because RC2 metadata pins an older source revision than current Runtime main; the pinned RC2 source also predates `package-modules.py` and `test-module-package.py`, so its original tag workflow cannot produce the new module artifact without an explicit external build-recipe change. Backend #25 needs its 1.2.1 binary assets/metadata; Frontend #40 still publishes source-only release archives instead of Core/TUI/GUI-SDL target packages.
- Do not advertise `ime-composition/1` or `pane-splitter-resize/1` on the currently pinned product candidates. CDIN #118 records the mismatch between Registry-selected immutable component source revisions and current component mainlines. New immutable Backend/Frontend/Runtime candidates and Product/Catalog pins must precede live product E2E.
- Product integration epic [#111](https://github.com/cdin-editor/cdin/issues/111) remains OPEN. The current issue body begins with the updated status correction; historical candidate sections are kept for traceability, not as current branch state.

The earlier verification sections below describe the 2026-11-08 Registry-integrated source-build candidate and remain historical evidence for that exact package/source set. They must not be interpreted as evidence that the artifact-first migration, IME/PaneTree product capability gates, or release packaging are complete.

---

## Current integration verification — 2026-11-08

**Status: VERIFIED INTEGRATION CANDIDATE.** CDIN Composition Root [PR #110](https://github.com/cdin-editor/cdin/pull/110) was merged to `main` at `e2ea9f74bf247a1b1104cded53255ac4a34551a0`. The exact tested source head was `a937947ce2a2ec06e6eed549672a585b10e2c3fb`; [CI run 42447891569](https://github.com/cdin-editor/cdin/actions/runs/42447891569) completed successfully.

### Immutable dependency set

The pinned Registry Catalog is `2a611eca830c0f235dacab04a1d006a8fd46e586`. It retains previous metadata identities and adds the immutable Frontend 1.0.1 TUI/GUI-SDL and Runtime RC2 entries.

| Component | Resolved package | Relevant contract |
| --- | --- | --- |
| Kernel | `1.2.1` | Kernel ABI `1.1.0` |
| Backend | `1.2.0` | Runtime Host API `1.0.0`; Frontend Protocol `1.0.0` |
| Runtime | `1.0.0-rc.2` | Provides `org.cdin.runtime-extension-contract@1.0.0` |
| Frontend TUI | `1.0.1` | Requires Frontend Protocol `1.0.0` |
| Frontend GUI-SDL | `1.0.1` | Requires Frontend Protocol `1.0.0` |

Backend's existing Runtime dependency range selects RC2. `allow_prerelease: true`
remains deliberate and transitional; do not switch to stable-only until a
stable Runtime package is published. Previously published Frontend 1.0.0 and
Runtime RC1 metadata, digests and source pins remain unchanged.

### Exact-head verification

All seven required jobs in [run 42447891569](https://github.com/cdin-editor/cdin/actions/runs/42447891569) passed:

- Linux, macOS and Windows TUI product profiles.
- Linux, macOS and Windows GUI-SDL + TUI fallback profiles.
- Full-stack AddressSanitizer, UndefinedBehaviorSanitizer and leak-detection job.

In each of the six native profile/OS jobs, the Registry CLI ran its Go suite,
Catalog/Product Definition schema validation, resolve, prepare, Manifest
replay, Manifest verification and workspace E2E. The resolver selected the
five exact package versions in the table above; older Frontend 1.0.0
candidates were rejected by the explicit 1.0.1 constraints. Runtime startup
logged `version=1.0.0-rc.2`, matching the Resolved Manifest, on Linux,
macOS and Windows in both profiles.

The native tests also passed the GUI-SDL live-session smoke, document
text/paste, undo/redo, atomic save, close/open and exact-byte persistence,
filesystem failure/recovery, byte-preservation fixtures, multi-session
Driver/Observer promotion, detach/reattach, abrupt peer loss with queued UI
work, same-session reconnect, lease reacquisition and exact Backend-owned
document content recovery. Compiler-resolved include checks found no private
component source/build headers. Full-stack ASan/UBSan/leak detection passed.

### Measured, but not release-grade, performance evidence

The CI benchmark runs ten iterations of the named `cdin --check`
headless-composition-root smoke and records p50/p95/p99 wall time plus sampled
peak RSS. It is not per-keystroke/input-to-visible or save latency, is not a
representative editing workload, and is not a soak or release baseline.
Allocator peak, operation-level budgets, repeatable editing workload and
documented soak/leak acceptance remain open in issue #111. Raw benchmark and
source-snapshot artifacts were attached to the native workflow.

### Remaining product/release gates

The CI success validates the integrated composition slice; it does not make
CDIN a stable editor release. Issue [#111](https://github.com/cdin-editor/cdin/issues/111)
remains open for FE-019 lost-wakeup/readiness and Windows CTRL-event stress,
supported non-experimental launch, live plugin capability/permission and
failure-lifecycle tests, Backend/Runtime process failure recovery, soak and
operation-level performance baselines, clean-machine application installers,
signed release artifacts and component Catalog publication automation.

The JavaScript/TypeScript CodeQL analyzer still reports no source on this
repository. C/C++, Python, Actions and the top-level CodeQL check pass; the
post-merge Default Setup language-selection adjustment is tracked in
[CDIN #113](https://github.com/cdin-editor/cdin/issues/113) and requires
repository Settings access. No fake JS/TS source or legacy website has been
reintroduced.

Cross-repository status: Runtime #7, Backend #19, Spec #16 and Spec #23 are
closed. Frontend #24 has its 1.0.1 package identity, immutable metadata,
Catalog entries and full CDIN matrix verified; its formal tag/release decision
remains open. Frontend #15 and Spec #14, #20, #21 and #25 remain open as
presentation, IME, splitter-resize and byte-anchor contract gates.

---

## Registry integration update — 2026-11-07
## Cross-repository version synchronization — 2026-11-08

The Registry Catalog snapshot pinned by this candidate is
`2a611eca830c0f235dacab04a1d006a8fd46e586`. It preserves the previous
immutable entries and adds:

- Backend `1.2.0` (existing)
- Kernel `1.2.1` (existing)
- Runtime `1.0.0-rc.2` with the provider contract
  `org.cdin.runtime-extension-contract@1.0.0`
- Frontend TUI `1.0.1`
- Frontend GUI-SDL `1.0.1`

The exact Frontend and Runtime metadata URI/digest pairs are stored in the
Catalog at that pinned commit. The Product Definitions select Frontend
`1.0.1`; Backend `1.2.0` resolves Runtime RC2 through its declared
dependency range. The Resolved Manifest remains authoritative for every
selected package and source revision. This sync PR deliberately does not
change Backend or Kernel package identities.

The exact current-head Linux/macOS/Windows TUI/GUI-SDL product matrix and
full-stack ASan/UBSan/leak job must pass before this cross-repository update
is accepted. A prior successful run against Frontend 1.0.0 / Runtime RC1 is
historical evidence only. Runtime prerelease selection remains enabled until
a stable Runtime release exists; it must not be disabled merely because RC2
is now selected.


The Composition Root implementation is merged to `main` in [PR #110](https://github.com/cdin-editor/cdin/pull/110) and uses the Registry-based component selection and source handoff described by [Registry integration](registry.md) and [Spec ROOT-010](https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md#L31-L31).

- Kernel, Runtime, Backend and Frontend own immutable release metadata in their component repositories. Frontend TUI and GUI-SDL are separately declared variants.
- CDIN contains only the TUI and GUI-SDL Product Definitions. The versioned Catalog Index now lives in the pinned Registry checkout at `catalogs/cdin-components/catalog-index.json`; the CDIN repository no longer stores component metadata URIs, repository URLs or a Catalog Index.
- The GUI-SDL product resolves both the TUI base adapter and GUI-SDL adapter, matching the current executable composition.
- Registry is pinned as a host build tool, runs its Go tests, validates the product/catalog documents, resolves and prepares sources, verifies and replays the Manifest. It is not a runtime dependency.
- Component versions and source revisions are read from the Resolved Manifest; component entries have been removed from `deps.lock`.
- The native CI matrix now includes TUI and GUI-SDL product profiles on Linux, macOS and Windows. The sanitizer job uses the GUI-SDL superset profile, exercising TUI, GUI-SDL and headless paths together.

**Status: VERIFIED INTEGRATION CANDIDATE.** The Registry pin and package selectors passed the exact-head six-job native matrix and full-stack ASan/UBSan/leak verification in [run 42447891569](https://github.com/cdin-editor/cdin/actions/runs/42447891569). The Runtime prerelease allowance remains transitional. A separate Catalog publisher/release publication workflow remains outstanding.

## Current verification update — 2026-11-07

PR #110 was merged to `main` on 2026-11-08 at `e2ea9f74bf247a1b1104cded53255ac4a34551a0`; its exact tested head was `a937947ce2a2ec06e6eed549672a585b10e2c3fb`.

- Frontend PR #19 is merged at `1373715c23eb965445caa926de3a99d9c0246f81`; Registry selects this immutable source through the Frontend Release Metadata referenced by its Catalog Index rather than a component entry in CDIN's `deps.lock`.
- Runtime sandbox capability-denial unit coverage is in Runtime commit `e2f19e279e3194a6615ce213331639fde4f42e87`; Runtime CI run [42315040626](https://github.com/cdin-editor/runtime/actions/runs/42315040626) passed Linux, Windows, macOS, Pipeline quality and docs/workflow validation.
- CDIN's trusted extension CLI and PTY/ConPTY fixtures were corrected after the prior run exposed invalid Python triple-quoted Lua source. Current CLI/PTY/ConPTY fixtures now use one line-continuation backslash; the accidental duplicate ConPTY source block and stale capability sentinel were removed.
- The multi-session smoke now verifies exact Backend-owned document bytes survive abrupt peer loss and a new Protocol client reconnecting to the same Backend session (commit `6eb58fd`). This test is not accepted until the current matrix passes.
- Current native + ASan/UBSan/leak matrix: [CDIN run 42447891569](https://github.com/cdin-editor/cdin/actions/runs/42447891569) passed all six profile/OS jobs and the full-stack sanitizer job on the exact tested head.
- Frontend SDL renderer device-loss recovery is verified in Frontend CI [42315157831](https://github.com/cdin-editor/frontend/actions/runs/42315157831); the broader GUI-SDL and IME release work remains open in [Frontend Issue #15](https://github.com/cdin-editor/frontend/issues/15).

The interactive TUI launch remains experimental/fail-closed. Do not mark FE-019, Windows ConPTY, plugin lifecycle/capability integration, document reconnect recovery, or product release gates complete until current CDIN test evidence is inspected.


# Integration status and release gates

This document reports capabilities exercised by the CDIN Composition Root, not merely features exposed by a component. A green component build does not prove that the complete editor is usable.

The product epic and acceptance criteria are tracked in [issue #111](https://github.com/cdin-editor/cdin/issues/111). The current integration candidate is developed on `feature/complete-composition-root-rewrite` through [PR #110](https://github.com/cdin-editor/cdin/pull/110), which remains Draft. The current branch includes the merged Frontend ConPTY correction and the immutable dependency pin recorded below.

## Current verification update — 2026-11-07

### Frontend ConPTY correction

- Frontend [PR #19](https://github.com/cdin-editor/frontend/pull/19) merged at `1373715c23eb965445caa926de3a99d9c0246f81`.
- Frontend CI [run 42312049293](https://github.com/cdin-editor/frontend/actions/runs/42312049293) passed all five jobs: Linux native TUI, macOS native TUI, Windows native TUI, SDL3 production adapter/installed consumer, and Pipeline quality.
- CDIN `deps.lock` pins that exact merge commit. The pin update is [commit ab9d854](https://github.com/cdin-editor/cdin/commit/ab9d85455c78200e2cccd7df50e5f65bbf70b6c9).
- CDIN full-stack + sanitizer verification for that exact pin is [run 42312594183](https://github.com/cdin-editor/cdin/actions/runs/42312594183). At the time of this document update, its Linux, macOS, Windows and ASan/UBSan/leak-detection jobs are still running. The Windows `cdin_tui_live_conpty_smoke` must pass before the cross-repository ConPTY gate is checked off.

### Current verified boundary

- The previous CDIN candidate passed the headless editing/persistence workflow, POSIX PTY, multiple Frontend Driver/Observer roles, detach/reattach lease reacquisition, byte-preservation fixtures, filesystem failure recovery, compiler-resolved include graph, reproducible source snapshot and Linux ASan/UBSan/leak detection in [run 42182694691](https://github.com/cdin-editor/cdin/actions/runs/42182694691).
- GUI-SDL live-session text input and exact-byte save smoke passed on Linux/macOS/Windows in [run 42310020078](https://github.com/cdin-editor/cdin/actions/runs/42310020078). That run used the prior Frontend pin and is not a substitute for the new run above. GUI-SDL remains experimental; complete PaneTree rendering, IME, shaping/bidi/Persian, device-loss recovery and full session recovery are still open.
- The previous CDIN ConPTY failure was isolated to the readiness wait using a different handle from the terminal adapter's `CONIN## Current integration verification — 2026-11-08

**Status: VERIFIED INTEGRATION CANDIDATE.** CDIN Composition Root [PR #110](https://github.com/cdin-editor/cdin/pull/110) was merged to `main` at `e2ea9f74bf247a1b1104cded53255ac4a34551a0`. The exact tested source head was `a937947ce2a2ec06e6eed549672a585b10e2c3fb`; [CI run 42447891569](https://github.com/cdin-editor/cdin/actions/runs/42447891569) completed successfully.

### Immutable dependency set

The pinned Registry Catalog is `2a611eca830c0f235dacab04a1d006a8fd46e586`. It retains previous metadata identities and adds the immutable Frontend 1.0.1 TUI/GUI-SDL and Runtime RC2 entries.

| Component | Resolved package | Relevant contract |
| --- | --- | --- |
| Kernel | `1.2.1` | Kernel ABI `1.1.0` |
| Backend | `1.2.0` | Runtime Host API `1.0.0`; Frontend Protocol `1.0.0` |
| Runtime | `1.0.0-rc.2` | Provides `org.cdin.runtime-extension-contract@1.0.0` |
| Frontend TUI | `1.0.1` | Requires Frontend Protocol `1.0.0` |
| Frontend GUI-SDL | `1.0.1` | Requires Frontend Protocol `1.0.0` |

Backend's existing Runtime dependency range selects RC2. `allow_prerelease: true`
remains deliberate and transitional; do not switch to stable-only until a
stable Runtime package is published. Previously published Frontend 1.0.0 and
Runtime RC1 metadata, digests and source pins remain unchanged.

### Exact-head verification

All seven required jobs in [run 42447891569](https://github.com/cdin-editor/cdin/actions/runs/42447891569) passed:

- Linux, macOS and Windows TUI product profiles.
- Linux, macOS and Windows GUI-SDL + TUI fallback profiles.
- Full-stack AddressSanitizer, UndefinedBehaviorSanitizer and leak-detection job.

In each of the six native profile/OS jobs, the Registry CLI ran its Go suite,
Catalog/Product Definition schema validation, resolve, prepare, Manifest
replay, Manifest verification and workspace E2E. The resolver selected the
five exact package versions in the table above; older Frontend 1.0.0
candidates were rejected by the explicit 1.0.1 constraints. Runtime startup
logged `version=1.0.0-rc.2`, matching the Resolved Manifest, on Linux,
macOS and Windows in both profiles.

The native tests also passed the GUI-SDL live-session smoke, document
text/paste, undo/redo, atomic save, close/open and exact-byte persistence,
filesystem failure/recovery, byte-preservation fixtures, multi-session
Driver/Observer promotion, detach/reattach, abrupt peer loss with queued UI
work, same-session reconnect, lease reacquisition and exact Backend-owned
document content recovery. Compiler-resolved include checks found no private
component source/build headers. Full-stack ASan/UBSan/leak detection passed.

### Measured, but not release-grade, performance evidence

The CI benchmark runs ten iterations of the named `cdin --check`
headless-composition-root smoke and records p50/p95/p99 wall time plus sampled
peak RSS. It is not per-keystroke/input-to-visible or save latency, is not a
representative editing workload, and is not a soak or release baseline.
Allocator peak, operation-level budgets, repeatable editing workload and
documented soak/leak acceptance remain open in issue #111. Raw benchmark and
source-snapshot artifacts were attached to the native workflow.

### Remaining product/release gates

The CI success validates the integrated composition slice; it does not make
CDIN a stable editor release. Issue [#111](https://github.com/cdin-editor/cdin/issues/111)
remains open for FE-019 lost-wakeup/readiness and Windows CTRL-event stress,
supported non-experimental launch, live plugin capability/permission and
failure-lifecycle tests, Backend/Runtime process failure recovery, soak and
operation-level performance baselines, clean-machine application installers,
signed release artifacts and component Catalog publication automation.

The JavaScript/TypeScript CodeQL analyzer still reports no source on this
repository. C/C++, Python, Actions and the top-level CodeQL check pass; the
post-merge Default Setup language-selection adjustment is tracked in
[CDIN #113](https://github.com/cdin-editor/cdin/issues/113) and requires
repository Settings access. No fake JS/TS source or legacy website has been
reintroduced.

Cross-repository status: Runtime #7, Backend #19, Spec #16 and Spec #23 are
closed. Frontend #24 has its 1.0.1 package identity, immutable metadata,
Catalog entries and full CDIN matrix verified; its formal tag/release decision
remains open. Frontend #15 and Spec #14, #20, #21 and #25 remain open as
presentation, IME, splitter-resize and byte-anchor contract gates.

---

## Registry integration update — 2026-11-07
## Cross-repository version synchronization — 2026-11-08

The Registry Catalog snapshot pinned by this candidate is
`2a611eca830c0f235dacab04a1d006a8fd46e586`. It preserves the previous
immutable entries and adds:

- Backend `1.2.0` (existing)
- Kernel `1.2.1` (existing)
- Runtime `1.0.0-rc.2` with the provider contract
  `org.cdin.runtime-extension-contract@1.0.0`
- Frontend TUI `1.0.1`
- Frontend GUI-SDL `1.0.1`

The exact Frontend and Runtime metadata URI/digest pairs are stored in the
Catalog at that pinned commit. The Product Definitions select Frontend
`1.0.1`; Backend `1.2.0` resolves Runtime RC2 through its declared
dependency range. The Resolved Manifest remains authoritative for every
selected package and source revision. This sync PR deliberately does not
change Backend or Kernel package identities.

The exact current-head Linux/macOS/Windows TUI/GUI-SDL product matrix and
full-stack ASan/UBSan/leak job must pass before this cross-repository update
is accepted. A prior successful run against Frontend 1.0.0 / Runtime RC1 is
historical evidence only. Runtime prerelease selection remains enabled until
a stable Runtime release exists; it must not be disabled merely because RC2
is now selected.


The Composition Root implementation is merged to `main` in [PR #110](https://github.com/cdin-editor/cdin/pull/110) and uses the Registry-based component selection and source handoff described by [Registry integration](registry.md) and [Spec ROOT-010](https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md#L31-L31).

- Kernel, Runtime, Backend and Frontend own immutable release metadata in their component repositories. Frontend TUI and GUI-SDL are separately declared variants.
- CDIN contains only the TUI and GUI-SDL Product Definitions. The versioned Catalog Index now lives in the pinned Registry checkout at `catalogs/cdin-components/catalog-index.json`; the CDIN repository no longer stores component metadata URIs, repository URLs or a Catalog Index.
- The GUI-SDL product resolves both the TUI base adapter and GUI-SDL adapter, matching the current executable composition.
- Registry is pinned as a host build tool, runs its Go tests, validates the product/catalog documents, resolves and prepares sources, verifies and replays the Manifest. It is not a runtime dependency.
- Component versions and source revisions are read from the Resolved Manifest; component entries have been removed from `deps.lock`.
- The native CI matrix now includes TUI and GUI-SDL product profiles on Linux, macOS and Windows. The sanitizer job uses the GUI-SDL superset profile, exercising TUI, GUI-SDL and headless paths together.

**Status: VERIFIED INTEGRATION CANDIDATE.** The Registry pin and package selectors passed the exact-head six-job native matrix and full-stack ASan/UBSan/leak verification in [run 42447891569](https://github.com/cdin-editor/cdin/actions/runs/42447891569). The Runtime prerelease allowance remains transitional. A separate Catalog publisher/release publication workflow remains outstanding.

## Current verification update — 2026-11-07

PR #110 was merged to `main` on 2026-11-08 at `e2ea9f74bf247a1b1104cded53255ac4a34551a0`; its exact tested head was `a937947ce2a2ec06e6eed549672a585b10e2c3fb`.

- Frontend PR #19 is merged at `1373715c23eb965445caa926de3a99d9c0246f81`; Registry selects this immutable source through the Frontend Release Metadata referenced by its Catalog Index rather than a component entry in CDIN's `deps.lock`.
- Runtime sandbox capability-denial unit coverage is in Runtime commit `e2f19e279e3194a6615ce213331639fde4f42e87`; Runtime CI run [42315040626](https://github.com/cdin-editor/runtime/actions/runs/42315040626) passed Linux, Windows, macOS, Pipeline quality and docs/workflow validation.
- CDIN's trusted extension CLI and PTY/ConPTY fixtures were corrected after the prior run exposed invalid Python triple-quoted Lua source. Current CLI/PTY/ConPTY fixtures now use one line-continuation backslash; the accidental duplicate ConPTY source block and stale capability sentinel were removed.
- The multi-session smoke now verifies exact Backend-owned document bytes survive abrupt peer loss and a new Protocol client reconnecting to the same Backend session (commit `6eb58fd`). This test is not accepted until the current matrix passes.
- Current native + ASan/UBSan/leak matrix: [CDIN run 42447891569](https://github.com/cdin-editor/cdin/actions/runs/42447891569) passed all six profile/OS jobs and the full-stack sanitizer job on the exact tested head.
- Frontend SDL renderer device-loss recovery is verified in Frontend CI [42315157831](https://github.com/cdin-editor/frontend/actions/runs/42315157831); the broader GUI-SDL and IME release work remains open in [Frontend Issue #15](https://github.com/cdin-editor/frontend/issues/15).

The interactive TUI launch remains experimental/fail-closed. Do not mark FE-019, Windows ConPTY, plugin lifecycle/capability integration, document reconnect recovery, or product release gates complete until current CDIN test evidence is inspected.


# Integration status and release gates

This document reports capabilities exercised by the CDIN Composition Root, not merely features exposed by a component. A green component build does not prove that the complete editor is usable.

The product epic and acceptance criteria are tracked in [issue #111](https://github.com/cdin-editor/cdin/issues/111). The current integration candidate is developed on `feature/complete-composition-root-rewrite` through [PR #110](https://github.com/cdin-editor/cdin/pull/110), which remains Draft. The current branch includes the merged Frontend ConPTY correction and the immutable dependency pin recorded below.

## Current verification update — 2026-11-07

### Frontend ConPTY correction

- Frontend [PR #19](https://github.com/cdin-editor/frontend/pull/19) merged at `1373715c23eb965445caa926de3a99d9c0246f81`.
- Frontend CI [run 42312049293](https://github.com/cdin-editor/frontend/actions/runs/42312049293) passed all five jobs: Linux native TUI, macOS native TUI, Windows native TUI, SDL3 production adapter/installed consumer, and Pipeline quality.
- CDIN `deps.lock` pins that exact merge commit. The pin update is [commit ab9d854](https://github.com/cdin-editor/cdin/commit/ab9d85455c78200e2cccd7df50e5f65bbf70b6c9).
- CDIN full-stack + sanitizer verification for that exact pin is [run 42312594183](https://github.com/cdin-editor/cdin/actions/runs/42312594183). At the time of this document update, its Linux, macOS, Windows and ASan/UBSan/leak-detection jobs are still running. The Windows `cdin_tui_live_conpty_smoke` must pass before the cross-repository ConPTY gate is checked off.

### Current verified boundary

- The previous CDIN candidate passed the headless editing/persistence workflow, POSIX PTY, multiple Frontend Driver/Observer roles, detach/reattach lease reacquisition, byte-preservation fixtures, filesystem failure recovery, compiler-resolved include graph, reproducible source snapshot and Linux ASan/UBSan/leak detection in [run 42182694691](https://github.com/cdin-editor/cdin/actions/runs/42182694691).
- GUI-SDL live-session text input and exact-byte save smoke passed on Linux/macOS/Windows in [run 42310020078](https://github.com/cdin-editor/cdin/actions/runs/42310020078). That run used the prior Frontend pin and is not a substitute for the new run above. GUI-SDL remains experimental; complete PaneTree rendering, IME, shaping/bidi/Persian, device-loss recovery and full session recovery are still open.
-  read handle. Frontend PR #19 aligned the wait and read handles and restores the original standard input handle on teardown. The exact current CDIN Windows TUI/GUI-SDL jobs passed in run 42447891569; interactive launch remains experimental until FE-019 readiness and CTRL-event stress gates pass.
- PR #110 remains Draft. No supported release-mode interactive launch, complete plugin capability policy, process recovery, product-grade performance/soak evidence or native application installers are claimed.

## 1. Verified in CDIN

| Capability | Status | Evidence |
| --- | --- | --- |
| Registry component selection and immutable workspace | VERIFIED | Exact Catalog pin, Product Definitions, source collection, Resolved Manifest and workspace replay/verify pass on all six native product jobs in run 42447891569. |
| Registry release/contract resolution and package compatibility | VERIFIED | Exact versions/contract metadata resolve on all six native jobs; Runtime startup reports `1.0.0-rc.2`, matching the Resolved Manifest. |
| Backend lifecycle | VERIFIED | `--check` calls Backend create/start/pump/shutdown/destroy and routes Backend log callbacks into the CDIN logger. |
| Headless Frontend Protocol | PASS on Linux/macOS/Windows | HELLO/HELLO_ACK, ATTACH, ordered UI snapshot, `ui.flush`/ACK, queue release and resize are exercised over the public Frontend session API. |
| Document editing workflow | PASS on Linux/macOS/Windows | `document.new/open/close`, text and binary paste, undo/redo, atomic save and version-pinned line readback run through Frontend → Backend → Runtime → Kernel. |
| Byte preservation | PASS on Linux/macOS/Windows | Fixtures cover NUL, invalid UTF-8, BOM, LF-only and mixed CRLF/LF/CR data; saved and reopened bytes are compared exactly. |
| Filesystem failure recovery | PASS on Linux/macOS/Windows | Missing-file read and failed atomic save are exercised; the in-memory document remains intact and a subsequent valid save succeeds. |
| CLI validation | PASS | Help/version, invalid values, unknown options and fail-closed frontend selections are covered by executable-level CTest. A help assertion now checks the advertised `headless|tui` choices. |
| Architecture check unit tests | PASS on Linux/macOS/Windows | Six tests cover installed-header allow, private source/build header deny, compiler probe flag handling and include-trace parsing. |
| Compiler-resolved include graph | PASS on Linux/macOS/Windows | Compiler include tracing covered all four CDIN translation units on each platform and found no private component source/build headers. |
| Source snapshot and hash | PASS on Linux/macOS/Windows | Deterministic source ZIP, archive safety/CRC checks and SHA-256 sidecar validated on each native runner. This is a source archive, not an application installer. |

### Current candidate update — 2026-11-07

The current CDIN PR #110 head is `f347f5085e5c32a14fda09e2a4971cc90d981800`. [CI run 42296140965](https://github.com/cdin-editor/cdin/actions/runs/42296140965) failed on Linux, macOS, Windows and the Linux sanitizer job at the same compile step: `src/integration/gui_sdl.c` includes `integration/frontend_smoke.h`, but the `cdin` target did not add the repository `src/` directory to its private include path. The pinned Kernel, Backend and Frontend component builds/tests reached completion before that CDIN compile failure. The CMake target include path is being corrected; do not mark this run or GUI E2E as PASS.

The Frontend pin is `552eedd14e3971e2b39d706804d4af57f8b2dc38` (Frontend PR #17 candidate). [Frontend CI run 42295241142](https://github.com/cdin-editor/frontend/actions/runs/42295241142) passed Linux, macOS, Windows and Pipeline quality. Its SDL3 job passed all 12 tests under AddressSanitizer, installed the `cdin::frontend_ui_gui_sdl` package and built the clean-prefix consumer. This verifies the standalone Frontend package only.

Backend PR #18 head `b24102fa61461cc8efc696d81d7a582d53297989` passed [Linux Live Runtime integration 42291308024](https://github.com/cdin-editor/backend/actions/runs/42291308024), [native resource/sanitizer matrix 42291307713](https://github.com/cdin-editor/backend/actions/runs/42291307713) and [Python Code Quality 42291301523](https://github.com/cdin-editor/backend/actions/runs/42291301523). The new resolver integration test runs in the Linux Live Runtime job; its execution on macOS and Windows is still an explicit follow-up, so Backend Issue #14 must remain open for that matrix.

### Previous fully completed native evidence

[Historical CDIN CI run 42182694691](https://github.com/cdin-editor/cdin/actions/runs/42182694691) passed on exact branch HEAD `6166fd2034194c3a8b5b13d4baa1d81adce3b14d`; it remains historical evidence for the TUI/headless candidate and does not validate the newer GUI-enabled SHA.

- Linux, macOS and Windows pinned-stack build/E2E jobs all completed successfully. Linux and macOS each passed 19/19 Frontend tests and 11/11 root CDIN CTest cases, including `cdin_tui_live_pty_smoke`; Windows passed 18/18 Frontend tests and 11/11 root CDIN CTest cases (the POSIX-only PTY test is not run on Windows).
- All three native logs report `Frontend multi-session smoke passed: Driver/Observer, negotiated promotion, detach/reattach lease reacquisition and input`. The test uses two independent public Frontend sessions against one Backend; it also verifies that an Observer cannot send input.
- All three logs confirm the document workflow, exact-byte fixtures (NUL, invalid UTF-8, BOM, LF-only, mixed CRLF/LF/CR), missing-file and failed-atomic-save recovery, and successful recovery save.
- Compiler-resolved include graph passed on all three platforms: four CDIN translation units, no component source/build headers. The six architecture policy tests passed.
- Linux ASan/UBSan/leak-detection job passed. The Backend dependency's companion Live Runtime, ASan/UBSan, ThreadSanitizer and Linux/macOS/Windows stress checks passed on Backend PR #13 head `60ccca7254ba6907f2c99f21adf45355966f2238`; PR #13 is now merged at `3764128a13051c1a16683ef201a391b026a93e6f`.
- Deterministic source archives passed archive/CRC validation and SHA-256 verification on native runners. Linux/macOS/Windows source artifacts are not native application installers.
- CodeQL Default Setup passed C/C++, Python and Actions analysis in [run 42182689616](https://github.com/cdin-editor/cdin/actions/runs/42182689616). The separate Code Quality workflow passed Python but failed its JavaScript/TypeScript job because this repository has no JS/TS source; that language selection is a repository setting.

The CI's short headless benchmark recorded p50/p95/p99 of 21.0/32.2/39.5 ms and sampled peak RSS 3.64 MB on Linux; 57.9/89.8/97.1 ms and 4.90 MB on macOS; and 74.0/74.7/74.9 ms and 7.08 MB on Windows. These are measurements of this small headless smoke workload, not product performance budgets, allocator peaks or long-running soak evidence.

## 2. Experimental TUI status

The POSIX path is present in `src/integration/frontend_smoke.c` and is deliberately gated by `CDIN_ENABLE_EXPERIMENTAL_TUI=1`. Without the opt-in, the launcher returns status 3 and prints that interactive launch remains gated. The CI PTY harness sets the opt-in explicitly.

The live path opens the terminal, installs SIGWINCH/SIGTERM/SIGINT wakeup handling, attaches a Frontend Protocol session, applies and ACKs the initial snapshot, creates a scratch document, then runs the Frontend TUI event loop with bounded terminal and Backend draining, resize handling, rendering and orderly teardown. The PTY test checks title/render, input, SIGWINCH interruption, save+quit with pending UI work, separate SIGTERM shutdown, startup failure and restoration of terminal flags/modes.

Frontend PR [#11](https://github.com/cdin-editor/frontend/pull/11) fixed the earlier version-pinned line-request lifecycle defect and merged as `e29df5118e7b822912724b15c0c963b0b99f2f8a`. The current candidate also includes [Frontend PR #14](https://github.com/cdin-editor/frontend/pull/14), merged as `eaadc442e04020b0dd209f89c1b94cdb1d3aa7b3`; it exposes a newly granted Driver role during `ATTACH_SENT` while keeping input APIs gated until `ATTACHED`. Backend [PR #12](https://github.com/cdin-editor/backend/pull/12) is merged and implements capability-gated lease reacquisition. Backend [PR #13](https://github.com/cdin-editor/backend/pull/13) corrects the per-connection event-sequence assertion and is now merged at `3764128a13051c1a16683ef201a391b026a93e6f`; CDIN `deps.lock` has been refreshed to this actual merge commit. The two-Frontend integration path now passes on the current CDIN candidate in run 42182694691.

Windows TUI remains fail-closed for supported release-mode launch; the current ConPTY smoke passes on the exact Linux/macOS/Windows matrix but FE-019 readiness/CTRL-event stress is still open. GUI-SDL is behind `CDIN_ENABLE_EXPERIMENTAL_GUI_SDL=1`; its live-session, editing and save smoke pass on the full native matrix and sanitizer job, but this does not establish a production Unicode renderer or stable GUI release.

## 3. Architecture and security checks

### Compiler-resolved include graph

`scripts/check_include_graph.py` consumes the generated CMake `compile_commands.json` and asks the configured compiler to emit its resolved include trace (`-E -H`). It rejects headers resolved from component source checkouts or private component build trees and allows headers from the installed component prefix. `scripts/check_boundaries.py` also runs the six Python policy tests.

This is stronger than checking literal `#include` spellings, but it is not a proof of every cross-component semantic dependency rule. The current native matrix verified the graph for all four CDIN translation units on Linux, macOS and Windows.

### GitHub Code Quality

The separate GitHub Code Quality dynamic workflow still attempts JavaScript/TypeScript analysis even though this repository has no JavaScript/TypeScript source. Its Python job passes; the JS/TS job fails after extracting YAML-only configuration files. This selection is controlled by repository Settings → Security → Code quality, not by the checked-in Pipeline configuration. Deselect JavaScript/TypeScript there and retain Python.

### CodeQL

The repository uses GitHub CodeQL Default Setup. The custom advanced workflow was removed to avoid conflicting SARIF uploads while Default Setup is enabled. Run 42182689616 passed C/C++, Python and Actions analysis on the current SHA. The separate Code Quality dynamic workflow is distinct: Python passed, while JS/TS failed because there is no JS/TS source. Deselect JavaScript/TypeScript in Settings → Security → Code quality; this cannot be changed by a source commit.

### Artifact provenance

The reproducible source snapshot and trusted-main provenance flow are source-distribution evidence only. PR jobs do not receive attestation permissions; the trusted-main job is intentionally skipped for pull requests. A source ZIP is not a runnable application installer or release package.

## 4. Not complete

| Area | Status | Remaining work |
| --- | --- | --- |
| Live experimental TUI on POSIX | PASS on Linux/macOS | The current PTY smoke passes initial render, input, SIGWINCH, save/quit, signal shutdown, startup failure and terminal restoration. Launch remains opt-in with `CDIN_ENABLE_EXPERIMENTAL_TUI=1`; this is not a supported release-mode launch. |
| Windows TUI | EXPERIMENTAL SMOKE PASS / LAUNCH GATED | The exact current Windows TUI and GUI-SDL jobs passed ConPTY/Console input, document and save smoke in run 42447891569. Supported non-experimental launch remains gated on FE-019 wakeup/CTRL-event stress and full product acceptance. |
| GUI-SDL | LIVE SESSION SMOKE PASS / PRODUCT INCOMPLETE | Exact current run 42447891569 passed the GUI-SDL product matrix on Linux/macOS/Windows, including SDL live-session, document input/save and multi-session reconnect smoke. Interactive launch remains experimental; renderer is ASCII/debug text and IME/Unicode/presentation product gates remain open. |
| Runtime/plugin lifecycle | HEADLESS LIVE SMOKE PASS ON LINUX/MACOS; FULL RELEASE ACCEPTANCE OPEN | CDIN accepts `--extension-root` and repeated `--load-extension`; `cdin_trusted_extension_cli_smoke` creates a temporary extension and verifies its real Lua init/unload sentinels through the trusted Backend C API. This CTest passed on Linux/macOS in run `42199285019`; Linux ASan/UBSan/leak detection passed. The TUI launcher also calls the same trusted load/unload helpers, but no dedicated TUI-plus-extension PTY assertion is present. Capability allow/deny, failed-init/runtime failure isolation and Windows integration remain unverified. Runtime PR #6 and Backend PR #16 are merged; `deps.lock` now pins their merge commits. |
| Multiple Frontends and recovery | CONTROLLED RECONNECT VERIFIED / FAILURE RECOVERY OPEN | Exact run 42447891569 passes Driver/Observer promotion, detach/reattach, abrupt peer loss with queued UI work, same-session reconnect, lease reacquisition and exact Backend-owned document recovery across Linux/macOS/Windows. Backend/Runtime process failure, owner-loop wakeup stress, partial startup and repeated shutdown remain open. |
| Performance | PARTIAL / NOT A BASELINE | Short headless smoke reports per-platform sampled RSS and p50/p95/p99; allocator peak, defined editing workloads, input-to-visible/save latency, budgets and soak/leak workload remain open. |
| Application installers | NOT IMPLEMENTED | Native Linux/macOS/Windows packages, runtime discovery, clean-machine install/upgrade/uninstall and checksums/provenance. |
| Stable release | NOT READY | Requires all interactive, recovery, security, performance and packaging gates above. |

Historical note: this sentence predates the Registry handoff implementation. The current Catalog ownership and build path are described in the Registry integration section at the top of this document.

## 5. Ordered release gates

1. Complete the Windows ConPTY path: deliver terminal bytes through the opened CONIN$ handle, verify Frontend Protocol mutations and UI ACK/redraw, then assert exact save bytes and restoration. Keep Windows launch fail-closed until that test passes.
2. Fix the current CDIN GUI-SDL compile include path; pass the live Backend/Runtime SDL smoke, native matrix and sanitizer. Then complete text rendering/IME/pane capabilities before enabling a supported GUI release.
3. Finish trusted-extension release acceptance: make the real Lua init/unload smoke pass on all native platforms; test unknown/denied names plus initialization/runtime/unload failure cleanup; add a TUI-plus-extension PTY assertion; and document the administrator-controlled extension root. Runtime PR #6 and Backend PR #16 are merged, but capability policy and Windows validation are not yet green.
4. Exercise transport disconnect/reconnect with work pending, Backend/Runtime failure recovery, partial startup and repeated start/stop.
5. Define named editing workloads; collect allocator peak where available, input-to-visible/save latency, p50/p95/p99, raw per-platform results and a documented soak/leak run. The current benchmark is only a short headless smoke.
6. Produce Linux/macOS/Windows application installers and validate clean-machine dependency discovery, launch, basic editing, upgrade and uninstall; sign artifacts and verify embedded licenses/assets.
7. In Settings → Security → Code quality, deselect JavaScript/TypeScript and retain Python. CodeQL already passed C/C++, Python and Actions on the current SHA.
8. Keep CDIN PR #110 under independent review. Backend PR #13 is merged; the current dependency pin now uses its merge commit.

PR #110 is merged. Issue #111 remains open; this work proves the tested integration slice, not a stable editor release.

The epic remains open until these release gates are verified. Configured workflows, partial output or a green component suite must not be marked as product-level PASS.


## Dependency merge and current verification — 2026-11-06

Runtime PR [#6](https://github.com/cdin-editor/runtime/pull/6) is merged at `d2acb6f174edf127c3bf59e8e5d4aedcbef0d490`; Backend PR [#16](https://github.com/cdin-editor/backend/pull/16) is merged at `bdb3d17e1330b3fc5d2a4906ec212b3aa32905c1`. CDIN `deps.lock` now pins those merge commits (their source trees match the tested PR heads). Frontend remains pinned to PR #16's candidate SHA `8b4714d6e3501bc0e9387bd8c7cd233806ab18cc` while its ConPTY work remains open.

On the same component source trees, [CDIN run 42199285019](https://github.com/cdin-editor/cdin/actions/runs/42199285019) passed Linux and macOS native build/E2E and Linux ASan/UBSan/leak detection. Both POSIX runners passed all 16 root CTests, including `cdin_trusted_extension_cli_smoke` and `cdin_tui_live_pty_smoke`, and the compiler-resolved include graph. Windows failed before CTest while compiling Backend `src/runtime/extension_resolver.c`: GCC 16.2 reports two `-Wtype-limits` diagnostics as errors at the DWORD-to-`size_t` allocation guards (lines 190 and 686). The Windows resolver build is therefore **NOT PASS**.

The new merge-SHA CDIN run [42224282657](https://github.com/cdin-editor/cdin/actions/runs/42224282657) is currently running. Do not mark the native matrix complete until its Windows job passes or the compiler-guard issue is fixed and the rerun is inspected. CDIN PR #110 remains Draft; issue #111 remains open.


## GUI-SDL composition candidate

The candidate uses the immutable Frontend PR #17 source revision `552eedd14e3971e2b39d706804d4af57f8b2dc38` and the checksum-pinned SDL3 3.4.16 archive recorded in `deps.lock`. `scripts/build_stack.py` builds and installs SDL3, builds the Frontend SDL target, then configures CDIN with `CDIN_ENABLE_GUI_SDL=ON`. The CDIN executable owns the in-process transport callbacks and Backend lifecycle; the Frontend SDL library owns SDL window/events/rendering and the semantic model. No Backend, Runtime or Kernel private headers are added to the Frontend package.

The live-session smoke is intentionally a CI test path, not a second editor implementation: it attaches the GUI Driver Session, creates a temporary document through Runtime, pushes a deterministic SDL text event and Ctrl+S key event, and checks the saved bytes. The test is bounded and removes its temporary file on teardown. It does not prove production text shaping, full GUI interactions, reconnect or installer readiness.
