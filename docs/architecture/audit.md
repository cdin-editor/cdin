# Architecture audit

**Current candidate:** CDIN PR [#110](https://github.com/cdin-editor/cdin/pull/110), branch `feature/complete-composition-root-rewrite`, head `f347f5085e5c32a14fda09e2a4971cc90d981800`. The current CI run [42296140965](https://github.com/cdin-editor/cdin/actions/runs/42296140965) is **FAILED** on all native jobs and Linux sanitizers because `src/integration/gui_sdl.c` includes the private Composition Root header `integration/frontend_smoke.h` without the `src/` directory on the `cdin` target include path. The component build stages completed before this compilation failure. This document distinguishes the current implementation from prior green evidence.

## 1. Ownership model

- **Kernel:** canonical document bytes, edits, versions, snapshots and undo/redo.
- **Runtime:** Lua 5.4 editor policy, commands, keymaps, configuration and extension execution.
- **Backend:** Runtime/Kernel hosting, sessions, Frontend Protocol server, file I/O and OS services.
- **Frontend:** protocol client, physical input, semantic UI model, presentation layout and terminal/window rendering.
- **CDIN:** immutable dependency pins, stack orchestration, launcher, transport construction, application process lifecycle, integration tests and packaging.

CDIN must not copy document, keymap, plugin, session, protocol, input or renderer implementations from the component repositories. The GUI integration source constructs the transport and lifecycle only; SDL event translation and drawing remain in Frontend.

## 2. Composition Root inventory

| Area | Source | Current assessment |
| --- | --- | --- |
| CLI and launch dispatch | `src/main.c`, `src/cli/options.c` | Headless checks, experimental POSIX TUI, and an experimental GUI-SDL launch path are present. GUI-SDL is opt-in via `CDIN_ENABLE_EXPERIMENTAL_GUI_SDL=1`; its CI `--check` path runs with SDL dummy video. |
| Headless integration | `src/integration/frontend_smoke.c` | Public Frontend Session handshake/attach, ordered snapshot/flush/ACK/resize and document lifecycle; previously passed the Linux/macOS/Windows matrix and Linux sanitizers on CDIN run 42265415995. |
| POSIX TUI | `src/integration/frontend_smoke.c`, `scripts/tui_pty_smoke.py` | Experimental PTY-tested input/edit/save/quit and terminal restore on the previous fully green candidate. |
| Windows TUI | `scripts/tui_conpty_smoke.py` | Experimental ConPTY test exists and passed on the previous candidate; supported launch remains gated pending the broader Windows console contract. |
| GUI-SDL composition | `src/integration/gui_sdl.c` | Builds a real Backend Runtime host, opens a Frontend Protocol Driver Session, creates the SDL adapter, requests a document and drives the SDL event/render loop. An executable smoke sends text and Ctrl+S and checks exact saved bytes. Current CDIN CI has not reached this source's compile due to the include-path defect above. |
| GUI-SDL component package | `deps.lock`, Frontend PR #17 | Frontend pin `552eedd14e3971e2b39d706804d4af57f8b2dc38`; SDL3 3.4.16 is checksum-pinned. Frontend CI run 42295241142 passed native and SDL AddressSanitizer tests plus clean-prefix consumer installation. |
| Runtime extension lifecycle | `src/integration/frontend_smoke.c`, Backend PR #18 | CDIN has a temporary extension Lua init/unload smoke; Backend adds repeated-read, case-fold and read-failure tests. Backend PR #18 Linux Runtime integration, three-platform stress/sanitizers and Python quality passed, but resolver test execution on macOS/Windows remains open. |
| Source distribution | `scripts/package.py` | Reproducible source ZIP with archive validation and SHA-256. This is not an application installer. |
| Resource benchmarks | `tests/bench/` | Short headless smoke measurements exist; no product allocator peak, editing latency budget or long-running soak proof. |

## 3. Verified versus incomplete

| Capability | Status | Evidence / limitation |
| --- | --- | --- |
| Immutable pins / stack orchestration | IMPLEMENTED | `deps.lock`, `scripts/deps.py`, Pipeline; includes SDL3 archive SHA-256. |
| Backend/Runtime lifecycle and headless editing | VERIFIED ON PREVIOUS CANDIDATE | CDIN CI run 42265415995 passed Linux, macOS, Windows and Linux ASan/UBSan/leak detection before the newest GUI source was added. |
| Frontend GUI-SDL package | VERIFIED AS COMPONENT | Frontend CI run 42295241142 passed native/Pipeline jobs, SDL3 AddressSanitizer tests, installed package and external CMake consumer. |
| CDIN GUI-SDL live session | IMPLEMENTED / NOT VERIFIED | Build is blocked at missing internal include path; do not claim runtime input/save smoke passed. |
| TUI POSIX | VERIFIED ON PREVIOUS CANDIDATE; EXPERIMENTAL | Previous CDIN candidate passed PTY, input/save/quit and restoration on Linux/macOS. |
| TUI Windows | EXPERIMENTAL / NOT RELEASE-READY | ConPTY test exists; native Console contract and broader input semantics remain gated. |
| Backend resolver regression tests | VERIFIED ON LINUX ONLY | Linux Live Runtime integration run 42291308024 passed. Native resource/sanitizer matrix 42291307713 and Python quality 42291301523 passed; the extension resolver integration executable is not yet run under macOS/Windows. |
| Multiple Frontends / Driver-Observer | VERIFIED ON PREVIOUS CANDIDATE | Previous CDIN run 42265415995; transport-loss recovery and work-pending reconnect remain open. |
| Plugin capability isolation and failure recovery | PARTIAL | Load/unload smoke exists; capability allow/deny, failed-init/runtime containment and recovery under live session remain. |
| Product RSS/latency/soak | NOT COMPLETE | Existing short smoke measurements are not product workload baselines. |
| Native installers / stable release | NOT IMPLEMENTED | Clean-machine install, upgrade, launch, uninstall and signing remain. |

## 4. Required next checks

1. Add `${CMAKE_CURRENT_SOURCE_DIR}/src` as a private include directory for the `cdin` target (or use an explicit private header path), then rebuild all three native jobs and Linux sanitizers.
2. Inspect `cdin_gui_sdl_live_session_smoke` specifically: attach snapshot/ACK, Runtime document creation, SDL text event, Ctrl+S dispatch, saved-byte equality and teardown.
3. Keep GUI-SDL launch behind the experimental environment gate until the live session smoke passes. The current renderer is a debug ASCII baseline, not a release text renderer.
4. Run Backend resolver integration on Linux, macOS and Windows before closing Backend Issue #14.
5. Complete Windows Console TUI, reconnect while work is pending, repeated start/stop and process recovery.
6. Define editing workloads and record allocator peak, input-to-visible/save latency, p50/p95/p99 and a documented soak/leak run.
7. Build signed native installers and validate clean-machine install/upgrade/launch/uninstall.
8. Resolve the separate repository Code Quality JavaScript/TypeScript language selection in Settings; this source tree has no JS/TS.
