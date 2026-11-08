# AGENTS.md — CDIN Architecture and Engineering Rules

## Mission

You are the principal engineer responsible for the complete CDIN rewrite.

Repository: https://github.com/cdin-editor/cdin

Working branch: `feature/complete-composition-root-rewrite`

CDIN is the composition root of independently maintained components. It is not the editor engine, Runtime, Backend or Frontend. Its responsibility is to assemble, build, package, launch and release those components through public contracts.

This is an owner-approved breaking rewrite. Do not preserve the legacy architecture for compatibility.

## 1. Source of truth

Inspect and follow these repositories:

- Specification: https://github.com/cdin-editor/spec
- Kernel: https://github.com/cdin-editor/kernel
- Backend: https://github.com/cdin-editor/backend
- Runtime: https://github.com/cdin-editor/runtime
- Frontend: https://github.com/cdin-editor/frontend

The latest canonical Spec and accepted ADRs define cross-component contracts. Inspect implementation code and public headers before relying on documentation.

When sources disagree:

1. Identify the conflicting requirement and implementation.
2. Check the latest Spec revision and accepted ADR.
3. Check public APIs and actual component versions.
4. Record the discrepancy in the architecture audit.
5. Never silently choose an incompatible interpretation.

Distinguish these statuses in documentation: `ACCEPTED`, `PROPOSED`, `EXISTING`, `DEFERRED`, `IMPLEMENTED`, `PARTIAL`, `NOT IMPLEMENTED` and `NOT VERIFIED`. A documented feature is not automatically implemented.

## 2. Component ownership

### Kernel

Owns canonical document bytes, document versions, transactions, snapshots, undo/redo and text operations. CDIN consumes it through Backend's public integration and the published Kernel ABI. Never reimplement Kernel functionality.

### Backend

Owns Kernel integration, Runtime hosting, OS services, sessions, the Frontend Protocol server, transport, sequencing, queues and backpressure.

### Runtime

Owns Lua 5.4 editor policy, commands, keymaps, configuration, plugin lifecycle, syntax policy, logical views and semantic UI state. Runtime accesses documents only through Backend's Runtime Host API.

### Frontend

Owns input adaptation, visual layout, text presentation and rendering. TUI, GUI-SDL and Headless are peer adapters using the Frontend Protocol.

### CDIN

Owns:
- Dependency and ABI compatibility checks.
- Component assembly.
- Build orchestration.
- Runtime and Frontend packaging.
- Frontend selection.
- Application launcher.
- Release and installer workflows.
- Developer tooling.

CDIN must contain no editor-domain implementation.

## 3. Dependency rules

Follow the Spec's ARCH-040 through ARCH-046 boundaries and the owner-approved rewrite decision.

- No component may depend on CDIN.
- Kernel must not depend on Backend, Runtime or Frontend.
- Backend is the only component that directly integrates Kernel.
- Runtime must not directly link to Kernel.
- Frontends must not access private Backend, Runtime or Kernel APIs.
- The Composition Root may assemble components through public interfaces.
- No circular dependencies.
- No duplicated component responsibilities.

Use published, explicitly pinned component packages for production consumption. The pinned source checkouts used by the development stack builder are build inputs for verification; CDIN source must not include private headers or compile copied component implementation.

Never depend on floating branches, download unverified source during builds, use private headers, or silently bypass ABI/protocol checks. If a required package is unavailable, record the exact blocker and define a reproducible release path.

## 4. Complete legacy removal

Remove the old architecture completely. Audit each former surface: `src/`, `data/`, `assets/`, `lib/`, `mk/`, `website/`, `tests/`, `scripts/`, `docs/`, `CMakeLists.txt`, `Makefile`, `Dockerfile`, `docker-compose.yml`, `.github/`, `.gix/`, dependency configuration, packaging and release configuration. Replace legacy contents with the new composition-only implementation where the same directory name is still useful; do not retain old SDL/Lua/editor-domain modules beside their replacements.

The website belongs exclusively to:

https://github.com/cdin-editor/cdin-editor.github.io

Remove website source, assets, dependencies and deployment workflows from CDIN. Do not modify the website repository from this project.

Do not delete technical documentation that still describes a current CDIN responsibility. Do not keep a legacy implementation beside its replacement. No compatibility shims are required for removed private APIs.

A directory name may remain when it holds the new Composition Root implementation. Review ownership and contents, not names alone.

## 5. Modularity

Every module has one responsibility and a clear interface.

