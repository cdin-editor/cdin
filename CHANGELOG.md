# Changelog

## Unreleased

### Added
- Add an experimental POSIX TUI launch path behind the explicit `CDIN_ENABLE_EXPERIMENTAL_TUI=1` opt-in, using Frontend's terminal/session/event-loop APIs and CDIN-owned wake/signal lifecycle.
- Add a POSIX PTY acceptance harness for initial rendering, text input, SIGWINCH, save/quit with pending work, SIGTERM, startup failure and terminal restoration.
- Add compiler-resolved include-graph auditing from CMake's `compile_commands.json`, rejecting private component source/build headers and allowing installed public headers.
- Add six architecture policy tests for include classification, compiler-probe flags and trace parsing.
- Add exact-byte file fixtures for NUL/invalid UTF-8, BOM, LF-only and mixed CRLF/LF/CR data, plus missing-file and failed-atomic-save recovery.
- Add CLI regression coverage for missing values, fail-closed launch behavior and the advertised `headless|tui` frontend choices.

### Changed
- Correct the Composition Root boundary rule to permit the public Frontend TUI render adapter while continuing to reject direct SDL implementation calls.
- Export the CMake compile database and run the compiler-resolved include audit as part of the architecture check.
- Connect the CDIN logger to Frontend TUI Session/Model diagnostics.
- Document the two current execution modes: headless integration and opt-in experimental POSIX TUI.
- Refresh architecture audit, Spec traceability, E2E, benchmark, installation and user guides against current code and CI evidence.
- Keep Backend 1.0.2 and Frontend 1.0.0 package identity and immutable component pins explicit.

### Verification notes
- CDIN CI run [42117574266](https://github.com/cdin-editor/cdin/actions/runs/42117574266) passed the full Windows stack, 9/9 CDIN CTest tests, six architecture tests and compiler-resolved include graph for four CDIN translation units. The headless document/file/failure fixtures passed.
- The same run passed the headless CDIN CTest and Frontend 19/19 component suite on Linux and macOS, but the live POSIX PTY test failed (9/10 root CTest tests passed). The Linux sanitizer job failed on that same PTY test.
- Frontend PR [#11](https://github.com/cdin-editor/frontend/pull/11) contains a request-state lifecycle fix and regression tests for the TUI failure. Ubuntu, Windows and Pipeline/quality checks passed; macOS was still queued at the latest inspection. For integration testing only, CDIN's feature branch now pins the immutable unmerged PR head `efbb5804943d5aa4f0a303f2f7b7cd10bab42444`; CDIN CI run [42120816389](https://github.com/cdin-editor/cdin/actions/runs/42120816389) for that pin is pending. After PR #11 merges, replace the temporary pin with its immutable merge SHA and rerun the complete native/sanitizer matrix before the PTY gate is accepted.
- GitHub Code Quality's JavaScript/TypeScript job still requires a manual repository-setting correction because this repository has no JS/TS source. CodeQL Default Setup remains the scanner; verify its C/C++ and Python language selection in repository settings.

### Not yet complete
- Passing POSIX live PTY TUI E2E on the merged Frontend request-lifecycle fix.
- Native Windows Console TUI readiness/input/restore bridge and GUI-SDL launch.
- Plugin lifecycle/capability isolation, multiple Frontends, detach/reconnect and failure recovery.
- Linux/macOS compiler include-graph evidence after the TUI gate permits the task to run.
- Measured RSS/allocator peak, leak, soak and latency benchmarks.
- Clean-machine native application installers and signed application release artifacts.
