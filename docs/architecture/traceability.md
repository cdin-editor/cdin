# Spec traceability

| Spec area | Composition implementation |
|---|---|
| ARCH-001 / ROOT-001 | Composition Root boundary and ownership model |
| ROOT-002 / ROOT-010 | immutable pins in deps.lock and deterministic checkout/build |
| ROOT-006 | CLI argument parsing only |
| ROOT-007 | Backend/Frontend protocol version compile-time compatibility |
| ARCH-013 | CDIN-owned m-mdy-m/log.c diagnostics with BACKEND tag on Backend callbacks |
| ROOT-008 | ordered startup and reverse-order cleanup |
| PROTO-001 / PROTO-010 | Protocol is owned by Backend and Frontend; no duplicate codec here |
| FE-019 | interactive launch remains gated until readiness/wakeup is implemented |

Keymaps, commands, plugins, extension lifecycle and document operations remain Runtime/Kernel responsibilities. They are not exposed as new Composition APIs.
