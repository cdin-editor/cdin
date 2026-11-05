# Changelog

## Unreleased

### Changed
- Replace the legacy editor application tree with the Composition Root boundary.
- Pin Runtime, Kernel, Backend, Frontend, logger and tooling revisions.
- Add deterministic stack build, executable lifecycle tests and native CI matrix.
- Make interactive launch fail-closed until the Backend readiness contract exists.

### Not yet complete
- Live TUI/GUI event-loop integration (FE-019).
- Product create/open/edit/save/reopen E2E through Kernel, Runtime, Backend and Frontend.
- Measured process RSS, allocator peak, leak, soak and latency benchmarks.
