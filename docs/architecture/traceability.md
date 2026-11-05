# Spec traceability

This page connects requirements to CDIN source and records whether the current implementation proves them. Spec links point to the requirement's source line in the inspected canonical Spec revision. Proposed requirements remain marked proposed in the Spec even when this rewrite makes progress toward them.

## 1. Requirement matrix

| Requirement | Spec status | CDIN evidence | Current result |
| --- | --- | --- | --- |
| [ARCH-001](https://github.com/cdin-editor/spec/blob/main/docs/architecture/overview.md#L113-L113) — CDIN is the composition root and must not reimplement component logic | ACCEPTED | `src/main.c`, `src/cli/options.c`, `CMakeLists.txt` | **PARTIAL** — the current source stays small and composition-focused; complete Frontend launch is not implemented. |
| [ARCH-040](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L65-L65) — Kernel dependency boundary | ACCEPTED | `CMakeLists.txt`; Backend package is built with the pinned Kernel | **PARTIAL** — CDIN links Kernel for the static link closure but does not include or call its API. Backend owns integration. |
| [ARCH-041](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L66-L66) — Runtime uses Backend Host API | PROPOSED | `src/main.c` passes Runtime root/entry to Backend | **IMPLEMENTED for lifecycle smoke test**, not live editor behavior. |
| [ARCH-042](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L67-L67) — Backend has no display-toolkit dependency | ACCEPTED | Backend's own CMake/source; pinned build in `scripts/build_stack.py` | **Owned by Backend; not reimplemented in CDIN.** |
| [ARCH-043](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L68-L68) — Frontend depends on Protocol and its toolkit | ACCEPTED | Frontend package pin and Frontend-owned code | **Owned by Frontend; CDIN does not implement an adapter.** |
| [ARCH-044](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L69-L69) — `cdin-x` depends only on the extension contract | PROPOSED | Not applicable to this `cdin` Composition Root executable | **NOT IMPLEMENTED here** — `cdin-x` is a separate Spec-defined extension host and is not silently treated as the application Composition Root. |
| [ARCH-045](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L70-L70) — Composition Root may assemble components and must not be depended on | PROPOSED | Root executable links installed component interfaces | **PARTIAL** — no reverse dependency is introduced in this repository; complete product composition remains open. |
| [ARCH-046](https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L71-L71) — include-direction rules are enforced by implementation repositories' static checks | PROPOSED | `scripts/check_boundaries.py` | **PARTIAL** — current checks reject selected copied implementation calls, but do not yet inspect the complete include graph. |
| [ROOT-001](https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md#L22-L22) — no reimplementation of component logic | ACCEPTED | `src/` contains launcher, CLI parsing and diagnostics only | **IMPLEMENTED for current source tree.** |
| [ROOT-006](https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md#L27-L27) — launcher selects a frontend and passes Backend endpoint | PROPOSED | `src/cli/options.c`; `src/main.c` | **NOT IMPLEMENTED** — only the headless check value is accepted; there is no attached frontend endpoint. |
| [ROOT-007](https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md#L28-L28) — compatibility checks for assembled components | PROPOSED | `CMakeLists.txt`; `src/main.c`; `scripts/build_stack.py` | **PARTIAL** — versioned Backend 1.0.0, Frontend Core 1.0.0 and logger 0.1.0 packages are required; Backend runtime/header version, Protocol major/minor and pinned Runtime-reported version are checked. This is not a full semantic ABI matrix. |
| [ROOT-010](https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md#L31-L31) — Kernel consumed as a pinned version | PROPOSED | `deps.lock`; `scripts/deps.py` | **IMPLEMENTED for source build pinning**; a released binary dependency installation is not yet available. |
| [PROTO-001](https://github.com/cdin-editor/spec/blob/main/docs/architecture/frontend-protocol.md#L36-L36) — Backend owns editor state; Frontends may detach/reattach | ACCEPTED | Backend session and Protocol implementation; component tests | **Backend-owned. CDIN product detach/reattach E2E is NOT IMPLEMENTED.** |
| [PROTO-004](https://github.com/cdin-editor/spec/blob/main/docs/architecture/frontend-protocol.md#L40-L40) — raw keys go to Backend; Runtime owns keymap policy | ACCEPTED | Runtime and Backend components; no CDIN keymap code | **Ownership boundary preserved.** End-to-end input path is not connected. |
| [PROTO-010](https://github.com/cdin-editor/spec/blob/main/docs/architecture/frontend-protocol.md#L69-L69) — handshake starts with hello/hello_ack | ACCEPTED | Backend and Frontend Protocol implementations | **CDIN `--check` initiates HELLO/HELLO_ACK through Frontend Core; view attach and interactive flow remain pending.** |
| [FE-019](https://github.com/cdin-editor/spec/blob/main/docs/components/frontend.md#L82-L82) — TUI event loop multiplexes input, Backend readiness and lifecycle events | ACCEPTED | Frontend TUI is built as a pinned component; CDIN launch guard is in `src/main.c` | **NOT VERIFIED end-to-end** — interactive launch is gated until readiness/wakeup integration is complete. |

## 2. Source evidence

- Build dependencies and Protocol checks: [`CMakeLists.txt`](https://github.com/cdin-editor/cdin/blob/feature/complete-composition-root-rewrite/CMakeLists.txt#L11-L32).
- CLI parsing and supported options: [`src/cli/options.c`](https://github.com/cdin-editor/cdin/blob/feature/complete-composition-root-rewrite/src/cli/options.c#L1-L49).
- Backend version check and lifecycle order: [`src/main.c`](https://github.com/cdin-editor/cdin/blob/feature/complete-composition-root-rewrite/src/main.c#L24-L80).
- Backend Protocol version compile-time guard: [`src/main.c`](https://github.com/cdin-editor/cdin/blob/feature/complete-composition-root-rewrite/src/main.c#L10-L14).
- Logger initialization and Backend severity mapping: [`src/diagnostics/log.c`](https://github.com/cdin-editor/cdin/blob/feature/complete-composition-root-rewrite/src/diagnostics/log.c#L4-L50).
- Component build/test order and Runtime version assertion: [`scripts/build_stack.py`](https://github.com/cdin-editor/cdin/blob/feature/complete-composition-root-rewrite/scripts/build_stack.py#L48-L93).
- Pipeline tasks: [`pipeline.toml`](https://github.com/cdin-editor/cdin/blob/feature/complete-composition-root-rewrite/pipeline.toml#L10-L35).

## 3. Static boundary check

The current [`scripts/check_boundaries.py`](https://github.com/cdin-editor/cdin/blob/feature/complete-composition-root-rewrite/scripts/check_boundaries.py) scans CDIN C sources for selected calls that would copy Kernel, Runtime or Frontend implementation into the Composition Root. It does not parse compiler include graphs and cannot prove all ARCH-040 through ARCH-046 include-direction constraints. Full include-graph checking remains **PARTIAL** and must not be reported as complete.

## 4. Verification rule

A source link proves where code or a requirement is written; it does not prove runtime behavior. Runtime behavior is marked implemented only after an executable test or component integration test exercises the relevant public interface. Workflow configuration is not a passing CI result. See [Integration status](../development/integration-status.md) for current run evidence.
