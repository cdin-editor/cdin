# Integration status and release gates

This document distinguishes source integration from a verified, runnable product workflow.

| Area | Current status |
|---|---|
| Composition Root ownership | implemented in this rewrite |
| immutable component/tool pins | declared in deps.lock |
| Kernel integration | consumed through Backend's public dependency and ABI |
| Runtime | installed as Lua assets and configured through Backend |
| Backend lifecycle | --check exercises create/start/pump/shutdown/destroy |
| Frontend Core | pinned as a required peer dependency; launch is gated |
| TUI/GUI live editing | NOT COMPLETE; FE-019 readiness/event-loop contract remains open |
| document create/open/edit/save/reopen E2E | NOT COMPLETE at the Composition Root level |
| memory/soak benchmark | NOT RUN; do not infer it from bounded protocol queues |
| Windows/macOS/Linux validation | CI jobs configured; results are pending actual workflow execution |

The Backend repository owns Kernel document integration scenarios. CDIN's full-stack job builds and runs those tests, then runs the Composition Root lifecycle smoke test. This is not yet equivalent to a user-visible edit/save round trip through a live Frontend.

## Required before interactive release

1. Backend readiness/wakeup compatible with Frontend's event loop.
2. Live TUI and GUI adapters attached through the same Frontend Core protocol.
3. Product E2E: create/open/edit/save/reopen exact-byte comparisons, including NUL, invalid UTF-8, BOM and line-ending preservation.
4. Measured RSS/allocator peak, leak, long-session and multi-document benchmarks.
5. Passing native Linux, macOS and Windows CI runs and sanitizer evidence.
