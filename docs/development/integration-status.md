# Integration status and release gates

This document reports what the current CDIN branch actually connects. A component's own feature or a configured CI job is not automatically a verified CDIN product feature.

## 1. Implemented behavior

| Area | Status | Evidence |
| --- | --- | --- |
| Composition Root CLI | IMPLEMENTED | `--help`, `--version`, `--check`, Runtime root/entry and frontend options are parsed. |
| Component pinning | IMPLEMENTED | `deps.lock` records immutable source revisions. |
| Stack orchestration | IMPLEMENTED; Linux/macOS PASS, Windows PARTIAL | `scripts/build_stack.py` builds and tests the pinned stack. Windows reaches Backend CTest but one Backend-owned path test fails. |
| Runtime module installation | IMPLEMENTED | CMake installs the pinned Lua module tree under `share/cdin/lua`. |
| Backend lifecycle | IMPLEMENTED for smoke test | CDIN calls Backend create/start/pump/shutdown/destroy. |
| Backend/Frontend Protocol compatibility | PARTIAL | Major/minor header constants are compared at compile time; `--check` also sends Frontend Core HELLO through an in-process byte transport and validates Backend HELLO_ACK. |
| Backend version check | PARTIAL | Runtime version is compared with the version encoded by the included header. |
| Shared logging | IMPLEMENTED for CDIN and Backend callbacks | CDIN owns a logger instance and routes Backend log callbacks into it. |

## 2. Not complete

| Area | Status | Missing work |
| --- | --- | --- |
| Frontend Core handshake | IMPLEMENTED for headless smoke | `--check` creates a Frontend Core client/session, sends HELLO, validates HELLO_ACK and closes the Backend client. This is not a view attachment or interactive transport. |
| Interactive TUI | NOT IMPLEMENTED | The TUI adapter is not exported by Frontend Core 1.0.0; initial UI snapshot publication currently defers with `CDIN_BACKEND_LIMIT_EXCEEDED`; readiness/wakeup and FE-019 event loop integration remain. |
| GUI-SDL | NOT IMPLEMENTED in CDIN | GUI adapter is built disabled in the pinned stack and is not launched. |
| Real editing workflow | NOT IMPLEMENTED | Create/open/edit/save/reopen through real Runtime, Backend, Kernel and Frontend interfaces. |
| Keymaps and commands through input | NOT VERIFIED | Feed real Frontend input into Backend and verify Runtime dispatch. |
| Plugin lifecycle and isolation | NOT VERIFIED from CDIN | Exercise plugin load, capability denial, failure isolation and unload in a live session. |
| Multi-frontend attach/detach | NOT VERIFIED from CDIN | Exercise driver/observer roles, detach and reconnect. |
| Product memory and soak measurements | NOT IMPLEMENTED | Measure RSS, allocator peak, leaks and long-running sessions. |
| Installers and release archives | NOT IMPLEMENTED | Only a developer source archive exists. |
| Docker image | NOT IMPLEMENTED | No Docker build definition is present. |

## 3. CI evidence for the current HEAD

Run [41991189690](https://github.com/cdin-editor/cdin/actions/runs/41991189690), tested implementation baseline `c7b50b87034968a083c6fa2d52bee05babdea337` (the subsequent branch commits update audit documentation only):

- **Linux:** pinned stack, component tests, CDIN CLI/lifecycle smoke and boundary checks passed.
- **macOS:** pinned stack, component tests, CDIN CLI/lifecycle smoke and boundary checks passed.
- **Linux ASan + UBSan + leak detection:** passed.
- **Windows:** Backend built; 8/9 Backend CTest cases passed. `backend_e2e_platform_file_workflow` failed at `tests/e2e/scenarios/platform_file_workflow.c:56` while comparing normalized path output with the scenario helper's path string. This is a Backend-owned test failure and must be fixed in Backend.
- **CodeQL Python:** passed.
- **CodeQL JavaScript/TypeScript:** configuration failure because no JavaScript/TypeScript source was found for that language database.

The successful stack jobs include a Frontend Core HELLO/HELLO_ACK protocol smoke over an in-process transport, in addition to component tests, CLI checks and Backend/Runtime startup/shutdown. They do not prove view attachment, UI snapshot delivery, rendering, document editing, save/reopen, input dispatch or plugin behavior.

The CI log reports Runtime Host API `1.0.0` and Kernel ABI `1.1.0`, but Runtime self-reports `0.2.1-beta.10.next.17+gc7b50b8`; the Spec and Runtime status documents claim package candidate `1.0.0-rc.1`. This release-identity discrepancy remains unresolved.

Historical runs `41985097875` and `41987494172` describe earlier failures and are superseded for the current HEAD.

## 4. Release gates

Before describing CDIN as an interactive editor, all of the following must be implemented and tested:

1. Resolve Backend initial Runtime UI snapshot publication (`CDIN_BACKEND_LIMIT_EXCEEDED`) and test ATTACH, UI flush/ACK and resize end-to-end.
2. Publish an installable Frontend TUI adapter package/target or select another supported adapter.
3. Connect Backend worker-completion wakeup to the Frontend event loop and implement the FE-019 readiness multiplexer.
3. Product E2E for create/open/edit/save/close/reopen, with exact-byte comparisons for NUL, invalid UTF-8, BOM and line endings.
4. Runtime command/keymap execution through real input.
5. Plugin loading, capability isolation, failure handling and unload.
6. Frontend detach/reconnect, multi-frontend sessions and failure recovery.
7. Native Linux/macOS/Windows CI and sanitizer evidence.
8. Process RSS, allocator peak where available, leak checks, soak workloads and latency measurements.
9. Platform packages, installers and release workflow.

Unrun checks must be reported as NOT RUN, not PASS.
