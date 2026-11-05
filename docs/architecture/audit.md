# Architecture audit

**Audit baseline:** CDIN branch `feature/complete-composition-root-rewrite`, current tip `3b3542c8130462a425aa09cdb0be5ce29f09d4a3`; expanded document-smoke code validated on Linux and Windows in run `42073455899` (with Linux ASan/UBSan/leak detection), macOS job queued; component revisions in `deps.lock`, inspected on 2026-11-05.

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
| Frontend smoke | `src/integration/frontend_smoke.c` | In-process HELLO/HELLO_ACK/ATTACH, ordered UI snapshot/flush/ACK/resize plus document new, text/binary paste, Runtime undo/redo/save keymaps, close/open and byte-exact `view.request_lines` readback. Current native CI validation is pending. |
| Source snapshot | `scripts/package.py` | Reproducible source ZIP, archive safety/CRC checks and SHA-256 sidecar. |
| Product E2E | `src/integration/frontend_smoke.c`, `tests/e2e/README.md` | A headless end-to-end document cycle is implemented through the public Frontend/Backend/Runtime/Kernel APIs; current CI validation is pending. Interactive TUI and multi-frontend product E2E remain. |
| Benchmarks | `tests/bench/README.md` | Measurement plan; no verified product RSS/soak benchmark. |

## 3. Verified versus incomplete

| Capability | Status | Evidence / limitation |
| --- | --- | --- |
| Immutable component source pins | IMPLEMENTED | `deps.lock`. |
| Full pinned stack build | PASS | CI run 42024750897 passed Linux, macOS and Windows jobs on candidate commit `167de187...`. |
| Backend package compatibility | IMPLEMENTED | Versioned Backend 1.0.2 CMake package is consumed with `find_package(cdinBackend 1.0.2 CONFIG REQUIRED)`; it includes the optional bounded binary-safe Host file reader. |
| Runtime version identity | VERIFIED for pinned revision | CI log reports Runtime `1.0.0-rc.1`, matching `deps.lock`; `build_stack.py` enforces this check. |
| Runtime hosting | VERIFIED for lifecycle smoke | Backend creates/owns Runtime; CDIN supplies root and entry. |
| Frontend Core protocol path | VERIFIED on Linux/macOS/Windows | HELLO/HELLO_ACK, real ATTACH, initial snapshot delivery, ordered `ui.flush`/ACK, queue release and resize through Frontend Core over in-process byte transport; CI run 42051385717 passed. |
| Interactive TUI/GUI launch | PARTIAL / NOT LAUNCHABLE | Frontend now installs/exports `cdin::frontend_ui_tui`, but CDIN has not connected it to a native FE-019 readiness/wakeup/terminal-restore loop. GUI-SDL is not launched. |
| View attach and UI snapshot | VERIFIED on Linux/macOS/Windows | Backend PRs #7–#9 are merged. The smoke validates the six-message initial snapshot, snapshot-scoped `ui.flush`, ACK-based queue release and resize. Linux, macOS and Windows E2E plus Linux sanitizers pass in CI run 42051385717. |
| Document create/open/edit/save/reopen | IMPLEMENTED IN HEADLESS SMOKE; CI PENDING | The new CDIN smoke runs commands and input over a real Frontend Protocol session, saves through Backend Host I/O and compares reopened Kernel line bytes with the saved file. Awaiting current native CI. |
| Runtime command/keymap E2E | IMPLEMENTED IN HEADLESS SMOKE; CI PENDING | `request.command`, text/paste and Ctrl+Z/Ctrl+Shift+Z/Ctrl+S are sent over the public session API; plugin lifecycle remains NOT VERIFIED in CDIN. |
| CLI fail-closed paths | PASS | Nine CDIN CTest cases passed on all three native platforms. |
| ASan/UBSan/leak checks | PASS | Linux sanitizer job in run 42024750897 passed. |
| CodeQL scanning | DEFAULT SETUP ACTIVE | The repository CodeQL Default Setup is enabled. The branch no longer adds a competing advanced-mode `.github/workflows/codeql.yml`; run 42051385905 showed that advanced SARIF uploads are rejected while Default Setup is enabled. |
| Source snapshot integrity | PASS | Determinism, archive safety, CRC and SHA-256 verified on Linux, macOS and Windows. |
| Product RSS/soak/latency benchmarks | NOT IMPLEMENTED | Existing benchmark material is a plan, not product measurements. |
| Application installers | NOT IMPLEMENTED | Source archive is not a runnable application package. |

## 4. CI and security verification

