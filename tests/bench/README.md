# Resource and soak benchmarks

No CDIN product memory or latency benchmark is implemented yet. The current `--check` command creates and shuts down Backend; it does not exercise a live editing workload. Bounded queue configuration is not a measurement of process RSS, allocator peak or leak behavior.

## 1. Required workloads

Run repeatable workloads against the real Kernel-backed editor path:

- open and close many small, medium and large documents;
- large paste, replace, undo and redo histories;
- repeated save and reopen;
- many views and multiple frontend sessions;
- plugin load, use and unload;
- cancellation and Backend shutdown during background work;
- long-lived idle and active sessions;
- malformed input and repeated transport reconnect.

The benchmark must not be published until the real create/open/edit/save/reopen product E2E path is implemented.

## 2. Required report fields

| Field | Required value |
| --- | --- |
| Source | Commit SHA and immutable component pins. |
| Platform | OS version, architecture and native toolchain. |
| Build | Compiler, flags, build type and sanitizer settings. |
| Workload | Document bytes, document/session/view counts, operation mix and iteration count. |
| Memory | Peak process RSS and allocator peak when a component exposes it. |
| Latency | Wall-clock p50, p95 and p99 for named operations. |
| Safety | ASan, UBSan, leak checker and soak duration/results. |
| Comparison | Previous baseline and percentage change for the same workload. |

Do not infer missing memory values. Write NOT AVAILABLE when a component does not expose a measurement and NOT RUN when the workload has not been executed.

## 3. Current status

**NOT IMPLEMENTED / NOT RUN.** This document is a measurement specification, not evidence of a benchmark result.
