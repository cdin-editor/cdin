# Changelog

## Unreleased

### Added
- Add a dedicated CodeQL workflow for the repository's actual C/C++ and Python source languages.
- Upload a validated source snapshot from each native CI platform as a short-lived verification artifact.

### Changed
- Add explicit timeouts to native and sanitizer CI jobs.
- Update integration status and architecture audit with the latest inspected green stack/sanitizer evidence and the remaining interactive-product gates.
- Keep the Frontend handshake smoke explicitly scoped to HELLO/HELLO_ACK; it does not claim view attachment or editing.

### Not yet complete
- Live TUI/GUI event-loop integration, view attachment and UI snapshot delivery.
- Product create/open/edit/save/reopen E2E through Kernel, Runtime, Backend and Frontend.
- Runtime command/keymap and plugin E2E through real Frontend input.
- Measured process RSS, allocator peak, leak, soak and latency benchmarks.
- Production platform installers and signed release artifacts.
