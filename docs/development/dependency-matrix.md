# Dependency matrix

The lock file is the source of truth for immutable source revisions. Version fields below are included only where the lock or pinned source metadata explicitly declares them.

| Component | Pinned revision | Declared version/contract | Role and current limitation |
| --- | --- | --- | --- |
| Runtime | `dddebe07e7a773c7d8f3cb83321c2cbb5d259c52` | Package `1.0.0-rc.1`; Host API `1.0.0`; Protocol `1.0.0`; Kernel ABI `1.1.0` | Merged Runtime PR #2. Adds document lifecycle commands, Runtime-owned keymaps, Backend Host file access and exact-byte persistence tests. Main-branch CI run 42077125147 passed Linux, macOS and Windows plus Pipeline quality/docs checks. |
| Kernel | `f4875b6eb59bd76878e7ff486b6114abd9bb1329` | Package 1.2.1; ABI 1.1.0 | Backend's native document engine dependency. |
| Backend | `f816b9cdbd6b97f7c70a4772a0d8f1e63c47eb9e` | Version 1.0.2; Protocol 1.0.0 | Merged Backend 1.0.2 plus post-merge filesystem regression-test fix on `main`. Includes bounded binary-safe optional `host.fs.read_file`, Backend lifecycle/protocol and worker wakeup API. CDIN requires `find_package(cdinBackend 1.0.2 CONFIG REQUIRED)`. |
| Frontend | `94643adada76cb3d056baf0b6ad475451d56ab0f` | Project version 1.0.0; Protocol 1.0.0 | Merged Frontend PR #2. Installs/exports `cdin::frontend_ui_tui` and typed `request.command` session API. CDIN consumes this public package but still does not launch an interactive adapter until FE-019 is complete. |
| m-mdy-m/log.c | `c9b53e9901dc7103eb50be282ae055fe16e98f9a` | Version 0.1.0; ABI 1.0 | Shared diagnostics library. |
| Pipeline | `79169afc4f9f74ee46c52be2bf6974f8544c7db1` | Immutable tool revision | Local and CI task execution. |
| PSX | `e4f12e85725e1ebd44c7f3a4e18fcbaa893b30df` | Immutable tool revision | Project structure validation. |
| Gix | `9f0867923177cef3cd36d980cc2b356a35bee507` | Immutable tool revision | Git branch workflow. |

The CDIN executable target is version 0.2.0 in the root CMake project. This is the in-tree project version; it is not a claim that a release artifact has been published.

## Compatibility checks

- Root CMake requires logger 0.1.0, Frontend Core 1.0.0 and versioned Backend package 1.0.2.
- The pinned component build checks PUC Lua 5.4.x and the Kernel package dependency used by Backend.
- CDIN checks the Backend runtime version against the Backend header version.
- CDIN checks Backend/Frontend Protocol major and minor values at compile time.
- The stack lifecycle smoke checks the Runtime-reported package version against `deps.lock`.

These checks are stronger than comparing repository SHAs alone, but they do not assert complete semantic compatibility across every component API.

## Current verification note

CI run [42074655322](https://github.com/cdin-editor/cdin/actions/runs/42074655322) passed the current pinned stack and expanded headless document E2E on Linux, macOS and Windows, plus Linux ASan/UBSan/leak detection, on candidate `006263f89f1c1c5352807b00544c8944e131a2dd`. Backend, Frontend and CDIN CTest suites passed; each platform log records exact-byte document save/close/open/readback.

Runtime PR #2 was merged at `dddebe07e7a773c7d8f3cb83321c2cbb5d259c52`; [Runtime CI run 42077125147](https://github.com/cdin-editor/runtime/actions/runs/42077125147) passed Linux Lua 5.5, macOS Lua 5.4, Windows Lua 5.4, Pipeline quality and docs/workflow validation. The CDIN candidate still requires its own pin/build/E2E run after the Runtime pin moves to the merge commit.
