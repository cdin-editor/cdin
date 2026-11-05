# Architecture audit

**Audit baseline:** CDIN branch `feature/complete-composition-root-rewrite`, candidate commit `9dfca4d5ec8ad3ce5271d0ae59e591e4f03f2353`, component revisions in `deps.lock`, inspected on 2026-11-05.

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
| Frontend smoke | `src/integration/frontend_smoke.c` | In-process Frontend Core HELLO/HELLO_ACK only. |
| Source snapshot | `scripts/package.py` | Reproducible source ZIP, archive safety/CRC checks and SHA-256 sidecar. |
| Product E2E | `tests/e2e/README.md` | Documents live edit/save E2E still required. |
| Benchmarks | `tests/bench/README.md` | Measurement plan; no verified product RSS/soak benchmark. |

## 3. Verified versus incomplete

| Capability | Status | Evidence / limitation |
| --- | --- | --- |
| Immutable component source pins | IMPLEMENTED | `deps.lock`. |
| Full pinned stack build | PASS | CI run 42023541244 passed Linux, macOS and Windows jobs on candidate commit `9dfca4d...`. |
| Backend package compatibility | IMPLEMENTED | Versioned Backend 1.0.0 CMake package is consumed with `find_package(cdinBackend 1.0.0 CONFIG REQUIRED)`. |
| Runtime version identity | VERIFIED for pinned revision | CI log reports Runtime `1.0.0-rc.1`, matching `deps.lock`; `build_stack.py` enforces this check. |
| Runtime hosting | VERIFIED for lifecycle smoke | Backend creates/owns Runtime; CDIN supplies root and entry. |
| Frontend Core handshake | VERIFIED for headless smoke | HELLO/HELLO_ACK through in-process byte transport. |
| Interactive TUI/GUI launch | NOT IMPLEMENTED | No supported installed adapter/readiness event loop is connected. |
| View attach and UI snapshot | NOT VERIFIED | An earlier attempt returned `CDIN_BACKEND_LIMIT_EXCEEDED`; current smoke deliberately stops at handshake. |
| Document create/open/edit/save/reopen | NOT IMPLEMENTED in CDIN | No connected live Frontend product path. |
| Runtime command/keymap/plugin E2E | NOT VERIFIED | No real Frontend input path through the Composition Root. |
| CLI fail-closed paths | PASS | Nine CDIN CTest cases passed on all three native platforms. |
| ASan/UBSan/leak checks | PASS | Linux sanitizer job in run 42023541244 passed. |
| C/C++ and Python CodeQL | PASS | Run 42023541330 completed both analyses successfully. |
| Source snapshot integrity | PASS | Determinism, archive safety, CRC and SHA-256 verified on Linux, macOS and Windows. |
| Product RSS/soak/latency benchmarks | NOT IMPLEMENTED | Existing benchmark material is a plan, not product measurements. |
| Application installers | NOT IMPLEMENTED | Source archive is not a runnable application package. |

## 4. CI and security verification

CI run [42023541244](https://github.com/cdin-editor/cdin/actions/runs/42023541244) completed successfully on candidate commit `9dfca4d5ec8ad3ce5271d0ae59e591e4f03f2353` for Linux, macOS, Windows and Linux ASan/UBSan/leak detection. The run also passed nine CDIN CTest cases on each platform, the pinned component suites, reproducible archive verification, SHA-256 comparison and source artifact upload.

CodeQL run [42023541330](https://github.com/cdin-editor/cdin/actions/runs/42023541330) completed successfully for traced C/C++ and Python analysis.

The GitHub-managed dynamic workflow [42023531270](https://github.com/cdin-editor/cdin/actions/runs/42023531270) passed Python but failed JavaScript/TypeScript because no processable JS/TS source exists. This Default Setup language selection is configured in GitHub repository settings, outside the committed workflows. The explicit C/C++ and Python workflow does not disable that separate configuration.

The preceding CI log emitted Node.js 20 deprecation warnings. The current action-pinned run emitted no matching Node.js 20 warning in the Linux, macOS or Windows logs inspected.

## 5. Compatibility findings

- **Runtime version identity:** the prior discrepancy is resolved for the pinned Runtime revision. CI logs show the exact `1.0.0-rc.1` version recorded in `deps.lock`; the build rejects a mismatch.
- **Backend package:** versioned CMake package discovery is enforced at 1.0.0; do not regress to unversioned header/library discovery.
- **Frontend adapter:** the TUI target is experimental/unexported by Frontend Core 1.0.0. CDIN must consume an installable supported adapter, not copy sources into the Composition Root.
- **Snapshot limits:** initial Runtime UI snapshot publication previously returned `CDIN_BACKEND_LIMIT_EXCEEDED`. The current handshake smoke does not bypass this by increasing message limits or claim snapshot delivery.
- **Readiness integration:** Backend exposes a worker-completion wakeup callback, but CDIN still needs a real readiness-driven event loop that combines terminal readiness, Backend wakeups, resize and termination.
- **Static include boundaries:** the current boundary script catches selected copied implementation calls but does not parse the compiler's full include graph. It is a guardrail, not a proof of all architectural include rules.
- **GitHub Default Setup:** its JavaScript/TypeScript selection remains a settings-level failure; the repository-owned CodeQL workflow covers the actual C/C++ and Python languages.

## 6. Remaining release gates

1. Resolve the Backend initial UI snapshot limit and verify ATTACH, UI flush/ACK and resize.
2. Obtain an installable Frontend TUI adapter or another supported Frontend adapter.
3. Implement the FE-019 readiness multiplexer and connect Backend wakeups.
4. Add live product E2E for create/open/edit/save/reopen and exact-byte preservation.
5. Verify Runtime command/keymap dispatch through actual Frontend input.
6. Verify plugin loading, capability isolation, failure handling and unload.
7. Verify detach/reconnect, multiple Frontends and failure recovery.
8. Keep native platform CI, sanitizer checks and both CodeQL language analyses green on every release candidate.
9. Add measured RSS, allocator peak, leaks, soak and latency benchmarks.
10. Build platform installers and publish signed application release artifacts only after the live editing path is complete.

A green component CI is necessary, but it is not proof that CDIN is already an interactive editor.
