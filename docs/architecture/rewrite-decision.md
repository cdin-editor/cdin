# Big-bang rewrite decision

- Status: ACCEPTED
- Date: 2026-11-05
- Decision owner: repository owner
- Supersedes: the incremental migration strategy in cdin-editor/spec ADR-0012

## Context

The repository still contains the original monolithic SDL/Lua editor runtime. The target architecture has independently versioned Kernel, Runtime, Backend and Frontend components, with this repository acting as their composition root. The repository owner explicitly approved replacing the old implementation in one breaking-change rewrite. There are no production users whose compatibility requirements justify carrying the old interfaces forward.

## Decision

Replace the legacy implementation rather than migrating it incrementally. This decision is an explicit owner-approved exception to the incremental migration strategy in Spec ADR-0012. ADR-0012 is no longer the governing implementation strategy for this repository.

The rewrite has these boundaries:

- **Kernel** owns canonical document bytes, document versions, snapshots, undo/redo and byte-position primitives. It is consumed through its published C ABI.
- **Runtime** owns Lua 5.4 policy: commands, keymaps, configuration, UI model, syntax policy and extension loading. It accesses documents only through Backend's Runtime Host API.
- **Backend** owns Kernel adaptation, Runtime hosting, OS services, frontend sessions, protocol validation, bounded queues, backpressure, sequencing and transport endpoints.
- **Frontend** owns presentation and input adaptation. TUI, GUI and Headless are peers behind the Frontend Protocol. Frontends do not call Kernel or Backend-private APIs and do not resolve keymaps.
- **cdin** owns composition, ABI/version checks, frontend selection/launch, build orchestration, packaging, release workflows and developer tooling. It contains no editor-domain implementation.

No compatibility shims are required for the old private APIs. Remove legacy modules, dependencies and observable behavior when their replacements are implemented and covered by end-to-end tests. Do not preserve an old interface merely to avoid a breaking change.

## Legacy surfaces to replace

The rewrite must remove the old monolithic ownership and its private APIs, including:

- SDL window, renderer, renderer cache, font and platform display code from the composition root.
- Embedded Lua state, Lua C modules, document/editor policy and plugin loading from the composition root.
- The old event/job loop, allocator and filesystem/search services when they duplicate Kernel or Backend ownership.
- The legacy command/keymap/config/plugin contracts and their old data layout.
- Legacy CLI flags and startup/shutdown behavior that are not defined by the Spec.
- Unit-test-only architecture as the primary product verification strategy.

The removal is complete only when the replacement path is exercised through the actual executable and component packages. Deleting files before their replacement is connected is not a completed rewrite.

## Required implementation sequence

1. Replace the old build graph and dependency discovery with pinned component package inputs; no build-time source downloads or floating component branches.
2. Implement the launcher and CLI from the current Spec, including component ABI/version checks and explicit frontend selection.
3. Compose Backend with the published Kernel ABI and Runtime Host API; configure m-mdy-m/log.c as the shared structured logger.
4. Launch the selected Frontend adapter and connect it through the Frontend Protocol. TUI is the first interactive target; Headless is the protocol reference.
5. Move keymaps, commands, plugin loading and user-visible policy to Runtime and validate them against the current Spec.
6. Replace old build, bundle, install and release workflows with m-mdy-m/pipeline; use m-mdy-m/psx for repository structure checks and m-mdy-m/gix for the configured branch flow.
7. Remove superseded source, headers, dependencies, data, scripts and tests. No parallel legacy implementation remains at completion.

## Verification gates

Product behavior is verified primarily through integration and end-to-end tests, not isolated unit tests.

- Real executable startup, CLI parsing, help/version, invalid arguments and exit codes.
- Full document lifecycle: open, edit, save, close and reopen, with byte-exact content.
- Runtime command and keymap dispatch from real frontend input events.
- Plugin discovery, loading, capability denial, failure isolation and unload behavior.
- Protocol negotiation, malformed frames, sequence errors, reconnect, detach and resynchronization.
- TUI and Headless end-to-end flows first; GUI flows when the GUI adapter is enabled.
- Linux, macOS and Windows native CI. Include Windows named pipes and Unix-domain sockets on their supported platforms.
- ASan, UBSan, TSan where applicable, leak checking, bounded-queue/backpressure tests, fuzzing of external parsers and long-running soak tests.
- Memory and latency benchmarks across small, medium and large documents, many views, large paste, repeated open/close, syntax-heavy files and concurrent background work. Record RSS and component-level memory where available; compare against committed baselines.
- A skipped or unavailable check is reported as NOT RUN, never as PASS.

## Implementation constraints

- Pin released Kernel, Runtime, Backend, Frontend and logger versions/commits. Never fetch dependencies from a floating branch during a build.
- All queues, caches, messages and histories have explicit byte/count limits and a documented refusal or eviction policy.
- Lua remains single-threaded; workers never access Lua state.
- Each resource has one owner and a defined lifetime; shutdown is reverse dependency order.
- New C code is warning-clean under the repository's strict warning set. Do not add a unit-test suite as a substitute for product-level E2E coverage.
- Do not claim a build, test, sanitizer, benchmark or platform passed unless it was actually run and its result inspected.

## Consequences

This is intentionally a breaking rewrite. Existing users' configuration, keymaps, plugin interfaces, CLI invocations and undocumented behaviors are not compatibility constraints. The Spec contracts and published component APIs are the source of truth. The old implementation is removed as replacement slices become executable and verified; the final state contains only the new composition-root architecture.
