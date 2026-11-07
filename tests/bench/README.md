# Resource and soak benchmarks

The real headless document workflow is exercised through Frontend → Backend → Runtime → Kernel: create/open, text and binary paste, undo/redo, atomic save, close/reopen and exact-byte readback. Fixtures include NUL, invalid UTF-8, BOM and mixed line endings; filesystem failure recovery is also tested.

## 1. Automated macro benchmark

`scripts/benchmark.py` now runs the installed `cdin --check` executable with two warm-up runs and ten measured iterations by default. The native CI matrix executes it after the pinned stack and integration checks and uploads one JSON report per OS.

The report contains:

- wall-clock duration for the complete `cdin --check` process, with p50/p95/p99, min, mean, max and sample count;
- periodically sampled peak resident set size for each process, plus the sampling method and total sample count;
- source commit, SHA-256 of `deps.lock`, executable SHA-256, OS, architecture, Python version and build metadata;
- each raw measured iteration and warm-up result.

Run it locally after `make stack`:

```sh
python3 scripts/benchmark.py --warmup 2 --iterations 10
```

The default output is `dist/cdin-headless-benchmark.json`. Use `--executable` to select another built CDIN binary, `--runtime-root` to select its Runtime tree, and `--output` to write the report elsewhere.

**Interpretation limits:** this is an end-to-end *macro* measurement of `--check`, not latency for individual editor operations. RSS is sampled every 10 ms by default; a short peak between samples may be missed. The ten measured runs are an initial comparison signal, not enough evidence to establish stable budgets or regressions on their own. No allocator peak or per-component attribution is reported. Do not compare runs with different source pins, OS/toolchain or workload settings as if they were equivalent.

## 2. Additional workloads still required

The current macro check does not yet cover all product workloads. Add repeatable workload drivers for:

- Open/close many small, medium and large documents.
- Large paste, replace, undo and redo histories with configurable payload sizes.
- Multiple views and multiple Frontend sessions, including Driver/Observer promotion.
- Plugin load, use, capability denial and unload.
- Cancellation, transport interruption and Backend shutdown during background work.
- Long-lived idle and active sessions with repeated recovery.
- Malformed input, disconnect/reconnect and repeated shutdown.
- TUI redraw/resize/input workloads after the interactive frontend is supported.

Each workload must specify document bytes, document/session/view counts, operation mix, warmup, iteration count and soak duration.

## 3. Required report fields for expanded benchmarks

| Field | Required value |
| --- | --- |
| Source | Commit SHA and immutable component pins. |
| Platform | OS version, architecture and native toolchain. |
| Build | Compiler, flags, build type and sanitizer settings. |
| Workload | Document bytes, document/session/view counts, operation mix, warmup and iterations. |
| Memory | Peak process RSS, sampled interval and allocator peak when exposed by a component. |
| Latency | p50, p95 and p99 for named operations, with sample count. |
| Safety | ASan, UBSan, leak checker, soak duration and failure count. |
| Comparison | Previous baseline and percentage change under the same workload. |

Do not infer missing memory values. Record `NOT AVAILABLE` when a component does not expose a metric and `NOT RUN` when a workload has not executed. Preserve raw measurement artifacts so results can be reproduced.

## 4. Current status

**Headless macro benchmark implementation: ADDED.** Native CI now runs the measurement and retains per-platform JSON artifacts. Numerical baselines are pending the next full workflow completion for this commit.

**Per-operation latency, allocator-level memory, multiple-session/plugin workloads and long-running soak: NOT IMPLEMENTED / NOT RUN.**

This document describes the measurement scope; it is not evidence that a particular performance target has been met.
