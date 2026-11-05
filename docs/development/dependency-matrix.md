# Dependency matrix

The lock file is the source of truth for immutable source revisions. Version fields below are included only where the lock or pinned source metadata explicitly declares them.

| Component | Pinned revision | Declared version/contract | Role and current limitation |
| --- | --- | --- | --- |
| Runtime | `fda2db69d8e0ab90c854c3a74efa1dd80d9714cc` | Lua 5.4 module tree; version is not recorded in `deps.lock` | Runtime policy and Lua assets loaded by Backend. |
| Kernel | `f4875b6eb59bd76878e7ff486b6114abd9bb1329` | Package 1.2.1; ABI 1.1.0 | Backend's native document engine dependency. |
| Backend | `23e31e5f9dd68b3702c4eca968be8d26b5228b14` | Version 1.0.0; Protocol 1.0.0 | Backend lifecycle and Runtime/Kernel host. CMake discovers installed libraries by name; runtime version is checked by CDIN. |
| Frontend | `7145c931e4202ae32f8b38bc3cc8b07726b48ee1` | Project version 1.0.0; Protocol header 1.0.0 | Core package and peer adapters. CDIN does not launch a live adapter yet. |
| m-mdy-m/log.c | `c9b53e9901dc7103eb50be282ae055fe16e98f9a` | Version 0.1.0; ABI 1.0 | Shared diagnostics library. |
| Pipeline | `79169afc4f9f74ee46c52be2bf6974f8544c7db1` | Immutable tool revision | Local and CI task execution. |
| PSX | `e4f12e85725e1ebd44c7f3a4e18fcbaa893b30df` | Immutable tool revision | Project structure validation. |
| Gix | `9f0867923177cef3cd36d980cc2b356a35bee507` | Immutable tool revision | Git branch workflow. |

The CDIN executable target is version 0.2.0 in the root CMake project. This is the in-tree project version; it is not a claim that a release artifact has been published.

## Compatibility checks

- CMake requires logger 0.1.0 and Frontend Core 1.0.0.
- CMake requires PUC Lua 5.4.x.
- CMake requires Kernel package version 1.2.1 or newer.
- The build stack compiles the pinned Backend and Frontend revisions.
- CDIN checks the Backend runtime version against the header version.
- CDIN checks Backend/Frontend Protocol major and minor values at compile time.

The package-level Backend ABI contract and a released prebuilt dependency installation are still incomplete. Do not infer ABI compatibility from a matching repository SHA alone.
