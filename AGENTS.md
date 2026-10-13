# AGENTS.md — rules for working on cdin (the runtime)

## 1. What this repository is

cdin: a C11 + Lua 5.4 editor runtime. C is the mechanism (buffer, events, jobs, syntax tokens, fonts, graphics, filesystem); Lua (`data/core/`) is the policy. cdin-x (separate repository) holds the package manager and every optional feature. cdin knows nothing about cdin-x and runs with an empty site directory.

Master prompt: `PROMPT_CDIN_MASTER.md`. Architecture, budgets, phases and open decisions are there.

## 2. Hard rules

1. **Never edit cdin-x or `website/`.** Report what cdin-x must do under `CDIN-X SIDE`.
2. **Never break the extension contract** (`docs/architecture/extension-contract.md`) unless an owner-approved decision says so. A removed or changed API stays as a shim that logs one deprecation per process.
3. **Lua state is single-threaded. Workers never touch Lua.** They work on immutable, ref-counted snapshots.
4. **No unbounded growth.** Every cache, queue, buffer and history has a byte cap and an eviction or refusal policy. No fixed ceiling that silently drops data (`push_command` returning NULL and losing a font is the bug to never repeat).
5. **Every handle has one owner and a defined lifetime.** Userdata with `__gc` and an explicit `close()`. A C object that Lua can reach cannot be freed while Lua can still use it.
6. **Bytes round-trip.** The buffer stores bytes. Never "sanitize" or rewrite file content (NUL, invalid UTF-8, BOM, EOL) on load; a decoder substitutes only for display.
7. **Never block the frame.** No `fread`/`popen`/`waitpid`/`sleep` loops on the main thread for anything unbounded.
8. **Never spawn through a shell.** `argv` arrays only.
9. **Do not run destructive commands. Do not commit unless asked.**
10. The editor must **build and start after every step**.

## 3. Priorities when they conflict

correctness and data safety > memory safety (no UB, no leaks) > bounded memory > latency > simplicity > modularity > brevity. Say so in the report when you chose between two.

## 4. What you write and what the owner writes

You write: C and Lua code, tests (unit, model-based, fuzz, soak, bench), harnesses, build/CI changes, LuaLS annotations, comments in code. The owner writes: documentation, README, changelog, guides. Where a doc is now wrong, list the passage under `OPEN`; do not edit it.

## 5. When to ask

Ask for: the open decisions in the master prompt (section 7); anything that would break a contract promise; a new external dependency not on the master prompt's list; any deletion of user-visible behaviour; any ambiguity where a wrong guess is expensive to undo. Otherwise decide from the code and say what you decided.

Format (always this shape, one question at a time):

```text
CONTEXT   what you are doing and what you found
DECISION  the one question
OPTIONS   A) ... (cost/benefit)  B) ...  C) ...
RECOMMEND the option and why
DEFAULT   what you will do if the owner does not answer
```

## 6. C style

- C11. Warnings: `-Wall -Wextra -Wshadow -Wconversion -Wstrict-prototypes -Wformat=2`, new code warning-free. `-Werror` on CI for `src/` files you touched.
- `snake_case`; module prefix on every public symbol (`buf_`, `rope_`, `evt_`, `job_`, `font_`, `gfx_`, `fs_`); types `CamelCase` typedefs (`Rope`, `Snapshot`, `Mark`); macros `UPPER_CASE`; no leading-underscore identifiers.
- One header per module with only what callers need; opaque types (`typedef struct Rope Rope;`) and constructor/destructor pairs: `x_new`/`x_free`, `x_open`/`x_close`. No struct fields poked from outside the module.
- Return values: a `CdinErr` or a negative errno-style code for fallible functions, out-parameters for results; never `abort()`/`exit()` outside `main` and a tiny, documented set of unrecoverable startup failures.
- Sizes are `size_t`, offsets are `int64_t` (files can exceed 2 GB), counts that cross the Lua boundary are `lua_Integer`. Check every arithmetic that can overflow before allocating or indexing. No `int` for a byte offset.
- Banned: `strcpy`, `strcat`, `sprintf`, `gets`, `atoi`, VLAs, `alloca`, bare `malloc/calloc/realloc/free` (use `cdin_*`), `static` mutable state without a comment saying who owns it and which thread touches it, `volatile` as synchronisation, `goto` other than the single-exit cleanup pattern.
- Cleanup: one exit label per function that frees in reverse order; no leak on any error path (verify with ASan leak checks and the fault-injection allocator, which fails the Nth allocation).
- Concurrency: a data structure is either owned by one thread or immutable and ref-counted. Atomics only in `loop/queue.c` and the ref counts, with comments naming the memory order. Locks are leaf locks; never call back into Lua or user callbacks while holding one.
- Lua bindings: validate every argument with `luaL_check*`/`luaL_opt*`; push exactly the documented results; no `lua_error`/`luaL_error` between a resource's allocation and its attachment to a userdata (a longjmp leaks it); use `lua_newuserdatauv` + metatable + `__gc` first, then fill; callbacks into Lua through one helper that does `pcall` + traceback + logging.
- Comments: one block comment at the top of each file saying what the file does and who owns what; inside, a comment only for a non-obvious invariant, a unit, an ownership rule, a memory order, or a reason a "wrong-looking" line is right. No narrating comments, no commented-out code, no TODOs without an owner decision.
- Formatting: `clang-format` with a checked-in config (4-space indent, 100 columns, braces on the same line); do not reformat code you are not changing.

