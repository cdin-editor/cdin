# Changelog

## Unreleased

### Added
- Keep GitHub CodeQL Default Setup as the repository scanner and remove the competing advanced-mode workflow.
- Add reproducible source-snapshot generation with safe member paths, CRC checks and SHA-256 sidecar.
- Add CLI regression checks for missing option values and fail-closed interactive/frontend launch behavior.
- Add a live headless Frontend Protocol document cycle: typed commands, text/binary paste, undo/redo, atomic save, close/open and exact-byte readback.
- Add trusted-main-branch source snapshot provenance attestation.

### Changed
- Pin GitHub Actions to full commit SHAs and upgrade the action runtimes to current Node 24-compatible releases.
- Restrict Dependabot configuration to the GitHub Actions ecosystem actually used by this repository.
- Add explicit timeouts to native and sanitizer CI jobs.
- Correct the Backend package compatibility documentation to match the required versioned `cdinBackend 1.0.0` CMake package.
- Record the successful Runtime version identity check against `deps.lock`.
- Update integration status, architecture audit, dependency matrix and security policy to reflect the current implementation and evidence.
- Extend the Frontend Protocol smoke from ATTACH/snapshot/flush/ACK/resize to a headless create/edit/save/reopen workflow verified on Linux, macOS and Windows (CI run 42074655322).

### Not yet complete
- Interactive TUI/GUI readiness/rendering and event-loop integration; GUI-SDL launch.
- Full BOM/LF/mixed-EOL and injected filesystem-failure product matrix through CDIN.
- Plugin lifecycle/capability isolation, multiple Frontends, detach/reconnect and recovery.
- Measured process RSS, allocator peak, leak, soak and latency benchmarks.
- Production platform installers and signed application release artifacts.
