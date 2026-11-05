# Integration status and release gates

This document reports what the current CDIN branch actually connects. A component feature or configured CI job is not automatically a verified CDIN product feature.

## 1. Implemented behavior

| Area | Status | Evidence |
| --- | --- | --- |
| Composition Root CLI | IMPLEMENTED | `--help`, `--version`, `--check`, Runtime root/entry and frontend options are parsed. |
| Component pinning | IMPLEMENTED | `deps.lock` records immutable source revisions. |
| Stack orchestration | IMPLEMENTED | `scripts/build_stack.py` builds and tests the pinned component stack. |
| Runtime module installation | IMPLEMENTED | CMake installs the pinned Lua module tree under `share/cdin/lua`. |
| Backend lifecycle | IMPLEMENTED for smoke test | CDIN calls Backend create/start/pump/shutdown/destroy. |
| Backend package contract | IMPLEMENTED | Backend 1.0.0 exports versioned `cdinBackend` CMake package targets; CDIN consumes the installed package with `find_package(cdinBackend 1.0.0 CONFIG REQUIRED)`. |
| Backend/Frontend protocol compatibility | PARTIAL | Major/minor header constants are compared at compile time; `--check` sends Frontend Core HELLO through an in-process byte transport and validates Backend HELLO_ACK. |
| Shared logging | IMPLEMENTED for CDIN and Backend callbacks | CDIN owns a logger instance and routes Backend log callbacks into it. |

## 2. Not complete

| Area | Status | Missing work |
| --- | --- | --- |
| Frontend Core handshake | IMPLEMENTED for headless smoke | `--check` creates a Frontend Core client/session, sends HELLO, validates HELLO_ACK and closes the Backend client. This is not view attachment or an interactive transport. |
| Interactive TUI | NOT IMPLEMENTED | The TUI adapter is not exported by Frontend Core 1.0.0; initial UI snapshot publication returned `CDIN_BACKEND_LIMIT_EXCEEDED`; readiness/wakeup and FE-019 event-loop integration remain. |
| GUI-SDL | NOT IMPLEMENTED in CDIN | GUI adapter is not launched by the current Composition Root. |
| Real editing workflow | NOT IMPLEMENTED | Create/open/edit/save/reopen through real Runtime, Backend, Kernel and Frontend interfaces. |
| Keymaps and commands through input | NOT VERIFIED | Feed real Frontend input into Backend and verify Runtime dispatch. |
| Plugin lifecycle and isolation | NOT VERIFIED from CDIN | Exercise plugin load, capability denial, failure isolation and unload in a live session. |
| Multi-frontend attach/detach | NOT VERIFIED from CDIN | Exercise driver/observer roles, detach and reconnect. |
| Product memory and soak measurements | NOT IMPLEMENTED | Measure RSS, allocator peak, leaks and long-running sessions. |
| Platform installers | NOT IMPLEMENTED | The current package task creates a source snapshot only; it is not an application installer. |
| Docker image | NOT IMPLEMENTED | No verified runtime image is published. |

## 3. CI evidence

The current code baseline was verified by [CI run 42009406506](https://github.com/cdin-editor/cdin/actions/runs/42009406506) on commit `4ab4064af53f347ee714e57c3c2e936310f12673`. All four jobs completed successfully:

- Ubuntu pinned stack + E2E: PASS.
- macOS pinned stack + E2E: PASS.
- Windows pinned stack + E2E: PASS.
- Linux ASan + UBSan + leak detection: PASS.

The latest PR-head commit `9bc6ed3645dbdd47144d3b78b35df569c5379e59` also has CI run [42009406506](https://github.com/cdin-editor/cdin/actions/runs/42009406506) for its preceding code-identical commit; subsequent change at that point was documentation-only. The CI run on the latest PR head must be inspected independently before treating the newest commit as verified.

The passing stack jobs include a Frontend Core HELLO/HELLO_ACK protocol smoke over an in-process transport, component tests, CLI checks and Backend/Runtime startup/shutdown. They do **not** prove view attachment, UI snapshot delivery, rendering, document editing, save/reopen, input dispatch or plugin behavior.

The previous dynamic CodeQL workflow attempted JavaScript/TypeScript analysis even though the repository contains no JS/TS source. The new dedicated CodeQL workflow analyzes only C/C++ and Python in separate jobs; its first run is still required before calling the new configuration verified.

## 4. Compatibility and release blockers

- Runtime package identity is unresolved: the lock/status documents identify candidate `1.0.0-rc.1`, while the Runtime self-reported version observed in earlier CI logs was `0.2.1-beta.10.next.17+gc7b50b8`. Reconcile Runtime's Git-derived version with its release metadata before publishing.
- Backend 1.0.0 package discovery is versioned at CMake package level; do not regress to unversioned header/library discovery.
- Initial UI snapshot publication previously returned `CDIN_BACKEND_LIMIT_EXCEEDED`; the headless handshake was intentionally narrowed rather than increasing message limits or claiming a snapshot test.
- Frontend TUI target remains experimental/unexported by Frontend Core 1.0.0. CDIN must consume a supported installable adapter, not copy its implementation.

## 5. Release gates

Before describing CDIN as an interactive editor:

1. Resolve Backend initial Runtime UI snapshot publication and verify ATTACH, UI flush/ACK and resize end-to-end.
2. Publish an installable Frontend TUI adapter package/target or select another supported adapter.
3. Connect Backend worker-completion wakeup to the Frontend event loop and implement the FE-019 readiness multiplexer.
4. Add product E2E for create/open/edit/save/close/reopen, with exact-byte comparisons for NUL, invalid UTF-8, BOM and line endings.
5. Verify Runtime command/keymap execution through real input.
6. Verify plugin loading, capability isolation, failure handling and unload.
7. Verify Frontend detach/reconnect, multi-frontend sessions and failure recovery.
8. Maintain native Linux/macOS/Windows CI and sanitizer evidence on the latest commit.
9. Add measured process RSS, allocator peak where available, leak checks, soak workloads and latency measurements.
10. Produce platform packages/installers and a release workflow only after the interactive path is complete.

Unrun checks must be reported as NOT RUN, not PASS.
