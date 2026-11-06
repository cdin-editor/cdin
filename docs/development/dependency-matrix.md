# Dependency matrix

The lock file is the source of truth for immutable source revisions. Version fields below are included only where the lock or pinned source metadata explicitly declares them.

| Component | Pinned revision | Declared version/contract | Role and current limitation |
| --- | --- | --- | --- |
| Runtime | `d2acb6f174edf127c3bf59e8e5d4aedcbef0d490` | Package `1.0.0-rc.1`; Host API `1.0.0`; Protocol `1.0.0`; Kernel ABI `1.1.0` | Merged Runtime PR #6; includes structured extension resolver errors and lifecycle hooks. |
| Kernel | `f4875b6eb59bd76878e7ff486b6114abd9bb1329` | Package 1.2.1; ABI 1.1.0 | Backend's native document engine dependency. |
| Backend | `c0a88090460929796bd7cd731966f04115256910` | Package 1.2.0; Protocol 1.0.0 | Merged Backend PR #17: Windows GCC allocation-guard fix. Draft Backend PR #18 adds extension-resolver regression tests; Linux Live Runtime CI passes, but the resolver test still needs macOS/Windows execution before Issue #14 closes. |
| Frontend | `552eedd14e3971e2b39d706804d4af57f8b2dc38` | Project version 1.0.0; Protocol 1.0.0 | Frontend PR #17 candidate adds installable `cdin::frontend_ui_gui_sdl`; native matrix, SDL AddressSanitizer tests and clean-prefix consumer passed in run 42295241142. PR remains unmerged. |
| m-mdy-m/log.c | `c9b53e9901dc7103eb50be282ae055fe16e98f9a` | Version 0.1.0; ABI 1.0 | Shared diagnostics library. |
| SDL3 | `3.4.16` source archive | SHA-256 `7322236cd12090c3eb40b9728be4d49c76f66ad17d04369584d4ecad5cf77c68` | Built from the pinned archive by `scripts/build_stack.py`; used only by the Frontend GUI-SDL peer. |
| Pipeline | `79169afc4f9f74ee46c52be2bf6974f8544c7db1` | Immutable tool revision | Local and CI task execution. |
| PSX | `e4f12e85725e1ebd44c7f3a4e18fcbaa893b30df` | Immutable tool revision | Project structure validation. |
| Gix | `9f0867923177cef3cd36d980cc2b356a35bee507` | Immutable tool revision | Git branch workflow. |

The CDIN executable target is version 0.2.0 in the root CMake project. This is the in-tree project version; it is not a claim that a release artifact has been published.

## Compatibility checks

- Root CMake requires logger 0.1.0, Frontend Core 1.0.0 and Backend package 1.2.0 because CDIN now links the trusted Runtime extension lifecycle API.
- The pinned component build checks PUC Lua 5.4.x and the Kernel package dependency used by Backend.
- CDIN checks the Backend runtime version against the Backend header version.
- CDIN checks Backend/Frontend Protocol major and minor values at compile time.
- The stack lifecycle smoke checks the Runtime-reported package version against `deps.lock`.

These checks are stronger than comparing repository SHAs alone, but they do not assert complete semantic compatibility across every component API.

## Current verification note

Frontend CI run [42295241142](https://github.com/cdin-editor/frontend/actions/runs/42295241142) passed the current GUI-SDL component candidate on Linux/macOS/Windows and passed the SDL AddressSanitizer plus installed-consumer job. CDIN CI run [42296140965](https://github.com/cdin-editor/cdin/actions/runs/42296140965) is **not green**: the new GUI composition file cannot yet find its private header because the CDIN target include path omits `src/`. The dependency pins above describe the current feature branch, not `main`; see [Integration status](integration-status.md) for exact verification scope.

Runtime PR #2 was merged at `dddebe07e7a773c7d8f3cb83321c2cbb5d259c52`; [Runtime CI run 42077125147](https://github.com/cdin-editor/runtime/actions/runs/42077125147) passed Linux Lua 5.5, macOS Lua 5.4, Windows Lua 5.4, Pipeline quality and docs/workflow validation. The CDIN candidate still requires its own pin/build/E2E run after the Runtime pin moves to the merge commit.
