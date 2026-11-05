# Architecture audit

**Audit baseline:** CDIN branch `feature/complete-composition-root-rewrite`, candidate commit `167de187af4f0d4df8a81c9afb86ba887eaf6cb4`, component revisions in `deps.lock`, inspected on 2026-11-05.

This audit distinguishes code that exists from behavior exercised by the current Composition Root. It is not a claim that the complete editor is implemented.

## 1. Ownership model

CDIN is the composition root. Component ownership remains separate:

- **Kernel:** document bytes, edits, snapshots, versions and undo/redo.
- **Runtime:** Lua policy, commands, keymaps, configuration and plugin lifecycle.
- **Backend:** Kernel/Runtime hosting, sessions, protocol server, queues and OS services.
- **Frontend:** input, semantic projection, layout and rendering.
- **CDIN:** immutable dependency pins, stack build/install orchestration, CLI composition, diagnostics and Backend process lifecycle.

CDIN must not duplicate document, keymap, plugin, protocol or rendering implementations. The normative starting points are [ARCH-001](https://github.com/cdin-editor/spec/blob/main/docs/architecture/overview.md#L113-L113), [ARCH-040–046](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L65-L71) and [ROOT-001](https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md#L22-L22).

## 2. Composition Root inventory

| Area | Evidence | Scope |
| --- | --- | --- |
| CLI and launcher | `src/main.c`, `src/cli/options.c` | Parse options and compose Backend lifecycle. Interactive launch remains gated. |
| Diagnostics | `src/diagnostics/log.c`, `include/cdin/log.h` | CDIN logger setup and Backend callback adapter. |
| Dependency pins | `deps.lock`, `scripts/deps.py` | Immutable component/tool revisions and source materialization. |
| Stack orchestration | `scripts/build_stack.py`, `pipeline.toml` | Build, test and install pinned components; verify Runtime-reported package version. |
| Boundary checks | `scripts/check_boundaries.py`, `psx.yml` | Mechanical architecture/repository-shape checks; include-graph coverage is partial. |
| CLI E2E | `scripts/assert_cli.py`, root CTest entries | CLI success, invalid arguments and fail-closed launch paths. |
| Frontend smoke | `src/integration/frontend_smoke.c` | In-process HELLO/HELLO_ACK, real ATTACH, ordered initial UI snapshot, `ui.flush`/ACK and resize. |
| Source snapshot | `scripts/package.py` | Reproducible source ZIP, archive safety/CRC checks and SHA-256 sidecar. |
| Product E2E | `tests/e2e/README.md` | Documents live edit/save E2E still required. |
| Benchmarks | `tests/bench/README.md` | Measurement plan; no verified product RSS/soak benchmark. |

## 3. Verified versus incomplete

| Capability | Status | Evidence / limitation |
| --- | --- | --- |
| Immutable component source pins | IMPLEMENTED | `deps.lock`. |
| Full pinned stack build | PASS | CI run 42024750897 passed Linux, macOS and Windows jobs on candidate commit `167de187...`. |
| Backend package compatibility | IMPLEMENTED | Versioned Backend 1.0.0 CMake package is consumed with `find_package(cdinBackend 1.0.0 CONFIG REQUIRED)`. |
| Runtime version identity | VERIFIED for pinned revision | CI log reports Runtime `1.0.0-rc.1`, matching `deps.lock`; `build_stack.py` enforces this check. |
| Runtime hosting | VERIFIED for lifecycle smoke | Backend creates/owns Runtime; CDIN supplies root and entry. |
| Frontend Core protocol path | IMPLEMENTED; CI verification pending | HELLO/HELLO_ACK, ATTACH, initial snapshot delivery, ordered `ui.flush`/ACK and resize through in-process byte transport. |
| Interactive TUI/GUI launch | NOT IMPLEMENTED | No supported installed adapter/readiness event loop is connected. |
| View attach and UI snapshot | IMPLEMENTED; CI verification pending | Backend aggregate snapshot budget is separated from per-frame size in Backend PR #7; CDIN smoke now attaches, drains the snapshot and ACKs its final flush. |
| Document create/open/edit/save/reopen | NOT IMPLEMENTED in CDIN | No connected live Frontend product path. |
| Runtime command/keymap/plugin E2E | NOT VERIFIED | No real Frontend input path through the Composition Root. |
| CLI fail-closed paths | PASS | Nine CDIN CTest cases passed on all three native platforms. |
| ASan/UBSan/leak checks | PASS | Linux sanitizer job in run 42024750897 passed. |
| C/C++ and Python CodeQL | PASS | Run 42024750919 completed both analyses successfully. |
| Source snapshot integrity | PASS | Determinism, archive safety, CRC and SHA-256 verified on Linux, macOS and Windows. |
| Product RSS/soak/latency benchmarks | NOT IMPLEMENTED | Existing benchmark material is a plan, not product measurements. |
| Application installers | NOT IMPLEMENTED | Source archive is not a runnable application package. |

## 4. CI and security verification

CI run [42024750897](https://github.com/cdin-editor/cdin/actions/runs/42024750897) completed successfully on candidate commit `167de187af4f0d4df8a81c9afb86ba887eaf6cb4` for Linux, macOS, Windows and Linux ASan/UBSan/leak detection. The run also passed nine CDIN CTest cases on each platform, the pinned component suites, reproducible archive verification, SHA-256 comparison and source artifact upload.

CodeQL run [42024750919](https://github.com/cdin-editor/cdin/actions/runs/42024750919) completed successfully for traced C/C++ and Python analysis.

The GitHub Code Quality dynamic workflow [42025677183](https://github.com/cdin-editor/cdin/actions/runs/42025677183) passed Python but failed JavaScript/TypeScript because the extractor found only YAML configuration files and no JS/TS source. This language selection belongs to the repository's Settings → Security → Code quality configuration, not to `.github/workflows/codeql.yml`. The repository-owned C/C++ and Python CodeQL workflow is independent and passed.

The current action-pinned run emitted no Node.js 20 deprecation warning in the Linux, macOS or Windows logs inspected. OIDC and attestation permissions are isolated to a separate trusted-main job; PR build jobs receive only `contents: read`.

## 5. Compatibility findings

- **Runtime version identity:** the prior discrepancy is resolved for the pinned Runtime revision. CI logs show the exact `1.0.0-rc.1` version recorded in `deps.lock`; the build rejects a mismatch.
- **Backend package:** versioned CMake package discovery is enforced at 1.0.0; do not regress to unversioned header/library discovery.
- **Frontend adapter:** the TUI target is experimental/unexported by Frontend Core 1.0.0. CDIN must consume an installable supported adapter, not copy sources into the Composition Root.
- **Snapshot limits:** the pinned Backend used the 16 KiB per-frame limit as an aggregate snapshot limit. Backend PR [#7](https://github.com/cdin-editor/backend/pull/7) adds a separate bounded 4 MiB snapshot budget (64 MiB hard maximum) while retaining the per-frame cap; CDIN pins the immutable PR head and exercises ATTACH/snapshot/ACK. Native CI is still required to verify the candidate.
- **Readiness integration:** Backend exposes a worker-completion wakeup callback, but CDIN still needs a real readiness-driven event loop that combines terminal readiness, Backend wakeups, resize and termination.
- **Static include boundaries:** the current boundary script catches selected copied implementation calls but does not parse the compiler's full include graph. It is a guardrail, not a proof of all architectural include rules.
- **GitHub Code Quality:** deselect JavaScript/TypeScript in Settings → Security → Code quality; keep the repository-owned CodeQL workflow for C/C++ and Python.

## 6. Remaining release gates

1. Run native CI for Backend PR #7 and CDIN PR #110; verify ATTACH, initial snapshot, ordered UI flush/ACK and resize end-to-end.
2. Obtain an installable Frontend TUI adapter or another supported Frontend adapter.
3. Implement the FE-019 readiness multiplexer and connect Backend wakeups.
4. Add live product E2E for create/open/edit/save/reopen and exact-byte preservation.
5. Verify Runtime command/keymap dispatch through actual Frontend input.
6. Verify plugin loading, capability isolation, failure handling and unload.
7. Verify detach/reconnect, multiple Frontends and failure recovery.
8. Keep native platform CI, sanitizer checks and both CodeQL language analyses green on every release candidate.
9. Add measured RSS, allocator peak, leaks, soak and latency benchmarks.
10. Build platform installers and publish signed application release artifacts only after the live editing path is complete.

The owner-visible epic and its acceptance criteria are tracked in [issue #111](https://github.com/cdin-editor/cdin/issues/111). A green component CI is necessary, but it is not proof that CDIN is already an interactive editor.
