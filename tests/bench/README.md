# Resource and soak benchmarks

No product memory benchmark is claimed by this rewrite yet. The current CDIN
executable test checks startup and orderly shutdown; Backend's bounded queues
are not a substitute for process RSS, allocator peak, leak or long-session
measurements.

Before release, add repeatable workloads against the real document workflow:
multiple document sizes, large edit/undo histories, many sessions, plugin
load/unload, repeated open/close, cancellation and long-lived idle/active
sessions. Record OS, compiler, build type, commit pins, iteration/sample count,
document bytes, peak RSS, allocator peak where exposed, wall-clock latency
(p50/p95/p99), and sanitizer/leak results.

Do not publish a benchmark until the Kernel-backed create/open/edit/save/reopen
path is exercised end-to-end and the workload can be reproduced from CI.
