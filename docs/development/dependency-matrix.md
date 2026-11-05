# Dependency matrix

| Dependency | Immutable revision | Contract |
|---|---|---|
| Runtime | fda2db69d8e0ab90c854c3a74efa1dd80d9714cc | Lua policy/module tree |
| Kernel | f4875b6eb59bd76878e7ff486b6114abd9bb1329 | Backend-only native document engine |
| Backend | 23e31e5f9dd68b3702c4eca968be8d26b5228b14 | lifecycle and Protocol server |
| Frontend | 7145c931e4202ae32f8b38bc3cc8b07726b48ee1 | Core protocol client and semantic projection |
| m-mdy-m/log.c | c9b53e9901dc7103eb50be282ae055fe16e98f9a | independent diagnostics |
| pipeline | 79169afc4f9f74ee46c52be2bf6974f8544c7db1 | local/CI task execution |
| psx | e4f12e85725e1ebd44c7f3a4e18fcbaa893b30df | repository structure validation |
| gix | 9f0867923177cef3cd36d980cc2b356a35bee507 | topic branch workflow |

Pins live in deps.lock. Production builds must never download a floating branch or silently substitute an installed component of an unknown revision.
