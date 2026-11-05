# Spec traceability

This page maps Composition Root requirements to current source and records what has actually been exercised. A source link proves implementation location, not runtime behavior. Proposed Spec requirements retain their Spec status even where this repository has partial implementation.

## 1. Requirement matrix

| Requirement | Spec status | CDIN evidence | Current result |
| --- | --- | --- | --- |
| [ARCH-001](https://github.com/cdin-editor/spec/blob/main/docs/architecture/overview.md#L113-L113) — CDIN is the Composition Root and must not reimplement component logic | ACCEPTED | `src/main.c`, `src/cli/options.c`, `CMakeLists.txt` | **PARTIAL** — headless workflow and experimental POSIX TUI compose public APIs; Windows TUI, GUI and release behavior remain incomplete. |
| [ARCH-040](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L65-L65) — Kernel dependency boundary | ACCEPTED | Backend package and pinned Kernel dependency closure | **PARTIAL at Composition Root** — CDIN does not call Kernel document APIs; Backend owns integration. Compiler include audit also rejects private component source/build headers. |
| [ARCH-041](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L66-L66) — Runtime uses Backend Host API | PROPOSED | `src/main.c`, `deps.lock`, Backend lifecycle smoke | **IMPLEMENTED for headless integration** — Runtime loads through Backend; live plugin lifecycle remains unverified from CDIN. |
| [ARCH-042](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L67-L67) — Backend has no display-toolkit dependency | ACCEPTED | Pinned Backend build and its own source/CMake | **Backend-owned** — no display implementation is introduced in CDIN. |
| [ARCH-043](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L68-L68) — Frontend depends on Protocol and its toolkit | ACCEPTED | Frontend package pin and public Core/TUI API | **Frontend-owned** — CDIN consumes the installed package; no renderer copy is maintained here. |
| [ARCH-044](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L69-L69) — `cdin-x` depends only on the extension contract | PROPOSED | Not applicable to this Composition Root executable | **NOT IMPLEMENTED HERE** — `cdin-x` is a separate extension host. |
| [ARCH-045](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L70-L70) — Composition Root may assemble components and must not be depended on | PROPOSED | Root executable links installed component interfaces | **PARTIAL** — no reverse dependency is introduced here; full product delivery remains open. |
| [ARCH-046](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L71-L71) — include-direction rules are mechanically enforced | PROPOSED | `scripts/check_boundaries.py`, `scripts/check_include_graph.py`, `tests/architecture/test_include_graph.py` | **PARTIAL** — compiler-resolved includes are checked for all four CDIN translation units and six policy tests pass on Windows. Linux/macOS graph checks still need to complete; semantic dependency rules are not exhaustively proven. |
| [ROOT-001](https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md#L22-L22) — do not reimplement component logic | ACCEPTED | Launcher, diagnostics, stack orchestration and integration adapter in `src/` | **IMPLEMENTED for current code boundary** — document, keymap, plugin, protocol and rendering behavior remain component-owned. |
| [ROOT-006](https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md#L27-L27) — select a frontend and compose its endpoint | PROPOSED | `src/cli/options.c`, `src/main.c`, `src/integration/frontend_smoke.c` | **PARTIAL** — `--check` exercises the headless Frontend session; POSIX `--frontend tui` is opt-in via `CDIN_ENABLE_EXPERIMENTAL_TUI=1` and is not yet release-ready. Windows TUI remains fail-closed. |
| [ROOT-007](https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md#L28-L28) — compatibility checks for assembled components | PROPOSED | `CMakeLists.txt`, `src/main.c`, `scripts/build_stack.py` | **PARTIAL / VERIFIED CONTRACTS** — versioned package discovery, Backend runtime/header version, Protocol major/minor and Runtime reported version are checked. This is not a full semantic ABI matrix. |
| [ROOT-010](https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md#L31-L31) — consume Kernel as a pinned version | PROPOSED | `deps.lock`, `scripts/deps.py`, Backend dependency closure | **IMPLEMENTED for immutable source pinning** — released binary dependency delivery is not available. |
| [PROTO-001](https://github.com/cdin-editor/spec/blob/main/docs/architecture/frontend-protocol.md#L36-L36) — Backend owns editor state; Frontends can detach/reattach | ACCEPTED | Backend session implementation and component tests | **Backend-owned; CDIN product E2E PARTIAL** — multiple Frontends, detach/reattach and recovery are not yet verified through the application. |
| [PROTO-004](https://github.com/cdin-editor/spec/blob/main/docs/architecture/frontend-protocol.md#L40-L40) — Runtime owns keymap policy | ACCEPTED | Runtime keymaps dispatched through Backend; no CDIN keymap engine | **VERIFIED HEADLESS** — undo/redo/save keymaps are exercised through the public Frontend session; physical terminal key parsing is part of the live TUI gate. |
| [PROTO-010](https://github.com/cdin-editor/spec/blob/main/docs/architecture/frontend-protocol.md#L69-L69) — handshake starts with HELLO/HELLO_ACK | ACCEPTED | `src/integration/frontend_smoke.c` | **PASS IN HEADLESS PATH** — HELLO/HELLO_ACK, ATTACH, ordered snapshot, `ui.flush`/ACK, queue release and resize run through Frontend Core. |
| [FE-019](https://github.com/cdin-editor/spec/blob/main/docs/components/frontend.md#L82-L82) — TUI loop multiplexes input, Backend readiness and lifecycle events | ACCEPTED | `src/integration/frontend_smoke.c`, Frontend TUI package, `scripts/tui_pty_smoke.py` | **PARTIAL / NOT ACCEPTED** — POSIX terminal/wakeup/event-loop adapter exists behind experimental opt-in, but PTY test fails on pending `view.lines` response lifecycle. Frontend PR #11 holds the fix; Windows native readiness is absent. |

## 2. Source evidence

- Build dependencies, installed package discovery and Protocol guards: [`CMakeLists.txt`](https://github.com/cdin-editor/cdin/blob/feature/complete-composition-root-rewrite/CMakeLists.txt).
- CLI parsing and current launch choices: [`src/cli/options.c`](https://github.com/cdin-editor/cdin/blob/feature/complete-composition-root-rewrite/src/cli/options.c).
- Backend lifecycle, headless smoke and POSIX TUI composition: [`src/main.c`](https://github.com/cdin-editor/cdin/blob/feature/complete-composition-root-rewrite/src/main.c), [`src/integration/frontend_smoke.c`](https://github.com/cdin-editor/cdin/blob/feature/complete-composition-root-rewrite/src/integration/frontend_smoke.c).
- Component and tooling revisions: [`deps.lock`](https://github.com/cdin-editor/cdin/blob/feature/complete-composition-root-rewrite/deps.lock).
- Compiler-resolved include guard: [`scripts/check_include_graph.py`](https://github.com/cdin-editor/cdin/blob/feature/complete-composition-root-rewrite/scripts/check_include_graph.py), six unit tests in [`tests/architecture/test_include_graph.py`](https://github.com/cdin-editor/cdin/blob/feature/complete-composition-root-rewrite/tests/architecture/test_include_graph.py).
- Interactive PTY acceptance harness: [`scripts/tui_pty_smoke.py`](https://github.com/cdin-editor/cdin/blob/feature/complete-composition-root-rewrite/scripts/tui_pty_smoke.py).

## 3. Verification evidence and limits

[CDIN CI run 42117574266](https://github.com/cdin-editor/cdin/actions/runs/42117574266), on candidate `dd1f5896c27756948750a1adc1770b16b4207b66`, provides the latest fully completed native evidence inspected:

- Windows: all 9 CDIN CTest tests, 6 architecture tests and compiler-resolved include graph for 4 CDIN translation units passed. Logs include document edit/save/reopen, BOM/LF/mixed-EOL preservation and filesystem failure recovery.
- Linux/macOS: the headless CDIN test and Frontend component suite passed, but the live PTY test failed; therefore their later include-graph task was not reached.
- Linux sanitizer job failed on the same PTY acceptance test; no independent sanitizer defect was reported.
- Frontend PR [#11](https://github.com/cdin-editor/frontend/pull/11) contains the request-state lifecycle fix and regression tests. At the latest inspection, Ubuntu, Windows and Pipeline/quality were green; macOS was still queued.

A result is valid only for the SHA and workflow run that produced it. Later CLI/docs changes and an eventual Frontend pin update need fresh matching CDIN CI.

## 4. Static-boundary scope

`scripts/check_boundaries.py` blocks selected copied component implementation calls and invokes six Python policy tests plus `scripts/check_include_graph.py`. The include audit reads CMake's `compile_commands.json`, asks the compiler for its resolved `-H` trace, allows installed public headers and rejects private component source/build headers. This is stronger than matching `#include` text, but it does not prove every semantic dependency direction or runtime ownership rule.

## 5. Verification rule

A source link proves where code is written; it does not prove runtime behavior. Mark runtime behavior PASS only after the relevant executable test has run on the current SHA and its result has been inspected. A workflow definition, a queued job or an old green run is not current evidence.

See [Integration status](../development/integration-status.md) for release gates and repository settings that still require manual review.
