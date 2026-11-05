# Integration status and release gates

This document reports what the current CDIN branch actually connects. A component's own feature or a configured CI job is not automatically a verified CDIN product feature.

## 1. Implemented behavior

| Area | Status | Evidence |
| --- | --- | --- |
| Composition Root CLI | IMPLEMENTED | `--help`, `--version`, `--check`, Runtime root/entry and frontend options are parsed. |
| Component pinning | IMPLEMENTED | `deps.lock` records immutable source revisions. |
| Stack orchestration | IMPLEMENTED; current CI fix NOT VERIFIED | `scripts/build_stack.py` builds and tests each pinned component before CDIN. |
| Runtime module installation | IMPLEMENTED | CMake installs the pinned Lua module tree under `share/cdin/lua`. |
| Backend lifecycle | IMPLEMENTED for smoke test | CDIN calls Backend create/start/pump/shutdown/destroy. |
| Backend/Frontend Protocol compatibility | PARTIAL | Major/minor header constants are compared at compile time. No transport connection is made. |
| Backend version check | PARTIAL | Runtime version is compared with the version encoded by the included header. |
| Shared logging | IMPLEMENTED for CDIN and Backend callbacks | CDIN owns a logger instance and routes Backend log callbacks into it. |

## 2. Not complete

| Area | Status | Missing work |
| --- | --- | --- |
| Live Frontend connection | NOT IMPLEMENTED | Create and attach a Frontend client over the actual Protocol/Transport. |
| Interactive TUI | NOT IMPLEMENTED | Complete readiness/wakeup integration and FE-019 event loop, with terminal restoration. |
| GUI-SDL | NOT IMPLEMENTED in CDIN | GUI adapter is built disabled in the pinned stack and is not launched. |
| Real editing workflow | NOT IMPLEMENTED | Create/open/edit/save/reopen through real Runtime, Backend, Kernel and Frontend interfaces. |
| Keymaps and commands through input | NOT VERIFIED | Feed real Frontend input into Backend and verify Runtime dispatch. |
| Plugin lifecycle and isolation | NOT VERIFIED from CDIN | Exercise plugin load, capability denial, failure isolation and unload in a live session. |
| Multi-frontend attach/detach | NOT VERIFIED from CDIN | Exercise driver/observer roles, detach and reconnect. |
| Product memory and soak measurements | NOT IMPLEMENTED | Measure RSS, allocator peak, leaks and long-running sessions. |
| Installers and release archives | NOT IMPLEMENTED | Only a developer source archive exists. |
| Docker image | NOT IMPLEMENTED | No Docker build definition is present. |

## 3. CI evidence

Workflow run [41985097875](https://github.com/cdin-editor/cdin/actions/runs/41985097875) failed before compilation:

- Linux and macOS found empty source worktrees because the previous dependency script used `git clone --no-checkout` without always materializing the pinned revision.
- Windows could not install Pipeline because MSYS2 Python did not include pip.
- Gix reported a detached checkout and missing local branch identity/base-branch setup.

The current branch changes the dependency checkout behavior, installs the MSYS2 pip package, prepares the Git identity/main branch and removes the unused `develop` base from the Gix configuration. **These fixes are not verified until a new CI run completes.**

The inspected run did not compile CDIN. Therefore it provides no build, E2E, sanitizer or platform verification result.

## 4. Release gates

Before describing CDIN as an interactive editor, all of the following must be implemented and tested:

1. Backend readiness/wakeup integration with the Frontend event loop.
2. A real TUI connection through Frontend Core, Protocol and Transport.
3. Product E2E for create/open/edit/save/close/reopen, with exact-byte comparisons for NUL, invalid UTF-8, BOM and line endings.
4. Runtime command/keymap execution through real input.
5. Plugin loading, capability isolation, failure handling and unload.
6. Frontend detach/reconnect, multi-frontend sessions and failure recovery.
7. Native Linux/macOS/Windows CI and sanitizer evidence.
8. Process RSS, allocator peak where available, leak checks, soak workloads and latency measurements.
9. Platform packages, installers and release workflow.

Unrun checks must be reported as NOT RUN, not PASS.
