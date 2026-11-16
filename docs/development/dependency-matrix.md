# Dependency and delivery matrix

## Current artifact-first candidate — 2026-11-15

This page describes the dependency graph proposed by [CDIN PR #149](https://github.com/cdin-editor/cdin/pull/149). It is not yet the merged `main` selection. A published component Release is not automatically product-accepted: the exact package, metadata identity, target tuple, API/ABI contracts and downstream consumer evidence must agree.

| Component / environment | Candidate identity | Delivery and scope | Immutable source / release identity | Acceptance state |
| --- | --- | --- | --- | --- |
| Kernel | Package `1.2.3`; C ABI `1.1.0` | Five target-specific SDK archives pinned in `deps.lock`; also supplies the separately versioned logger SDK | [Kernel v1.2.3](https://github.com/cdin-editor/kernel/releases/tag/v1.2.3), tag commit `2fb09f52dc1a9963cf358ec54d584c520e174e67` | Existing package baseline reused; no new Kernel packaging work is part of CDIN #122. |
| m-mdy-m/log.c | C API `0.1.0` | Bundled with the Kernel SDK; not a private Backend dependency | Kernel v1.2.3 SDK assets | Existing package baseline reused. |
| Runtime | Package `1.0.0`; Extension Contract `1.0.0` | Platform-neutral Lua 5.4 module archive; Registry artifact | [Runtime v1.0.0](https://github.com/cdin-editor/runtime/releases/tag/v1.0.0), tag commit `eb48a511ea6d5085db38e501784290d80cb03947`; metadata asset `runtime-1.0.0.json` | Published. Runtime #16 remains open for exact clean-consumer/CDIN verification. |
| Backend | Package `1.2.2`; Runtime Host API `1.0.0` | Five target-native `cmake-prefix-v1` development packages; Registry artifact | [Backend v1.2.2](https://github.com/cdin-editor/backend/releases/tag/v1.2.2), tag commit `41681388d8294efeb371b0d337b426a72c19aeae`; metadata asset `backend-1.2.2.json` | Published. Backend #35 remains open for downstream Manifest, link and product-consumer evidence. |
| Frontend Core | Package `1.2.2`; Frontend Protocol `1.0.0` | Shared native package, resolved once for either profile | [Frontend v1.2.2](https://github.com/cdin-editor/frontend/releases/tag/v1.2.2), tag commit `728406c1e677d601c55b82b4fbf1a77eecfd8581`; metadata asset `frontend-core-1.2.2.json` | Published; clean-prefix coalescing and product consumption remain to be proven. |
| Frontend TUI | Package `1.2.2` | Native TUI adapter; no SDL3 dependency | Same Frontend v1.2.2 tag; metadata asset `frontend-tui-1.2.2.json` | Published; real terminal launch/input/restore acceptance remains open. |
| Frontend GUI-SDL | Package `1.2.2` | Native GUI adapter; SDL3 SDK is an external GUI-only dependency | Same Frontend v1.2.2 tag; metadata asset `frontend-gui-sdl-1.2.2.json` | Published; renderer, shaping, bidi and interactive product acceptance remain incomplete. |
| Registry consumer | CLI/package `1.0.1` | Five native executables plus descriptor; release-bundle Catalog is verified by the bootstrap but not used for CDIN product resolution | [Registry v1.0.1](https://github.com/cdin-editor/registry/releases/tag/v1.0.1), tag commit `ed7c8fbe5513b6b0d6eb76d31191c696b98f8d27`; descriptor SHA-256 `c37a1902afe6d41291b0f29d6970408d70dae239881307533673ceaf85634403`, size 1,633 bytes | Published. CDIN separately pins its product Catalog and exact component metadata assets; exact-head clean-consumer acceptance remains required. |
| Registry developer source | `1.0.1` source pin | Explicit developer/CI source-build path only; never the normal consumer path | Same exact source commit as immutable [Registry v1.0.1](https://github.com/cdin-editor/registry/releases/tag/v1.0.1): `ed7c8fbe5513b6b0d6eb76d31191c696b98f8d27` | Source and artifact delivery modes now identify the same immutable Registry release commit. Normal `make install` uses the five-target published executable bundle; explicit developer/CI builds may compile the pinned source. |
| SDL3 SDK | `3.4.16` | Five target-specific prebuilt SDKs; GUI-SDL only | [SDK Release](https://github.com/cdin-editor/cdin/releases/tag/sdl3-sdk-v3.4.16), tag commit `d249122c51acbab7262a6cd1e675922fd043bac7`; exact archive and sidecar sizes/digests are pinned in `deps.lock` | Published and pinned by PR #149; clean configure/link and extracted-product validation remain in CDIN #124. |

## Version and contract boundaries

| Identity | Candidate value | Notes |
| --- | --- | --- |
| Specification | Stable `v1.4.0`; Registry Data Contract `1.4.0` | ADR-0028 is accepted. Spec tag and newer Spec `main` source are distinct identities. |
| Kernel C ABI | `1.1.0` | Independent of Kernel package `1.2.3`. |
| Logger C API | `0.1.0` | Independent of Kernel package version. |
| Runtime Host API | `1.0.0` | Backend-to-Runtime contract; not the Runtime package version. |
| Runtime Extension Contract | `1.0.0` | Runtime package `1.0.0` does not determine this value. |
| Frontend Protocol | `1.0.0` | Backend/Frontend wire compatibility is checked separately from package SemVer. |
| Lua C API | `5.4.0` | External host dependency declared by both Product Definitions. |
| SDL3 SDK | `3.4.16` | GUI-SDL external environment contract only. |
| CDIN project | `0.2.0` on current `main` | The project version is not yet `1.0.0`; do not create a product tag until the Stable gates pass. |

## Product profile dependency closure

- **TUI:** Kernel/logger SDK, Runtime, Backend, Frontend Core and Frontend TUI. It must not download, build, link or stage SDL3.
- **GUI-SDL:** the same common dependencies plus Frontend GUI-SDL and the pinned SDL3 SDK. Frontend Core is resolved and installed once even though the profile has multiple Frontend adapters.
- Both stable Product Definitions set `allow_prerelease: false`. Registry resolves component dependencies and contract compatibility from the immutable entries Catalog; CDIN consumes the exact Resolved Manifest. The Catalog is the product-owned input map, with each entry bound to an exact metadata URL and digest.

Runtime is a transitive Backend dependency selected from the Registry Catalog. Frontend Core is a shared adapter dependency. Kernel and logger are provisioned through the existing target SDK lock, not repackaged by CDIN.

## Registry and artifact-delivery policy

CDIN PR #149 uses a checked-in static Catalog at `registry/catalog-index.json`, pinned by `tooling.cdin_catalog.sha256` in `deps.lock`. Its six `entries` bind Backend 1.2.2, Frontend Core/TUI/GUI-SDL 1.2.2, Kernel 1.2.3 and Runtime 1.0.0 metadata assets to their exact public Release URLs and GitHub-published SHA-256 digests. Registry validates the Catalog schema, downloads only those declared metadata bytes, verifies each digest, then performs dependency/contract resolution. The Catalog file is content-pinned and verified before every Registry invocation. The generic dynamic Catalog bundled with Registry v1.0.1 remains verified as part of the immutable Registry bundle, but CDIN does not pass it to product resolution.

ADR-0028 `release_sources` remains available to consumers that intentionally follow new releases dynamically. CDIN product definitions pin exact versions, so discovery adds no value to this release candidate and would add unnecessary cross-repository API calls. Component publishers continue to generate canonical metadata JSON as GitHub Release Assets; new per-version metadata files must not be added under component `registry/releases/` directories.

Normal installation must use the immutable Registry executable and artifact-delivered component packages. Registry/component source builds and SDL3 source compilation remain explicit developer/producer workflows only. A selected artifact that fails identity, digest, layout or extraction validation must fail closed; it must not trigger a source fallback.

## Product Catalog integrity and CI network access

The product Catalog is an ordinary version-controlled CDIN input, not a runtime lookup service. Its exact path and SHA-256 are pinned in `deps.lock`; `scripts/registry.py` rejects a missing, modified, symlinked, oversized or dynamic (`release_sources`) Catalog before launching Registry. Every metadata URL is a canonical public GitHub Release asset URL, and Registry independently checks the downloaded metadata against the Catalog SHA-256 before parsing it.

Because CI consumes this immutable `entries` Catalog, it does not enumerate component GitHub Releases or resolve tags through `api.github.com`. The native CI, sanitizer and Product Acceptance workflows require no cross-repository PAT or GitHub App token. Same-repository `GH_TOKEN` remains available only for same-repository GitHub CLI operations. Archive downloads and package extraction remain subject to the existing URL, size, digest, target and safe-extraction checks.

## Current readiness boundary

Registry v1.0.1 is published from exact commit `ed7c8fbe5513b6b0d6eb76d31191c696b98f8d27`. Its five target executables, generic same-tag Catalog, `registry-release-1.0.1.json`, and `SHA256SUMS` are present in the immutable [v1.0.1 Release](https://github.com/cdin-editor/registry/releases/tag/v1.0.1). CDIN PR #149 pins the executable bundle and separately pins its product-owned Catalog at SHA-256 `16384288f38191a069f9837d178a3cbeed6c1c5dde91d6c5ae71928ccea4f224` (1,902 bytes). The next gate is the exact-head native CI and ten-way installed-product acceptance against these immutable inputs; publication itself is not product acceptance.

CDIN PR #149 contains the candidate lock, Product Definition and bootstrap changes. Its artifact-first path still needs the exact Registry v1.0.1 Release, all ten installed-product jobs, clean-prefix extraction, warm/offline cache and Manifest replay. CDIN #118 and #111 separately gate live IME/PaneTree behavior, supported TUI/GUI-SDL interaction, Unicode shaping and Persian/Arabic text, lifecycle/recovery, performance, security and real product distributions.

**Current product state: DEVELOPMENT / NOT PRODUCT READY.** No CDIN `v1.0.0` Stable tag or Release is authorized by the evidence recorded here.
