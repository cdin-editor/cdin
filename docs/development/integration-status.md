# Integration status and release gates

This document reports capabilities exercised by the CDIN Composition Root, not merely features exposed by a component. A green component build does not prove that the complete editor is usable.

The product epic and acceptance criteria are tracked in [issue #111](https://github.com/cdin-editor/cdin/issues/111). The current integration candidate is developed on `feature/complete-composition-root-rewrite` through [PR #110](https://github.com/cdin-editor/cdin/pull/110), which remains Draft. The current candidate validates the experimental POSIX PTY path; supported Windows TUI and GUI-SDL launch remain unimplemented.

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
| Architecture check unit tests | PASS on Linux/macOS/Windows | Six tests cover installed-header allow, private source/build header deny, compiler probe flag handling and include-trace parsing. |
| Compiler-resolved include graph | PASS on Linux/macOS/Windows | Compiler include tracing covered all four CDIN translation units on each platform and found no private component source/build headers. |
| Source snapshot and hash | PASS on Linux/macOS/Windows | Deterministic source ZIP, archive safety/CRC checks and SHA-256 sidecar validated on each native runner. This is a source archive, not an application installer. |

### Latest completed native evidence

[Current CDIN CI run 42182694691](https://github.com/cdin-editor/cdin/actions/runs/42182694691) passed on exact branch HEAD `6166fd2034194c3a8b5b13d4baa1d81adce3b14d`.

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

Windows TUI remains fail-closed until a native Console readiness/restore adapter is implemented. GUI-SDL launch is not implemented.

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
| Windows TUI | PARTIAL / BLOCKED | Frontend PR #16 adds the ConPTY console-buffer fallback. CDIN can enter the initial screen, but the current ConPTY smoke still fails to observe edited text; input delivery, Protocol ACK/redraw and terminal restoration must pass before launch can be enabled. |
| GUI-SDL | NOT IMPLEMENTED | Adapter composition, lifecycle and GUI E2E. |
| Runtime/plugin lifecycle | IMPLEMENTATION CANDIDATE / TEST PENDING | Backend PR #16 exposes trusted owner-thread load/unload C APIs over the secure resolver; CDIN now accepts --extension-root and repeated --load-extension in headless and TUI paths, with a real Lua init/unload CTest. The current Backend 1.2.0 pin is a Draft PR candidate; live native validation, capability allow/deny, failed-init rollback and cleanup still need green evidence. |
| Multiple Frontends and recovery | PARTIALLY VERIFIED | Two concurrent Frontend sessions, Driver/Observer permissions, negotiated promotion, detach/reattach lease reacquisition and input pass on Linux/macOS/Windows. Transport disconnect/reconnect while work is pending, document/session continuity under transport loss, process failure recovery, partial startup and repeated shutdown remain open. |
| Performance | PARTIAL / NOT A BASELINE | Short headless smoke reports per-platform sampled RSS and p50/p95/p99; allocator peak, defined editing workloads, input-to-visible/save latency, budgets and soak/leak workload remain open. |
| Application installers | NOT IMPLEMENTED | Native Linux/macOS/Windows packages, runtime discovery, clean-machine install/upgrade/uninstall and checksums/provenance. |
| Stable release | NOT READY | Requires all interactive, recovery, security, performance and packaging gates above. |

Registry handoff is deliberately not a blocker for this epic; it is a later, product-neutral infrastructure concern.

## 5. Ordered release gates

1. Complete the Windows ConPTY path: deliver terminal bytes through the opened CONIN$ handle, verify Frontend Protocol mutations and UI ACK/redraw, then assert exact save bytes and restoration. Keep Windows launch fail-closed until that test passes.
2. Implement GUI-SDL composition, launch, rendering, input and lifecycle tests.
3. Finish and verify the explicit trusted-extension lifecycle: run the real Lua init/unload smoke on all native platforms, test unknown/denied names and initialization/runtime/unload failure cleanup, and document the administrator-controlled extension root. Backend PR #16 must merge before this becomes a supported dependency.
4. Exercise transport disconnect/reconnect with work pending, Backend/Runtime failure recovery, partial startup and repeated start/stop.
5. Define named editing workloads; collect allocator peak where available, input-to-visible/save latency, p50/p95/p99, raw per-platform results and a documented soak/leak run. The current benchmark is only a short headless smoke.
6. Produce Linux/macOS/Windows application installers and validate clean-machine dependency discovery, launch, basic editing, upgrade and uninstall; sign artifacts and verify embedded licenses/assets.
7. In Settings → Security → Code quality, deselect JavaScript/TypeScript and retain Python. CodeQL already passed C/C++, Python and Actions on the current SHA.
8. Keep CDIN PR #110 under independent review. Backend PR #13 is merged; the current dependency pin now uses its merge commit.

The PR remains Draft and issue #111 remains open; this work proves the current tested integration slice, not a stable editor release.

The epic remains open until these release gates are verified. Configured workflows, partial output or a green component suite must not be marked as product-level PASS.
