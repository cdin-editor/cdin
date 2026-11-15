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
| Registry consumer | CLI/package `1.0.1` | Five native executables plus same-tag dynamic Catalog and release descriptor | [Registry v1.0.1](https://github.com/cdin-editor/registry/releases/tag/v1.0.1), tag commit `ed7c8fbe5513b6b0d6eb76d31191c696b98f8d27`; descriptor SHA-256 `c37a1902afe6d41291b0f29d6970408d70dae239881307533673ceaf85634403`, size 1,633 bytes; Catalog SHA-256 `92d6d837d2dfa94c516036e406e2b7b12c3398a94acb8bfc4d26726bc47f60e0`, size 1,538 bytes | Published. Includes the Manifest schema-floor fix and authenticated cross-repository Release discovery; CDIN exact-head clean-consumer acceptance is now the required evidence. |
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
- Both stable Product Definitions set `allow_prerelease: false`. Registry resolves component SemVer and contract compatibility; CDIN consumes the exact Resolved Manifest and must not duplicate component version maps.

Runtime is a transitive Backend dependency selected from the Registry Catalog. Frontend Core is a shared adapter dependency. Kernel and logger are provisioned through the existing target SDK lock, not repackaged by CDIN.

## Registry and artifact-delivery policy

The Registry v1.0.1 Release carries the dynamic Catalog used by PR #149; it is pinned as the consumer binary and dynamic Catalog source identity. Under accepted Spec ADR-0028 / Registry Data Contract 1.4.0, that Catalog declares stable `release_sources`; Registry discovers complete eligible GitHub Release inventories, validates canonical per-variant metadata assets and tag/source provenance, resolves SemVer deterministically, and records exact release identities in the Manifest. Component publishers generate metadata JSON as GitHub Release Assets; new per-version metadata files must not be added under component `registry/releases/` directories.

Normal installation must use the immutable Registry executable and artifact-delivered component packages. Registry/component source builds and SDL3 source compilation remain explicit developer/producer workflows only. A selected artifact that fails identity, digest, layout or extraction validation must fail closed; it must not trigger a source fallback.

## Cross-repository CI credential

The GitHub Actions `GITHUB_TOKEN` belongs to the CDIN repository and cannot be treated as a credential for the Kernel, Runtime, Backend, Frontend or Registry repositories. CDIN PR #149 now expects the Actions secret `CDIN_GITHUB_READ_TOKEN` to be exposed as `CDIN_GITHUB_API_TOKEN` and `REGISTRY_GITHUB_API_TOKEN` in both CI and Product Acceptance, keeping the standard `GH_TOKEN` namespace free for same-repository CLI operations. It must be a fine-grained PAT or GitHub App installation token with `Contents: read` only on the selected repositories documented in `docs/development/registry.md`. No write permissions are required, and the secret value must never be committed or printed.

The secret's presence cannot be inferred from source files. CI, sanitizer and Product Acceptance now fail at preflight when it is missing: the Linux x86_64 GUI-SDL consumer reached Registry Manifest preparation but exhausted the anonymous GitHub API rate limit while resolving the Kernel tag. Local one-off public API requests may remain anonymous. The dedicated token is not distributed with CDIN and does not replace commit, asset-digest, size or package validation.

## Current readiness boundary

Registry v1.0.1 is now published from exact commit `ed7c8fbe5513b6b0d6eb76d31191c696b98f8d27`. Its five target executables, same-tag dynamic Catalog, `registry-release-1.0.1.json`, and `SHA256SUMS` are present in the immutable [v1.0.1 Release](https://github.com/cdin-editor/registry/releases/tag/v1.0.1); GitHub's Release API reports SHA-256/size identities and the annotated tag resolves to the exact main commit. CDIN PR #149 now pins this published release. The next gate is the exact-head native CI and ten-way installed-product acceptance against the real v1.0.1 bytes; publication itself is not product acceptance.

CDIN PR #149 contains the candidate lock, Product Definition and bootstrap changes. Its artifact-first path still needs the exact Registry v1.0.1 Release, all ten installed-product jobs, clean-prefix extraction, warm/offline cache and Manifest replay. CDIN #118 and #111 separately gate live IME/PaneTree behavior, supported TUI/GUI-SDL interaction, Unicode shaping and Persian/Arabic text, lifecycle/recovery, performance, security and real product distributions.

**Current product state: DEVELOPMENT / NOT PRODUCT READY.** No CDIN `v1.0.0` Stable tag or Release is authorized by the evidence recorded here.