CI run [42051385717](https://github.com/cdin-editor/cdin/actions/runs/42051385717) completed successfully on candidate `239b3ad69d573f8ca8b4b99e7825c15309c03553` for the attach-only path: Linux, macOS and Windows pinned-stack E2E plus Linux ASan/UBSan/leak detection passed. The expanded document workflow passed Linux and Windows plus Linux sanitizers in [run 42073455899](https://github.com/cdin-editor/cdin/actions/runs/42073455899); macOS remains queued. The Linux test log explicitly records `Frontend attach smoke passed: snapshot revision=0 messages=6 ordered flush/ACK and resize`. The current branch tip only removes the redundant CodeQL workflow file; product code is unchanged from the passing candidate.

Repository CodeQL **Default Setup** is enabled. The custom advanced CodeQL workflow produced `CodeQL analyses from advanced configurations cannot be processed when the default setup is enabled` in [run 42051385905](https://github.com/cdin-editor/cdin/actions/runs/42051385905). The custom `.github/workflows/codeql.yml` was therefore removed from this branch; Default Setup remains the repository's scanner. The precise language selection of Default Setup still needs to be checked in repository settings.

The separate GitHub Code Quality dynamic workflow [run 42052219702](https://github.com/cdin-editor/cdin/actions/runs/42052219702) passes Python but fails JavaScript/TypeScript because its extractor sees only YAML configuration and no JS/TS source. That language selection belongs to Settings → Security → Code quality, not to `.github/workflows/codeql.yml`; deselect JavaScript/TypeScript there.

The current action-pinned run emitted no Node.js 20 deprecation warning in the Linux, macOS or Windows logs inspected. OIDC and attestation permissions are isolated to a separate trusted-main job; PR build jobs receive only `contents: read`.

## 5. Compatibility findings

- **Runtime version identity:** the prior discrepancy is resolved for the pinned Runtime revision. CI logs show the exact `1.0.0-rc.1` version recorded in `deps.lock`; the build rejects a mismatch.
- **Backend package:** versioned CMake package discovery is enforced at 1.0.2; the optional bounded binary-safe Host read is Backend-owned.
- **Frontend adapter:** merged Frontend PR #2 installs/exports `cdin::frontend_ui_tui` and public headers, verified by a clean-prefix external consumer. CDIN must use the package target and not copy sources. FE-019 readiness/wakeup/terminal restoration still blocks interactive launch.
- **Snapshot limits:** Backend PR [#7](https://github.com/cdin-editor/backend/pull/7) separates the 16 KiB per-frame cap from the 4 MiB default/64 MiB maximum aggregate snapshot budget. Backend PR [#8](https://github.com/cdin-editor/backend/pull/8) fixes the reported package version, and [#9](https://github.com/cdin-editor/backend/pull/9) fixes optional Runtime `options` projection and HELLO_ACK driver role. All three are merged; CDIN pins the immutable Backend 1.0.1 revision. ATTACH/snapshot/ACK/resize passes three-platform CI.
- **Readiness integration:** Backend exposes a worker-completion wakeup callback, but CDIN still needs a real readiness-driven event loop that combines terminal readiness, Backend wakeups, resize and termination.
- **Static include boundaries:** the current boundary script catches selected copied implementation calls but does not parse the compiler's full include graph. It is a guardrail, not a proof of all architectural include rules.
- **GitHub Code Quality:** deselect JavaScript/TypeScript in Settings → Security → Code quality; the Python Code Quality job passes. The repository CodeQL Default Setup is enabled, so this branch removes the duplicate advanced workflow. Verify Default Setup has the intended C/C++ and Python languages selected.

## 6. Remaining release gates

1. Keep Backend ATTACH/snapshot/flush/ACK/resize and the expanded headless document workflow covered by native CI; current expanded smoke validation is pending.
2. Connect the published Frontend TUI package to an interactive launch path.
3. Implement the FE-019 readiness multiplexer and connect Backend wakeups.
4. Complete interactive TUI E2E for rendering, input, resize, terminal restoration and shutdown.
5. Verify Runtime command/keymap dispatch through actual Frontend input.
6. Verify plugin loading, capability isolation, failure handling and unload.
7. Verify detach/reconnect, multiple Frontends and failure recovery.
8. Keep native platform CI and sanitizer checks green; verify the CodeQL Default Setup language selection and keep the separate Python Code Quality job green after disabling JS/TS.
9. Add measured RSS, allocator peak, leaks, soak and latency benchmarks.
10. Build platform installers and publish signed application release artifacts only after the live editing path is complete.

The owner-visible epic and its acceptance criteria are tracked in [issue #111](https://github.com/cdin-editor/cdin/issues/111). A green component CI is necessary, but it is not proof that CDIN is already an interactive editor.
