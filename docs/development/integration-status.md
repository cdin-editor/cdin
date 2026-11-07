## Registry integration update — 2026-11-07

The Composition Root feature branch now contains the Registry-based component selection and source handoff described by [Registry integration](registry.md) and [Spec ROOT-010](https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md#L31-L31).

- Kernel, Runtime, Backend and Frontend own immutable release metadata in their component repositories. Frontend TUI and GUI-SDL are separately declared variants.
- CDIN contains only the TUI and GUI-SDL Product Definitions. The versioned Catalog Index now lives in the pinned Registry checkout at `catalogs/cdin-components/catalog-index.json`; the CDIN repository no longer stores component metadata URIs, repository URLs or a Catalog Index.
- The GUI-SDL product resolves both the TUI base adapter and GUI-SDL adapter, matching the current executable composition.
- Registry is pinned as a host build tool, runs its Go tests, validates the product/catalog documents, resolves and prepares sources, verifies and replays the Manifest. It is not a runtime dependency.
- Component versions and source revisions are read from the Resolved Manifest; component entries have been removed from `deps.lock`.
- The native CI matrix now includes TUI and GUI-SDL product profiles on Linux, macOS and Windows. The sanitizer job uses the GUI-SDL superset profile, exercising TUI, GUI-SDL and headless paths together.

**Status: IMPLEMENTED IN SOURCE / NOT VERIFIED.** The latest branch commits have not yet produced a confirmed successful full current-head CI run. Do not mark Registry integration accepted until all six native profile/OS jobs and the sanitizer job pass. The Runtime prerelease allowance is transitional. A separate Catalog publisher/release publication workflow remains outstanding.

## Current verification update — 2026-11-07

PR #110 is the active Draft integration candidate; consult the PR page for its current head SHA.

- Frontend PR #19 is merged at `1373715c23eb965445caa926de3a99d9c0246f81`; Registry selects this immutable source through the Frontend Release Metadata referenced by its Catalog Index rather than a component entry in CDIN's `deps.lock`.
- Runtime sandbox capability-denial unit coverage is in Runtime commit `e2f19e279e3194a6615ce213331639fde4f42e87`; Runtime CI run [42315040626](https://github.com/cdin-editor/runtime/actions/runs/42315040626) passed Linux, Windows, macOS, Pipeline quality and docs/workflow validation.
- CDIN's trusted extension CLI and PTY/ConPTY fixtures were corrected after the prior run exposed invalid Python triple-quoted Lua source. Current CLI/PTY/ConPTY fixtures now use one line-continuation backslash; the accidental duplicate ConPTY source block and stale capability sentinel were removed.
- The multi-session smoke now verifies exact Backend-owned document bytes survive abrupt peer loss and a new Protocol client reconnecting to the same Backend session (commit `6eb58fd`). This test is not accepted until the current matrix passes.
- Current native + ASan/UBSan/leak matrix: see the latest CI run attached to [PR #110](https://github.com/cdin-editor/cdin/pull/110); only the run for the current head is acceptance evidence.
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
- The current CDIN ConPTY failure before PR #19 was isolated to the readiness wait using a different handle from the terminal adapter's `CONIN$` read handle. PR #19 aligns the wait and read handles and restores the original standard input handle on teardown. The correction is merged and component-tested; CDIN acceptance is pending.
- PR #110 remains Draft. No supported release-mode interactive launch, complete plugin capability policy, process recovery, product-grade performance/soak evidence or native application installers are claimed.

## 1. Verified in CDIN

| Capability | Status | Evidence |
| --- | --- | --- |
| Registry component selection and immutable workspace | IMPLEMENTED / NOT VERIFIED | Component-owned `registry/releases/*.json`, Registry-owned Catalog Index, CDIN Product Definitions, `scripts/registry.py`, Resolved Manifest and product E2E assertions. Full current-head native/sanitizer CI is pending. |
| Registry release/contract resolution and package compatibility | IMPLEMENTED / NOT VERIFIED | Registry resolves Backend → Kernel/Runtime and the ABI/Host API/Protocol contracts; CMake and Runtime lifecycle checks consume versions from the Resolved Manifest. Current-head CI is pending. |
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

Windows TUI remains fail-closed until a native Console readiness/restore adapter is implemented. GUI-SDL launch is implemented in the current Composition Root candidate behind `CDIN_ENABLE_EXPERIMENTAL_GUI_SDL=1`, with a deterministic `--check` smoke. It is **NOT VERIFIED** until the current candidate compiles and that smoke passes on the native matrix and sanitizer job.

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
| GUI-SDL | IMPLEMENTED IN CANDIDATE / NOT VERIFIED | `src/integration/gui_sdl.c` composes Backend, Frontend Protocol Session and the installable SDL adapter; `cdin_gui_sdl_live_session_smoke` verifies Runtime document creation, SDL text input, Ctrl+S and exact-byte save. Current run 42296140965 stops at a missing private include path before this test executes. Interactive launch remains experimental and the current renderer is ASCII/debug text. |
| Runtime/plugin lifecycle | HEADLESS LIVE SMOKE PASS ON LINUX/MACOS; FULL RELEASE ACCEPTANCE OPEN | CDIN accepts `--extension-root` and repeated `--load-extension`; `cdin_trusted_extension_cli_smoke` creates a temporary extension and verifies its real Lua init/unload sentinels through the trusted Backend C API. This CTest passed on Linux/macOS in run `42199285019`; Linux ASan/UBSan/leak detection passed. The TUI launcher also calls the same trusted load/unload helpers, but no dedicated TUI-plus-extension PTY assertion is present. Capability allow/deny, failed-init/runtime failure isolation and Windows integration remain unverified. Runtime PR #6 and Backend PR #16 are merged; `deps.lock` now pins their merge commits. |
| Multiple Frontends and recovery | PARTIALLY VERIFIED | Two concurrent Frontend sessions, Driver/Observer permissions, negotiated promotion, detach/reattach lease reacquisition and input pass on Linux/macOS/Windows. Transport disconnect/reconnect while work is pending, document/session continuity under transport loss, process failure recovery, partial startup and repeated shutdown remain open. |
| Performance | PARTIAL / NOT A BASELINE | Short headless smoke reports per-platform sampled RSS and p50/p95/p99; allocator peak, defined editing workloads, input-to-visible/save latency, budgets and soak/leak workload remain open. |
| Application installers | NOT IMPLEMENTED | Native Linux/macOS/Windows packages, runtime discovery, clean-machine install/upgrade/uninstall and checksums/provenance. |
| Stable release | NOT READY | Requires all interactive, recovery, security, performance and packaging gates above. |

Registry handoff is deliberately not a blocker for this epic; it is a later, product-neutral infrastructure concern.

## 5. Ordered release gates

1. Complete the Windows ConPTY path: deliver terminal bytes through the opened CONIN$ handle, verify Frontend Protocol mutations and UI ACK/redraw, then assert exact save bytes and restoration. Keep Windows launch fail-closed until that test passes.
2. Fix the current CDIN GUI-SDL compile include path; pass the live Backend/Runtime SDL smoke, native matrix and sanitizer. Then complete text rendering/IME/pane capabilities before enabling a supported GUI release.
3. Finish trusted-extension release acceptance: make the real Lua init/unload smoke pass on all native platforms; test unknown/denied names plus initialization/runtime/unload failure cleanup; add a TUI-plus-extension PTY assertion; and document the administrator-controlled extension root. Runtime PR #6 and Backend PR #16 are merged, but capability policy and Windows validation are not yet green.
4. Exercise transport disconnect/reconnect with work pending, Backend/Runtime failure recovery, partial startup and repeated start/stop.
5. Define named editing workloads; collect allocator peak where available, input-to-visible/save latency, p50/p95/p99, raw per-platform results and a documented soak/leak run. The current benchmark is only a short headless smoke.
6. Produce Linux/macOS/Windows application installers and validate clean-machine dependency discovery, launch, basic editing, upgrade and uninstall; sign artifacts and verify embedded licenses/assets.
7. In Settings → Security → Code quality, deselect JavaScript/TypeScript and retain Python. CodeQL already passed C/C++, Python and Actions on the current SHA.
8. Keep CDIN PR #110 under independent review. Backend PR #13 is merged; the current dependency pin now uses its merge commit.

The PR remains Draft and issue #111 remains open; this work proves the current tested integration slice, not a stable editor release.

The epic remains open until these release gates are verified. Configured workflows, partial output or a green component suite must not be marked as product-level PASS.


## Dependency merge and current verification — 2026-11-06

Runtime PR [#6](https://github.com/cdin-editor/runtime/pull/6) is merged at `d2acb6f174edf127c3bf59e8e5d4aedcbef0d490`; Backend PR [#16](https://github.com/cdin-editor/backend/pull/16) is merged at `bdb3d17e1330b3fc5d2a4906ec212b3aa32905c1`. CDIN `deps.lock` now pins those merge commits (their source trees match the tested PR heads). Frontend remains pinned to PR #16's candidate SHA `8b4714d6e3501bc0e9387bd8c7cd233806ab18cc` while its ConPTY work remains open.

On the same component source trees, [CDIN run 42199285019](https://github.com/cdin-editor/cdin/actions/runs/42199285019) passed Linux and macOS native build/E2E and Linux ASan/UBSan/leak detection. Both POSIX runners passed all 16 root CTests, including `cdin_trusted_extension_cli_smoke` and `cdin_tui_live_pty_smoke`, and the compiler-resolved include graph. Windows failed before CTest while compiling Backend `src/runtime/extension_resolver.c`: GCC 16.2 reports two `-Wtype-limits` diagnostics as errors at the DWORD-to-`size_t` allocation guards (lines 190 and 686). The Windows resolver build is therefore **NOT PASS**.

The new merge-SHA CDIN run [42224282657](https://github.com/cdin-editor/cdin/actions/runs/42224282657) is currently running. Do not mark the native matrix complete until its Windows job passes or the compiler-guard issue is fixed and the rerun is inspected. CDIN PR #110 remains Draft; issue #111 remains open.


## GUI-SDL composition candidate

The candidate uses the immutable Frontend PR #17 source revision `552eedd14e3971e2b39d706804d4af57f8b2dc38` and the checksum-pinned SDL3 3.4.16 archive recorded in `deps.lock`. `scripts/build_stack.py` builds and installs SDL3, builds the Frontend SDL target, then configures CDIN with `CDIN_ENABLE_GUI_SDL=ON`. The CDIN executable owns the in-process transport callbacks and Backend lifecycle; the Frontend SDL library owns SDL window/events/rendering and the semantic model. No Backend, Runtime or Kernel private headers are added to the Frontend package.

The live-session smoke is intentionally a CI test path, not a second editor implementation: it attaches the GUI Driver Session, creates a temporary document through Runtime, pushes a deterministic SDL text event and Ctrl+S key event, and checks the saved bytes. The test is bounded and removes its temporary file on teardown. It does not prove production text shaping, full GUI interactions, reconnect or installer readiness.
