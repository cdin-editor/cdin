# Architecture audit

**Audit baseline:** CDIN branch `feature/complete-composition-root-rewrite`, component revisions in `deps.lock`, and repository evidence inspected on 2026-11-05.

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
| CLI and launcher | `src/main.c`, `src/cli/options.c` | Parse options and compose Backend lifecycle. |
| Diagnostics | `src/diagnostics/log.c`, `include/cdin/log.h` | CDIN logger setup and Backend callback adapter. |
| Dependency pins | `deps.lock`, `scripts/deps.py` | Immutable component/tool revisions and source materialization. |
| Stack orchestration | `scripts/build_stack.py`, `pipeline.toml` | Build, test and install pinned components. |
| Boundary checks | `scripts/check_boundaries.py`, `psx.yml` | Mechanical architecture/repository-shape checks. |
| CLI E2E | `scripts/assert_cli.py`, root CTest entries | CLI behavior and lifecycle smoke. |
| Frontend smoke | `src/integration/frontend_smoke.c` | In-process Frontend Core HELLO/HELLO_ACK only. |
| Product E2E | `tests/e2e/README.md` | Documents live edit/save E2E still required. |
| Benchmarks | `tests/bench/README.md` | Measurement plan; no verified product RSS/soak benchmark. |

## 3. Verified versus incomplete

| Capability | Status | Evidence / limitation |
| --- | --- | --- |
| Immutable component source pins | IMPLEMENTED | `deps.lock`. |
| Full pinned stack build | VERIFIED | CI run 42009406506 passed Linux, macOS and Windows jobs for commit `4ab4064...`. |
| Backend package compatibility | IMPLEMENTED | Backend 1.0.0 versioned CMake package is consumed with `find_package(cdinBackend 1.0.0 CONFIG REQUIRED)`. |
| Runtime hosting | VERIFIED for lifecycle smoke | Backend creates/owns Runtime; CDIN supplies root and entry. |
| Frontend Core handshake | VERIFIED for headless smoke | HELLO/HELLO_ACK through in-process byte transport. |
| Interactive TUI/GUI launch | NOT IMPLEMENTED | No supported installed adapter/readiness event loop is connected. |
| View attach and UI snapshot | NOT VERIFIED | An earlier attempt returned `CDIN_BACKEND_LIMIT_EXCEEDED`; current smoke deliberately stops at handshake. |
| Document create/open/edit/save/reopen | NOT IMPLEMENTED in CDIN | No connected live Frontend product path. |
| Runtime command/keymap/plugin E2E | NOT VERIFIED | No real Frontend input path through the Composition Root. |
| ASan/UBSan/leak checks | PASS for inspected baseline | CI run 42009406506 sanitizer job passed. |
| Product RSS/soak/latency benchmarks | NOT IMPLEMENTED | Existing benchmark material is a plan, not product measurements. |
| Platform installers | NOT IMPLEMENTED | Source archive is not a runnable application package. |

## 4. CI and security verification

CI run [42009406506](https://github.com/cdin-editor/cdin/actions/runs/42009406506) completed successfully for Linux, macOS, Windows and Linux ASan/UBSan/leak detection on commit `4ab4064af53f347ee714e57c3c2e936310f12673`. The later `9bc6ed3...` commit changed documentation only; the new CI run for that latest head must still be inspected before claiming the latest commit is verified.

The successful jobs verify the pinned component stack, CLI/lifecycle smoke and Frontend Core HELLO/HELLO_ACK handshake. They do not verify view attachment, UI snapshot delivery, rendering, editing, persistence, keymap dispatch or plugin behavior.

The previous CodeQL auto-configuration attempted JavaScript/TypeScript analysis despite no JS/TS source being present. A dedicated workflow now targets C/C++ and Python separately; its first successful run is still a release-quality check.

## 5. Compatibility findings

- **Runtime version identity:** lock/status metadata says candidate `1.0.0-rc.1`, while an earlier Runtime self-report in CI was `0.2.1-beta.10.next.17+gc7b50b8`. Resolve Git-derived package versioning and release metadata before publishing.
- **Frontend adapter:** the TUI target is experimental/unexported by Frontend Core 1.0.0. CDIN must consume an installable supported adapter, not copy sources into the Composition Root.
- **Snapshot limits:** initial Runtime UI snapshot publication previously returned `CDIN_BACKEND_LIMIT_EXCEEDED`. The current handshake smoke does not bypass this by increasing message limits or claim snapshot delivery.
- **Readiness integration:** Backend exposes a worker-completion wakeup callback, but CDIN still needs a real readiness-driven event loop that combines terminal readiness, Backend wakeups, resize and termination.

## 6. Remaining release gates

1. Resolve the Backend initial UI snapshot limit and verify ATTACH, UI flush/ACK and resize.
2. Obtain an installable Frontend TUI adapter or another supported Frontend adapter.
3. Implement the FE-019 readiness multiplexer and connect Backend wakeups.
4. Add live product E2E for create/open/edit/save/reopen and exact-byte preservation.
5. Verify Runtime command/keymap dispatch through actual Frontend input.
6. Verify plugin loading, capability isolation, failure handling and unload.
7. Verify detach/reconnect, multiple Frontends and failure recovery.
8. Keep native platform CI and sanitizer checks green on the current head.
9. Add measured RSS, allocator peak where available, leaks, soak and latency benchmarks.
10. Build platform installers and publish release artifacts only after the live editing path is complete.

A green component CI is necessary, but it is not proof that CDIN is already an interactive editor.
