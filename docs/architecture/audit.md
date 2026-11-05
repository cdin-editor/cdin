# Architecture audit

**Audit baseline:** the current Composition Root candidate uses immutable component pins from `deps.lock`. The latest fully completed native CDIN run inspected for the current integration direction is [run 42117574266](https://github.com/cdin-editor/cdin/actions/runs/42117574266), on candidate `dd1f5896c27756948750a1adc1770b16b4207b66`. Later commits update CLI help and documentation; their CI runs must be evaluated against their own HEAD SHAs.

This audit separates implemented source from behavior actually exercised by CDIN. It is not a claim that the complete editor or release package is finished.

## 1. Ownership model

- **Kernel:** document bytes, edits, snapshots, versions and undo/redo.
- **Runtime:** Lua policy, commands, keymaps, configuration and plugin lifecycle.
- **Backend:** Kernel/Runtime hosting, sessions, Protocol server, queues, file I/O and OS services.
- **Frontend:** input, semantic UI projection, layout, TUI event loop and rendering.
- **CDIN:** immutable pins, stack build/install, CLI, diagnostics, process composition and resource teardown.

CDIN must not duplicate document, keymap, plugin, protocol, session, input or rendering implementations. Normative references: [ARCH-001](https://github.com/cdin-editor/spec/blob/main/docs/architecture/overview.md#L113-L113), [ARCH-040–046](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L65-L71), [ROOT-001](https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md#L22-L22).

## 2. Composition Root inventory

| Area | Evidence | Assessment |
| --- | --- | --- |
| CLI and launch | `src/main.c`, `src/cli/options.c` | Headless `--check` and opt-in experimental POSIX `--frontend tui`; Windows TUI remains fail-closed. |
| Diagnostics | `src/diagnostics/log.c`, `include/cdin/log.h` | CDIN logger setup and Backend callback adapter; TUI logger is passed into Frontend Session/Model. |
| Dependency pins | `deps.lock`, `scripts/deps.py` | Immutable component/tool revisions. Frontend request-lifecycle fix still awaits PR #11 verification/merge and a new CDIN pin. |
| Stack orchestration | `scripts/build_stack.py`, `pipeline.toml` | Builds, tests and installs the pinned component stack; exports `compile_commands.json` for include auditing. |
| Architecture checks | `scripts/check_boundaries.py`, `scripts/check_include_graph.py` | Selected source-boundary checks plus compiler-resolved include traces and six policy unit tests. |
| Headless integration | `src/integration/frontend_smoke.c` | HELLO/HELLO_ACK/ATTACH, six-message snapshot/flush/ACK/resize, document new/edit/paste/undo/redo/save/close/open and exact byte readback. |
| POSIX TUI | `src/integration/frontend_smoke.c`, `scripts/tui_pty_smoke.py` | Real terminal/wakeup/event-loop adapter exists behind explicit opt-in; PTY test is currently failing on line-request lifecycle. |
| Source distribution | `scripts/package.py` | Reproducible source ZIP, path/CRC validation and SHA-256 sidecar. This is not an application installer. |
| Benchmarks | `tests/bench/README.md` | Workload/report specification only; no verified product RSS, latency or soak result. |

## 3. Verified versus incomplete

| Capability | Status | Evidence / limitation |
| --- | --- | --- |
| Immutable component source pins | IMPLEMENTED | `deps.lock`. |
| Backend/Runtime lifecycle | PASS in CDIN smoke | Backend create/start/pump/shutdown/destroy; Runtime version identity is checked against the pin. |
| Frontend Core Protocol | PASS in headless path | HELLO/HELLO_ACK, real ATTACH, ordered UI snapshot, `ui.flush`/ACK, queue release and resize. |
| Document new/edit/save/reopen | PASS in headless path | Public Frontend session APIs drive Runtime/Backend/Kernel; disk and reopened bytes are compared. |
| Byte preservation and file failures | PASS in inspected Windows run | BOM, LF-only and mixed CRLF/LF/CR fixtures; missing-file read, failed atomic commit, intact in-memory bytes and successful recovery. Linux/macOS headless CTest also passed in the same run, though the later PTY test failed. |
| CLI validation | PASS in inspected native jobs | Help/version, invalid/missing option values and fail-closed modes; a newer help regression now checks the advertised `headless|tui` choices and requires its own current-HEAD CI result. |
| Compiler-resolved include graph | PASS on Windows | Six Python architecture tests and compiler trace for all four CDIN translation units passed; the trace reported no private component source/build headers. Linux/macOS have not yet completed the task because the earlier PTY failure stops their stack pipeline first. |
| Experimental POSIX TUI | PARTIAL / NOT RELEASE-READY | Terminal setup, wake pipe, signal handling, attach/bootstrap and Frontend event-loop adapter exist. The live PTY test fails when the model loses `request_pending` before the matching `view.lines` response arrives. Frontend PR #11 contains the fix and regression coverage; macOS CI is still pending at the latest inspection. |
| Windows TUI | NOT IMPLEMENTED | Native Console readiness/input/restore bridge is absent; launcher fails closed. |
| GUI-SDL | NOT IMPLEMENTED | No GUI launch path in CDIN. |
| Plugin isolation and lifecycle | NOT VERIFIED FROM CDIN | Live load/unload, capability denial and failure isolation remain. |
| Multiple Frontends and recovery | NOT VERIFIED FROM CDIN | Driver/Observer roles, detach/reattach, reconnect and partial-startup recovery remain. |
| ASan/UBSan/leak gate | BLOCKED BY PTY | The inspected Linux sanitizer job failed on the same live PTY smoke; this is not a separate sanitizer diagnostic. Rerun once the Frontend request fix is pinned. |
| Source snapshot integrity | IMPLEMENTED | Deterministic source snapshot, archive safety/CRC and SHA-256 sidecar. Not a runnable application artifact. |
| Product RSS/soak/latency | NOT IMPLEMENTED | No measured product workload. |
| Application installers | NOT IMPLEMENTED | No clean-machine native installers or signed app releases. |

## 4. Native CI evidence

[CDIN run 42117574266](https://github.com/cdin-editor/cdin/actions/runs/42117574266) completed on candidate `dd1f5896c27756948750a1adc1770b16b4207b66`.

- **Windows:** full stack and 9/9 CDIN CTest cases passed. Logs record the document workflow, BOM/LF/mixed-EOL fixture, filesystem-failure recovery, six architecture unit tests and compiler-resolved include graph for four CDIN translation units.
- **Linux and macOS:** Frontend component suite 19/19 and headless CDIN CTest passed, but the live `cdin_tui_live_pty_smoke` failed (9/10 root CTest tests passed).
- **Linux sanitizer:** failed because the full-stack run includes the same PTY test; do not report this as a separate sanitizer defect.
- **Include graph:** Windows verified. Linux/macOS did not reach that later check after the PTY CTest failure.

The run is evidence for its recorded SHA only. Later commits require a fresh matching run. The trusted-main provenance job is intentionally skipped on PR builds.

## 5. Security and repository settings

### CodeQL

GitHub CodeQL Default Setup is enabled. The custom advanced workflow was removed to avoid a conflicting SARIF upload while Default Setup is active. Repository settings still need a manual review to confirm C/C++ and Python are selected.

### GitHub Code Quality

The separate GitHub-managed Code Quality workflow attempts JavaScript/TypeScript analysis even though this repository has no JS/TS source; its Python job passes and the JS/TS job fails after extracting YAML-only files. This is controlled under **Settings → Security → Code quality**, not by a repository source change. Deselect JavaScript/TypeScript and retain Python.

### Artifact provenance

The trusted-main attestation flow applies to reproducible source snapshots, not user-ready application installers. PR jobs do not receive OIDC/attestation permissions.

## 6. Remaining release gates

1. Verify and merge Frontend PR [#11](https://github.com/cdin-editor/frontend/pull/11) only after its complete Linux/macOS/Windows and Pipeline matrix passes.
2. Update CDIN's immutable Frontend pin to the merged commit and rerun the full CDIN native matrix plus Linux ASan/UBSan/leak detection.
3. Pass the real POSIX PTY workflow: render, input, resize/signal interruption, save/quit, terminal restoration and startup/shutdown failure.
4. Run compiler-resolved include graph checks on Linux, macOS and Windows.
5. Implement Windows TUI's native Console readiness/input/restore bridge.
6. Implement and verify GUI-SDL launch.
7. Verify live plugin load/unload, capability isolation, failure containment and configuration/command error propagation.
8. Verify multiple Frontends, Driver/Observer role, detach/reattach, reconnect and recovery.
9. Add measured RSS/allocator peak, latency p50/p95/p99, leak checks and soak workloads.
10. Produce reproducible, signed Linux/macOS/Windows application installers and test clean-machine install/upgrade/uninstall.
11. Complete the manual GitHub Code Quality and CodeQL language-selection review.

Registry handoff is deliberately not a blocker for this epic; it remains a later product-neutral infrastructure concern. The epic stays open until all required release gates are evidenced. A configured workflow or green component suite alone is not a product-level PASS.
