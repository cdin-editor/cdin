# Changelog

## Unreleased

### Added
- Add a dedicated CodeQL workflow for the repository's actual C/C++ and Python source languages.
- Add reproducible source-snapshot generation with safe member paths, CRC checks and SHA-256 sidecar.
- Add CLI regression checks for missing option values and fail-closed interactive/frontend launch behavior.
- Add trusted-main-branch source snapshot provenance attestation.

### Changed
- Pin GitHub Actions to full commit SHAs and upgrade the action runtimes to current Node 24-compatible releases.
- Restrict Dependabot configuration to the GitHub Actions ecosystem actually used by this repository.
- Add explicit timeouts to native and sanitizer CI jobs.
- Correct the Backend package compatibility documentation to match the required versioned `cdinBackend 1.0.0` CMake package.
- Record the successful Runtime version identity check against `deps.lock`.
- Update integration status, architecture audit, dependency matrix and security policy to reflect the current implementation and evidence.
- Keep the Frontend handshake smoke explicitly scoped to HELLO/HELLO_ACK; it does not claim view attachment or editing.

### Not yet complete
- Live TUI/GUI event-loop integration, view attachment and UI snapshot delivery.
- Product create/open/edit/save/reopen E2E through Kernel, Runtime, Backend and Frontend.
- Runtime command/keymap and plugin E2E through real Frontend input.
- Measured process RSS, allocator peak, leak, soak and latency benchmarks.
- Production platform installers and signed application release artifacts.
