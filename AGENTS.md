# AGENTS.md — CDIN Composition Root

## Repository responsibility

CDIN owns immutable dependency pins, build orchestration, bundling, release
tooling, installation, CLI composition, process lifecycle and verification.
It is not an editor implementation.

- Kernel owns canonical document bytes, edits, versions, snapshots and undo/redo.
- Runtime owns Lua policy, commands, keymaps, configuration and plugin lifecycle.
- Backend owns Kernel adaptation, Runtime hosting, OS services, sessions,
  protocol server, queues and transport endpoints.
- Frontend owns input adaptation, semantic projection, layout and rendering.
- This repository composes public contracts only. Never copy component source.

The owner-approved full rewrite in docs/architecture/rewrite-decision.md
supersedes legacy incremental-migration instructions. The Spec remains
normative for component behavior.

## Non-negotiable rules

1. Production builds use immutable revisions in deps.lock; never download a
   floating branch or silently substitute an unknown installed component.
2. Never duplicate Kernel, Runtime, Backend or Frontend APIs/implementation.
   Keymaps, commands and plugins remain Runtime responsibilities.
3. Validate versions/protocol compatibility before startup and shut down in
   reverse dependency order. Release resources on every error path.
4. Never report an unavailable test as passing. Missing pinned source trees are
   a CI configuration failure.
5. Keep buffers and queues bounded; backpressure must preserve complete input.
6. Implement only CLI behavior defined by the current Spec. Do not invent a
   standalone editor CLI or alternate plugin/keymap APIs.
7. New C code is C11 and warning-clean with -Wall -Wextra -Wshadow -Wconversion
   -Wstrict-prototypes -Wformat=2 -Wpedantic -Werror.
8. CDIN tests prioritize executable, lifecycle and cross-component E2E. Do not
   add unit-test-only substitutes for real product behavior.
9. Resource benchmarks report measured memory/latency and identify the workload.
   Never infer product RSS or leak results from transport buffer sizes.
10. Do not modify sibling component repositories in a CDIN change. Track
    component-side contract work separately.

## Required verification

```sh
python3 scripts/deps.py
python3 scripts/check_boundaries.py
python3 scripts/build_stack.py
pipeline run check
psx check
gix doctor
```

Native CI must cover Linux, macOS and Windows. ASan/UBSan with leak detection
runs on Linux. If a tool, platform or dependency is unavailable, report it as
NOT RUN with the reason. Product edit/save E2E, live TUI/GUI and measured memory
benchmarks remain release gates until implemented.

## Git workflow

Use .gix/config for branch flow. Use Conventional Commit subjects in imperative
mood, under 72 characters. Never force-update a branch.
