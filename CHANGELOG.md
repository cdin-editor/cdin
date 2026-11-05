# Changelog

## Unreleased

### Changed
- Replace the legacy editor application tree with a focused Composition Root.
- Pin Runtime, Kernel, Backend, Frontend, logger and developer-tool revisions.
- Build and test the component stack from immutable source revisions.
- Keep interactive launch fail-closed until Backend readiness and Frontend event-loop integration are verified.
- Remove the website source and deployment workflow; the website is maintained in cdin-editor/cdin-editor.github.io.
- Rewrite the README and technical documentation to describe the current implementation and its real release gates.

### Fixed
- Always materialize dependency worktrees after cloning, even when the cloned HEAD already equals the locked SHA.
- Install the MSYS2 Python pip and Go toolchain packages needed by Windows CI.
- Pin the Backend component's compiler-warning fix from [Backend PR #1](https://github.com/cdin-editor/backend/pull/1).
- Prepare a local main branch and Git identity before running Gix diagnostics.
- Install Kernel's pkg-config metadata with the pinned package release version while preserving its separate ABI version.
- Avoid running the same architecture-boundary check twice in the Pipeline task graph.

### Not yet complete
- Live TUI/GUI event-loop integration and Frontend attachment.
- Product create/open/edit/save/reopen E2E through Kernel, Runtime, Backend and Frontend.
- Runtime command/keymap and plugin E2E through real frontend input.
- Measured process RSS, allocator peak, leak, soak and latency benchmarks.
- Production installers, Docker image and release workflows.
