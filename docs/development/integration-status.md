# Integration status and release gates

This document reports capabilities exercised by the CDIN Composition Root, not merely features exposed by a component. A green component build does not prove that the complete editor is usable.

The product epic and acceptance criteria are tracked in [issue #111](https://github.com/cdin-editor/cdin/issues/111). The current integration candidate is developed on `feature/complete-composition-root-rewrite` through [PR #110](https://github.com/cdin-editor/cdin/pull/110), which remains Draft while the live TUI gate is unresolved.

## 1. Verified in CDIN

| Capability | Status | Evidence |
| --- | --- | --- |
| Immutable dependency pins and stack build | IMPLEMENTED | `deps.lock`, `scripts/deps.py`, `scripts/build_stack.py`. |
| Versioned package discovery | VERIFIED | CDIN requires the versioned Backend package and checks Backend ABI plus Backend/Frontend Protocol versions. Runtime's reported version is compared with the immutable lock entry. |
| Backend lifecycle | VERIFIED | `--check` calls Backend create/start/pump/shutdown/destroy and routes Backend log callbacks into the CDIN logger. |
| Headless Frontend Protocol | PASS on Linux/macOS/Windows | HELLO/HELLO_ACK, ATTACH, ordered UI snapshot, `ui.flush`/ACK, queue release and resize are exercised over the public Frontend session API. |
| Document editing workflow | PASS on Linux/macOS/Windows | `document.new/open/close`, text and binary paste, undo/redo, atomic save and version-pinned line readback run through Frontend → Backend → Runtime → Kernel. |
| Byte preservation | PASS on Linux/macOS/Windows | Fixtures cover NUL, invalid UTF-8, BOM, LF-only and mixed CRLF/LF/CR data; saved and reopened bytes are compared exactly. |
| Filesystem failure recovery | PASS on Linux/macOS/Windows | Missing-file read and failed atomic save are exercised; the in-memory document remains intact and a subsequent valid save succeeds. |
| CLI validation | PASS | Help/version, invalid values, unknown options and fail-closed frontend selections are covered by executable-level CTest. A help assertion now checks the advertised `headless|tui` choices. |
| Architecture check unit tests | PASS on Windows | Six tests cover installed-header allow, private source/build header deny, compiler probe flag handling and include-trace parsing. |
| Compiler-resolved include graph | PASS on Windows | GCC include tracing covered all four CDIN translation units and found no private component source/build headers. |
| Source snapshot and hash | PASS in earlier native matrix | Deterministic source ZIP, archive safety/CRC checks and SHA-256 sidecar are part of the pipeline. This is a source archive, not an application installer. |

### Latest completed native evidence

[CI run 42117574266](https://github.com/cdin-editor/cdin/actions/runs/42117574266) inspected candidate commit `dd1f5896c27756948750a1adc1770b16b4207b66`.

- Windows completed the stack build and all 9/9 CDIN CTest cases. Its `--check` log explicitly records the document smoke, BOM/LF/mixed-EOL fixture smoke and filesystem-failure recovery smoke. The 6 architecture unit tests passed and the compiler-resolved include audit reported 4 CDIN translation units with no private component headers.
- Linux and macOS each passed the Frontend component suite (19/19) and the headless CDIN CTest, including the headless protocol/document path. Each failed only at the live POSIX test `cdin_tui_live_pty_smoke` (9/10 root CTest tests passed).
- The ASan/UBSan/leak job failed on the same live TUI test; this does not constitute a separate sanitizer finding.
- On Linux/macOS the failed TUI gate stops the stack task before the later architecture include-graph task. Cross-platform include-graph execution is therefore not yet established; the Windows result is verified.

A later CLI-help wording correction and its regression CTest were added after this completed run. The latest Cdin CI for that revision is the run linked from the current branch checks; do not transfer the earlier result to a later SHA without checking its workflow status.

## 2. Experimental TUI status

The POSIX path is present in `src/integration/frontend_smoke.c` and is deliberately gated by `CDIN_ENABLE_EXPERIMENTAL_TUI=1`. Without the opt-in, the launcher returns status 3 and prints that interactive launch remains gated. The CI PTY harness sets the opt-in explicitly.

The live path opens the terminal, installs SIGWINCH/SIGTERM/SIGINT wakeup handling, attaches a Frontend Protocol session, applies and ACKs the initial snapshot, creates a scratch document, then runs the Frontend TUI event loop with bounded terminal and Backend draining, resize handling, rendering and orderly teardown. The PTY test checks title/render, input, SIGWINCH interruption, save+quit with pending UI work, separate SIGTERM shutdown, startup failure and restoration of terminal flags/modes.

The current failure is in Frontend's line-request lifecycle. A snapshot may preserve the same document version and line-window target while `lines_invalidated` remains set; the previous model logic cleared `request_pending` anyway. The matching `view.lines` response then arrived with the correct view/version/first-line but was rejected because the model believed no request was outstanding. A Frontend-owned fix with regression tests is under [PR #11](https://github.com/cdin-editor/frontend/pull/11):

- preserve the pull while a snapshot keeps the same request identity;
- cancel only when the committed snapshot changes document version or first-line target;
- treat duplicate/obsolete line responses as stale no-ops while continuing to reject malformed and future-version responses.

At the latest inspection, PR #11 had green Ubuntu, Windows and Pipeline/quality jobs; macOS was still queued. It must not be treated as merged or fully cross-platform verified until macOS completes. CDIN currently pins the diagnostics-only Frontend revision `d890217d89e4da3f14ca51ab01d373f52788b8cc`; after PR #11 is verified and merged, `deps.lock` must be advanced to its immutable merge commit and CDIN CI rerun.

Windows TUI remains fail-closed until a native Console readiness/restore adapter is implemented. GUI-SDL launch is not implemented.

## 3. Architecture and security checks

### Compiler-resolved include graph

`scripts/check_include_graph.py` consumes the generated CMake `compile_commands.json` and asks the configured compiler to emit its resolved include trace (`-E -H`). It rejects headers resolved from component source checkouts or private component build trees and allows headers from the installed component prefix. `scripts/check_boundaries.py` also runs the six Python policy tests.

This is stronger than checking literal `#include` spellings, but it is not a proof of every cross-component semantic dependency rule. Windows CI verified the current graph for all four CDIN translation units. Linux and macOS must run the same task once the preceding TUI gate is green.

### GitHub Code Quality

The separate GitHub Code Quality dynamic workflow still attempts JavaScript/TypeScript analysis even though this repository has no JavaScript/TypeScript source. Its Python job passes; the JS/TS job fails after extracting YAML-only configuration files. This selection is controlled by repository Settings → Security → Code quality, not by the checked-in Pipeline configuration. Deselect JavaScript/TypeScript there and retain Python.

### CodeQL

The repository uses GitHub CodeQL Default Setup. The custom advanced workflow was removed to avoid conflicting SARIF uploads while Default Setup is enabled. Verify in repository Security settings that Default Setup scans the intended C/C++ and Python languages. That settings review cannot be completed by a source commit.

### Artifact provenance

The reproducible source snapshot and trusted-main provenance flow are source-distribution evidence only. PR jobs do not receive attestation permissions; the trusted-main job is intentionally skipped for pull requests. A source ZIP is not a runnable application installer or release package.

## 4. Not complete

| Area | Status | Remaining work |
| --- | --- | --- |
| Live TUI on POSIX | BLOCKED | Merge and pin the Frontend request-lifecycle fix, rerun Linux/macOS/Windows and sanitizers, and pass the real PTY smoke. |
| Windows TUI | NOT IMPLEMENTED | Native Console readiness, input/resize multiplexer and restoration. |
| GUI-SDL | NOT IMPLEMENTED | Adapter composition, lifecycle and GUI E2E. |
| Runtime/plugin lifecycle | NOT VERIFIED FROM CDIN | Live plugin load/unload, capability grant/deny, failure isolation and configuration/command error propagation. |
| Multiple Frontends and recovery | NOT VERIFIED FROM CDIN | Driver/observer roles, detach/reattach, disconnect/reconnect, partial-startup recovery and repeated shutdown. |
| Performance | NOT IMPLEMENTED | RSS/peak memory, allocation/leak profile, latency p50/p95/p99 and long-running soak workloads. |
| Application installers | NOT IMPLEMENTED | Native Linux/macOS/Windows packages, runtime discovery, clean-machine install/upgrade/uninstall and checksums/provenance. |
| Stable release | NOT READY | Requires all interactive, recovery, security, performance and packaging gates above. |

Registry handoff is deliberately not a blocker for this epic; it is a later, product-neutral infrastructure concern.

## 5. Ordered release gates

1. Merge the Frontend TUI request-lifecycle fix only after its complete native CI matrix passes.
2. Update CDIN's immutable Frontend pin and rerun the entire CDIN Linux/macOS/Windows and sanitizer matrix.
3. Pass the live POSIX PTY test, including render, edit, save, resize/signal interruption, terminal restoration and shutdown.
4. Run the compiler-resolved include graph on Linux, macOS and Windows.
5. Keep the exact-byte and filesystem-failure smoke tests green on all native platforms.
6. Implement and test Windows TUI and GUI-SDL launch paths.
7. Verify plugin/capability lifecycle, multiple Frontends, detach/reconnect and failure recovery.
8. Add measured resource budgets, latency distributions and soak/leak tests.
9. Build clean-machine installable application packages and sign the release artifacts.
10. Complete repository Code Quality/CodeQL settings review and keep the intended language analyzers green.

The epic remains open until these release gates are verified. Configured workflows, partial output or a green component suite must not be marked as product-level PASS.
