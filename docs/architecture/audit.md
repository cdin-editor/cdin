# Registry handoff update — 2026-11-07

The current Composition Root branch includes Registry-based component selection. Component-owned immutable metadata is published in Kernel, Runtime, Backend and Frontend; CDIN supplies TUI and GUI-SDL Product Definitions and a pinned Catalog Index input. The GUI-SDL product resolves the TUI base plus GUI-SDL adapter. Registry is pinned and built as a host tool, never linked into the editor.

The stack task validates the Product Definition/Catalog, resolves Backend's Kernel/Runtime dependencies and ABI/Host API/Frontend Protocol contracts, prepares immutable sources, verifies/replays the Manifest, and feeds those source units to the component build. Package versions are passed to CMake from the Resolved Manifest. The TUI/GUI-SDL six-way native matrix and sanitizer run are not yet confirmed green; this is **IMPLEMENTED IN SOURCE / NOT VERIFIED**. See [Registry integration](../development/registry.md) and [issue #111](https://github.com/cdin-editor/cdin/issues/111).

# Architecture audit

**Current candidate:** CDIN PR [#110](https://github.com/cdin-editor/cdin/pull/110), branch feature/complete-composition-root-rewrite, head 634075a92aeb5a6e58b817d2045d653dfbf8bbf2. Current native/sanitizer CI [42304522348](https://github.com/cdin-editor/cdin/actions/runs/42304522348) has been dispatched but its jobs have not started; the GUI live-session smoke is **NOT VERIFIED**. Earlier native attempts progressed through CDIN compilation and initial attach/snapshot, then failed to prove SDL text + Ctrl+S exact-byte save. Current fixes capture flush metadata before ACK reuses the protocol buffer, warm up SDL startup focus/resize events before synthetic input, and pin Frontend PR #17 candidate 1dd2fc0826d302883fa0e6bab0cbead3ec84a6d4, which dynamically binds the Runtime-generated view ID. No current-head GUI PASS is claimed.

Frontend component CI [42304001468](https://github.com/cdin-editor/frontend/actions/runs/42304001468) passed Linux/macOS/Windows, SDL3 AddressSanitizer model/adapter tests, package installation and a clean-prefix consumer. Backend PR #18 [native CI 42300963625](https://github.com/cdin-editor/backend/actions/runs/42300963625), [Live Runtime 42300963086](https://github.com/cdin-editor/backend/actions/runs/42300963086), [resource stress 42300963234](https://github.com/cdin-editor/backend/actions/runs/42300963234) and [Code Quality 42300958559](https://github.com/cdin-editor/backend/actions/runs/42300958559) all passed; Backend Issue #14 is closed. These are component results and do not substitute for CDIN live application smoke.

## 1. Ownership model

- **Kernel:** canonical document bytes, edits, versions, snapshots and undo/redo.
- **Runtime:** Lua 5.4 editor policy, commands, keymaps, configuration and extension execution.
- **Backend:** Runtime/Kernel hosting, sessions, Frontend Protocol server, file I/O and OS services.
- **Frontend:** protocol client, physical input, semantic UI model, presentation layout and terminal/window rendering.
- **Registry:** build-time Product Definition/Catalog validation, release/contract resolution, immutable source collection, Workspace and Resolved Manifest; no runtime linkage.\n- **CDIN:** Product Definitions, pinned Catalog Index input, stack orchestration, launcher, transport construction, application process lifecycle, integration tests and packaging.

CDIN must not copy document, keymap, plugin, session, protocol, input or renderer implementations from the component repositories. The GUI integration source constructs the transport and lifecycle only; SDL event translation and drawing remain in Frontend.

## 2. Composition Root inventory

| Area | Source | Current assessment |
| --- | --- | --- |
| CLI and launch dispatch | `src/main.c`, `src/cli/options.c` | Headless checks, experimental POSIX TUI, and an experimental GUI-SDL launch path are present. GUI-SDL is opt-in via `CDIN_ENABLE_EXPERIMENTAL_GUI_SDL=1`; its CI `--check` path runs with SDL dummy video. |
| Headless integration | `src/integration/frontend_smoke.c` | Public Frontend Session handshake/attach, ordered snapshot/flush/ACK/resize and document lifecycle; previously passed the Linux/macOS/Windows matrix and Linux sanitizers on CDIN run 42265415995. |
| POSIX TUI | `src/integration/frontend_smoke.c`, `scripts/tui_pty_smoke.py` | Experimental PTY-tested input/edit/save/quit and terminal restore on the previous fully green candidate. |
| Windows TUI | `scripts/tui_conpty_smoke.py` | Experimental ConPTY test exists and passed on the previous candidate; supported launch remains gated pending the broader Windows console contract. |
| GUI-SDL composition | `src/integration/gui_sdl.c` | Builds a real Backend/Runtime host, attaches the Frontend Protocol Driver Session, creates the SDL adapter, requests a document and drives the event/render loop. The smoke sends SDL text and Ctrl+S and requires exact saved bytes. The payload-view-after-ACK, SDL startup-event ordering and view-id assumptions have been corrected in the current candidate, but exact-byte GUI smoke has not yet passed on the current head. |
| GUI-SDL component package | `deps.lock`, Frontend PR #17 | Frontend pin `552eedd14e3971e2b39d706804d4af57f8b2dc38`; SDL3 3.4.16 is checksum-pinned. Frontend CI run 42295241142 passed native and SDL AddressSanitizer tests plus clean-prefix consumer installation. |
| Runtime extension lifecycle | `src/integration/frontend_smoke.c`, Backend PR #18 | CDIN has a temporary extension Lua init/unload smoke; Backend adds repeated-read, case-fold and read-failure tests. Backend PR #18 Linux Runtime integration, three-platform stress/sanitizers and Python quality passed, but resolver test execution on macOS/Windows remains open. |
| Source distribution | `scripts/package.py` | Reproducible source ZIP with archive validation and SHA-256. This is not an application installer. |
| Resource benchmarks | `tests/bench/` | Short headless smoke measurements exist; no product allocator peak, editing latency budget or long-running soak proof. |

## 3. Verified versus incomplete

| Capability | Status | Evidence / limitation |
| --- | --- | --- |
| Registry component resolution / stack orchestration | IMPLEMENTED / NOT VERIFIED | Component-owned release metadata, CDIN Catalog Index and Product Definitions, pinned Registry CLI, Resolved Manifest and source-workspace E2E. Full current-head native/sanitizer matrix is pending. `deps.lock` now retains non-component pins only. |
| Backend/Runtime lifecycle and headless editing | VERIFIED ON PREVIOUS CANDIDATE | CDIN CI run 42265415995 passed Linux, macOS, Windows and Linux ASan/UBSan/leak detection before the newest GUI source was added. |
| Frontend GUI-SDL package | VERIFIED AS COMPONENT | Frontend CI run 42295241142 passed native/Pipeline jobs, SDL3 AddressSanitizer tests, installed package and external CMake consumer. |
| CDIN GUI-SDL live session | IMPLEMENTED / NOT VERIFIED | The source compiles on the prior candidate and live smoke reaches attach/snapshot. Current candidate captures flush metadata before ACK, warms the SDL event loop before synthetic input, and pins the dynamic-view-binding Frontend. Current native/sanitizer run 42304522348 has not started its jobs; exact-byte SDL text + Ctrl+S is not yet proven. |
| TUI POSIX | VERIFIED ON PREVIOUS CANDIDATE; EXPERIMENTAL | Previous CDIN candidate passed PTY, input/save/quit and restoration on Linux/macOS. |
| TUI Windows | EXPERIMENTAL / NOT RELEASE-READY | ConPTY test exists; native Console contract and broader input semantics remain gated. |
| Backend resolver regression tests | VERIFIED ON LINUX ONLY | Linux Live Runtime integration run 42291308024 passed. Native resource/sanitizer matrix 42291307713 and Python quality 42291301523 passed; the extension resolver integration executable is not yet run under macOS/Windows. |
| Multiple Frontends / Driver-Observer | VERIFIED ON PREVIOUS CANDIDATE | Previous CDIN run 42265415995; transport-loss recovery and work-pending reconnect remain open. |
| Plugin capability isolation and failure recovery | PARTIAL | Load/unload smoke exists; capability allow/deny, failed-init/runtime containment and recovery under live session remain. |
| Product RSS/latency/soak | NOT COMPLETE | Existing short smoke measurements are not product workload baselines. |
| Native installers / stable release | NOT IMPLEMENTED | Clean-machine install, upgrade, launch, uninstall and signing remain. |

## 4. Required next checks

1. Inspect CDIN native run 42304522348 on head 634075a92aeb5a6e58b817d2045d653dfbf8bbf2; require the GUI smoke log to prove snapshot commit, SDL text delivery, Ctrl+S dispatch, exact saved bytes and teardown.
2. If GUI smoke still fails, use the protocol send/receive trace to identify the first missing input.text, input.key, Runtime dispatch or file-save event; do not weaken the assertion or disable the test.
3. Keep GUI-SDL launch behind the experimental environment gate until the live session smoke passes. The current renderer is a debug ASCII baseline, not a release text renderer.
4. Backend Issue #14 resolver integration is closed based on Backend PR #18 head 987acd2f04bf6cc7eed360a4328bb11085628457 and its three-platform CI.
5. Complete Windows Console TUI, reconnect while work is pending, repeated start/stop and process recovery.
6. Define editing workloads and record allocator peak, input-to-visible/save latency, p50/p95/p99 and a documented soak/leak run.
7. Build signed native installers and validate clean-machine install/upgrade/launch/uninstall.
8. Resolve the separate repository Code Quality JavaScript/TypeScript language selection in Settings; this source tree has no JS/TS.