## 7. Lua style

Same as the repository today (snake_case, modules return tables, classes through `core.utils.object`, strict globals, `core.add_thread` for background work, command/keymap registration paired with removal) plus: annotate public functions and types with LuaLS; `luacheck` clean with a checked-in `.luacheckrc` declaring the host globals; no per-line or per-token tables for text; no unbounded caches (weak tables or explicit caps); modules' top level is declarations, registration happens in `init`.

## 8. Memory and performance discipline

- Allocate through `cdin_alloc` with the subsystem tag. Report per-subsystem peak bytes in every phase report.
- No allocation in the steady-state draw path or in the per-keystroke path; verify with the accounting allocator (counter must not move across 1000 frames of typing).
- Prefer snapshots and views over copies. Copy only at an ownership boundary and say why.
- Streams over slurps: read in chunks, write in chunks, bound every intermediate.
- Choose the data structure by the 1 GB case, not the 1 KB case.
- Benchmarks live in `tests/bench/` and print numbers; a regression of more than 10% against the recorded baseline fails the phase.

## 9. Verification (run all of these yourself before every report)

```text
make                       # release build, no new warnings
make debug                 # -O0 -g3 build
make debug-san             # ASan + UBSan; run the suites under it
make test                  # C unit + model + Lua suites
make check                 # static analysis + luacheck
make bench                 # numbers vs baseline
# cross-repo (need a cdin-x checkout, read-only for you):
make test-plugins          # test_commands.lua + test_lua.lua
make test-site-dir
make test-workflows        # only the known cdin-x name failures may remain; list them
```

Additionally per phase: TSan for anything with threads; Valgrind for the code ASan cannot cover; fuzz runs for every external-input parser you wrote or changed (state duration and corpus size); the soak script when memory-related code changed. A check you could not run is listed as NOT RUN with the reason. Never claim a check passed that you did not run.

## 10. Git conventions

Conventional commits (`feat(buffer): ...`, `fix(loop): ...`), imperative, under 72 characters, one topic each. Pure moves are separate commits from edits. Commit only when asked. End commit messages with the attribution lines the session provides.

## 11. Final report format (after every phase)

```text
DONE        what changed, by subsystem, in plain words
DECISIONS   choices you made and why (and the owner's decisions you consumed)
MEASURED    numbers vs the baseline: memory per MB of text, open time, edit latency,
            frame time, idle CPU, startup, per-subsystem peak bytes
SANITIZERS  ASan / UBSan / TSan / Valgrind: what ran, result
FUZZ/SOAK   targets, duration, corpus size, findings fixed
COMPAT      contract rows touched; which suites ran; known cdin-x name failures
API ADDED   new functions/events/options (names)
DEPRECATED  shims kept, replacement named, planned removal
EDGE CASES  from the master prompt list that applied: handled or not, and how
CDIN-X SIDE what cdin-x must do or can now simplify
OPEN        stale docs, unresolved questions, risks
NEXT        the next phase and anything it depends on
```