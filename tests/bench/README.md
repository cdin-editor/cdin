# Resource and soak benchmarks

The real headless document workflow is now exercised through Frontend → Backend → Runtime → Kernel: create/open, text and binary paste, undo/redo, atomic save, close/reopen and exact-byte readback. That is integration evidence, not a performance measurement.

**No CDIN product RSS, allocator-peak, latency or long-running soak benchmark is implemented yet.** Bounded queue capacities and a short `--check` run are not substitutes for measured process memory or sustained workloads.

## 1. Required workloads

Run repeatable workloads against the real document and Frontend session path:

- Open/close many small, medium and large documents.
- Large paste, replace, undo and redo histories.
- Repeated save/reopen, including BOM and mixed-EOL files.
- Multiple views and multiple Frontend sessions.
- Plugin load, use, capability denial and unload.
- Cancellation, transport interruption and Backend shutdown during background work.
- Long-lived idle and active sessions.
- Malformed input, disconnect/reconnect and repeated recovery.
- TUI redraw/resize/input workloads after the interactive PTY gate passes.

Each workload must specify document/session/view counts, payload sizes, operation mix, warmup, iteration count and soak duration. Run on the supported native platform/toolchain matrix where practical.

## 2. Required report fields

| Field | Required value |
| --- | --- |
| Source | Commit SHA and immutable component pins. |
| Platform | OS version, architecture and native toolchain. |
| Build | Compiler, flags, build type and sanitizer settings. |
| Workload | Document bytes, document/session/view counts, operation mix, warmup and iterations. |
| Memory | Peak process RSS and allocator peak when exposed by a component. |
| Latency | p50, p95 and p99 for named operations, with sample count. |
| Safety | ASan, UBSan, leak checker, soak duration and failure count. |
| Comparison | Previous baseline and percentage change under the same workload. |

Do not infer missing memory values. Record `NOT AVAILABLE` when a component does not expose a metric and `NOT RUN` when a workload has not executed. Preserve raw measurement artifacts so results can be reproduced.

## 3. Current status

**Integration workload: IMPLEMENTED / native CI verified for headless document operations.**

**Performance and soak measurement: NOT IMPLEMENTED / NOT RUN.**

This document is a benchmark specification, not evidence of a benchmark result. Performance budgets must be established from measurements rather than chosen from queue limits or expectations.