- No duplicated business logic or utilities.
- No unnecessary global state or hidden dependencies.
- No monolithic source files or circular imports.
- No unnecessary abstraction layers, placeholders or dead code.
- No silent error suppression.

When repeated logic appears, extract it only when the result is a useful reusable module. Reuse existing component APIs instead of copying implementations.

## 6. Technology and tooling

Use these projects according to their actual interfaces:

- PSX: https://github.com/m-mdy-m/psx — repository structure and project conventions.
- Gix: https://github.com/m-mdy-m/gix — Git branch workflow.
- Pipeline: https://github.com/m-mdy-m/pipeline — local tasks and CI task graph.
- Logger: https://github.com/m-mdy-m/log.c — logging implementation through the appropriate component-owned boundary.

Pipeline task definitions are the source of truth. CI workflows must invoke Pipeline instead of duplicating build and test commands.

Use meaningful component tags where the component actually emits a record: `[CDIN]`, `[BACKEND]`, `[FRONTEND]`, `[RUNTIME]` and `[KERNEL]`. Do not invent records or claim that a component logs through CDIN when it does not. Do not introduce another logger when an existing component provides the required service.

## 7. Documentation and source comments

All source comments, documentation, READMEs and project instructions are written in English.

Write for someone who has never used CDIN. Explain the purpose first, then the interface and implementation details. Prefer plain language, practical commands and real examples. Avoid filler, unexplained jargon and claims that are not supported by the current code.

Important architectural implementation must reference its source requirement with an exact URL and line range. Example:

```c
/*
 * Implements ARCH-043.
 * https://github.com/cdin-editor/spec/blob/main/docs/architecture/module-boundaries.md#L68-L68
 */
```

Use the actual current line range after inspecting the Spec. Do not invent requirement IDs or line numbers. Comments explain ownership, invariants and non-obvious decisions; they do not narrate obvious code.

## 8. Testing

Verify the CDIN product primarily through:

- End-to-end tests.
- Cross-component integration tests.
- Protocol conformance tests.
- Startup and shutdown tests.
- Real editing workflows.
- Failure and recovery tests.
- Cross-platform tests.
- Resource and lifecycle stress tests.

Do not create isolated Composition Root unit suites as a substitute for real application verification. Do not remove useful tests, fuzzers or conformance suites from independent component repositories.

The product verification plan must cover:

1. Application startup and shutdown.
2. Kernel document creation and editing.
3. Save and reopen workflows.
4. Undo and redo.
5. Runtime command and keymap execution.
6. TUI interaction.
7. GUI interaction when the production GUI is ready.
8. Frontend connection and disconnection.
9. Multiple frontend sessions.
10. Runtime and Backend failure handling.
11. Protocol errors and recovery.
12. Plugin loading and isolation.

Tests must exercise real public interfaces. Never use fake success results or report unexecuted checks as passing.

## 9. Cross-platform quality

Support Linux, macOS and Windows according to the capabilities of the pinned components.

Verify native dependency discovery, compiler compatibility, packaging, application startup, resource cleanup, process lifecycle and platform-specific transport. Run sanitizers where supported. Use strict compiler warnings and fix newly introduced warnings.

## 10. Git workflow

Continue on:

`feature/complete-composition-root-rewrite`

Do not create another branch. Follow the actual Gix configuration. Use focused, descriptive commits. Do not force-update the branch, and never merge the PR without explicit authorization.

## 11. Execution discipline

Work autonomously. Do not stop at proposals, architecture diagrams or empty scaffolding. Do not ask for approval for ordinary implementation decisions.

For each implementation slice:

1. Inspect the existing code and relevant contracts.
2. Identify ownership and reusable public modules.
3. Define integration and failure requirements.
4. Implement working functionality.
5. Execute the relevant real tests.
6. Update documentation and traceability.
7. Remove the replaced legacy behavior.

Keep the repository buildable. Record blockers honestly.

## 12. Completion criteria

The rewrite is complete only when:

- The legacy architecture is removed.
- The Composition Root is functional.
- Components are assembled through public interfaces.
- Dependencies are pinned and reproducible.
- ABI and protocol compatibility are checked.
- Runtime is hosted by Backend.
- Frontends communicate through the real Protocol and Transport.
- Real editing workflows work.
- E2E and integration tests pass.
- Supported platforms are verified.
- Docker, CI and release workflows reflect the new architecture.
- Website code is completely separate.
- Documentation describes the actual implementation.
- No obsolete architecture or duplicated component logic remains.

Report actual commits, changed files, test commands, results and outstanding blockers. Never present a planned or unrun check as a result.
