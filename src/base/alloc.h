/* The allocator facade every allocation in src/ goes through.
 *
 * One entry point per operation, each carrying a subsystem tag, and one free
 * that does not: cdin_free(p) reads the tag out of the header the allocator
 * wrote. That asymmetry is deliberate — a tag on free would mean the caller
 * has to remember it, and a caller that remembers a tag wrong corrupts the
 * accounting, which is the one thing this file exists to get right.
 *
 * Why a header at all: so that free can subtract exactly the right number from
 * exactly the right subsystem, detect a pointer that never came from here, and
 * detect a double free. The alternative — tag the pointer in a side table —
 * costs a hash lookup per free and cannot catch a foreign pointer.
 *
 * Ownership: this module owns every block it returns, and nothing else may
 * free() them directly. A pointer from here must only be released by
 * cdin_free.
 *
 * Threads: main thread only, today. Counters, registry and quarantine are
 * plain statics. Phase 3 needs an owner decision before workers exist: a
 * ref-counted snapshot is freed by whichever thread drops the last reference,
 * so cdin_free (and its counters) will be called off the main thread. Per-thread
 * arenas do not cover that; it needs relaxed atomic or per-thread sharded
 * counters, which AGENTS.md §6 currently does not allow outside loop/queue.c.
 */

#ifndef CDIN_BASE_ALLOC_H
#define CDIN_BASE_ALLOC_H

#include <stddef.h>

/* One tag per subsystem, so "where did the bytes go" has an answer rather
 * than a guess. The names are the ones the master prompt budgets against;
 * CDIN_MEM_BASE is for the allocator's own scratch and anything with no more
 * specific home.
 *
 * Values are stable and public: core:memory reports them by name, so
 * inserting one in the middle renames a subsystem in every report that ever
 * mentioned it. Append only. */
typedef enum {
  CDIN_MEM_BASE = 0,      /* allocator internals, anything uncategorised */
  CDIN_MEM_BUFFER,        /* text buffers, lines, snapshots          (Phase 4) */
  CDIN_MEM_SYNTAX,        /* token stores                            (Phase 6) */
  CDIN_MEM_FONT,          /* glyph atlases, shaping buffers          (Phase 7) */
  CDIN_MEM_GFX,           /* images, surfaces, layers                (Phase 8) */
  CDIN_MEM_LUA_BIND,      /* userdata, callback registries                    */
  CDIN_MEM_PLATFORM,      /* paths, config dirs                               */
  CDIN_MEM_LOOP,          /* jobs, timers, queue, pool             (Phase 3) */
  CDIN_MEM_FS,            /* path handling, atomic-write scratch              */
  CDIN_MEM_EDIT,          /* undo/redo nodes, history            (Phase 5) */
  CDIN_MEM_COUNT          /* sentinel — not a subsystem */
} CdinMemTag;

/* Allocate `size` bytes tagged to `subsystem`. Returns NULL when the request
 * cannot be served — including when fault injection is armed — and the
 * caller must handle it. Nothing in src/ may assume a non-NULL result outside
 * of the handful of places AGENTS.md names as unrecoverable. */
void *cdin_alloc(CdinMemTag subsystem, size_t size);

/* As cdin_alloc, zeroed. A zero-size calloc is a valid distinct pointer, as
 * the C standard requires, not a NULL. */
void *cdin_calloc(CdinMemTag subsystem, size_t count, size_t size);

/* Resize, preserving the original tag. Returns NULL on failure and leaves
 * `p` valid and untouched, so a failed realloc is not a leak by itself. */
void *cdin_realloc(CdinMemTag subsystem, void *p, size_t size);

/* Release a pointer from any cdin_alloc/cdin_calloc/cdin_realloc.
 *
 * Freeing NULL is a no-op. A pointer this module did not return, or one it
 * already released, is refused (counted by cdin_mem_bad_frees, logged, not
 * passed to free()). That detection is best effort: it reads the header in
 * front of `p`, so a foreign pointer needs readable memory there, and a double
 * free is only reliably caught in a debug build, which holds freed blocks in a
 * small quarantine. In a release build a double free is undefined behaviour,
 * as with free(). */
void cdin_free(void *p);

/* ── accounting ─────────────────────────────────────────────────────────
 *
 * Live = bytes currently handed out. Peak = the high-water mark since
 * process start, per subsystem. Both are exact, not sampled, and neither
 * moves unless an allocation happens — which is what makes "the counter must
 * not move across 1000 frames of typing" a checkable statement rather than
 * a hopeful one.
 *
 * Peak never decreases, including after cdin_free. A peak is a record of what
 * happened, and a cache that has already grown once cannot un-grow in the
 * sense that matters. */

size_t cdin_mem_live(CdinMemTag subsystem);
size_t cdin_mem_peak(CdinMemTag subsystem);
size_t cdin_mem_alloc_count(CdinMemTag subsystem);

/* Totals across every subsystem.
 *
 * cdin_mem_total_live is the sum of the per-tag figures and cannot drift from
 * them. cdin_mem_total_peak is NOT the sum of the per-tag peaks — two
 * subsystems rarely peak at the same instant, so summing their peaks reports
 * a high-water mark this process never reached. It is the largest value
 * cdin_mem_total_live has ever held. */
size_t cdin_mem_total_live(void);
size_t cdin_mem_total_peak(void);

/* The tag a live pointer belongs to, or CDIN_MEM_COUNT if it is not one of
 * ours. Used by the report to attribute an unexpected block. */
CdinMemTag cdin_mem_tag_of(const void *p);

/* Name of a tag, for reports. "unknown" for an out-of-range value rather
 * than an out-of-bounds read. */
const char *cdin_mem_tag_name(CdinMemTag subsystem);

/* ── fault injection ────────────────────────────────────────────────────
 *
 * AGENTS.md §6 requires a fault-injection allocator that fails the Nth
 * allocation, because the interesting question in a reviewer is "what happens
 * when this returns NULL" and the only honest answer is to run it.
 *
 * The semantics are "let the next n allocations through, refuse every one
 * after that", not "refuse the nth". The difference matters: a test that
 * wants the tenth allocation inside a buffer splice to fail has to let the
 * first nine succeed, and a version that refuses from the start exercises a
 * different path than the one that matters.
 *
 * Every entry point that can ask the system for memory goes through this —
 * cdin_realloc included. A realloc that skipped it made the growth path, which
 * is where nearly every node and cache entry is born, the one place where
 * running out of memory could not be tested at all.
 *
 * n = 0 refuses the very next allocation, which is the "out of memory from
 * the first call" case. Disarming is its own call rather than a magic value,
 * precisely so that this stays reachable. */

/* Arm: allow `n` more allocations, refuse every allocation after that —
 * including ones made by the code that is reacting to the refusals. That last
 * part is deliberate: a test that walks a splice expects every one of its
 * allocations refused, and a counter that stopped at the first would under
 * count what the code under test actually faced.
 *
 * Resets the refusal counter. Because disabling also resets it, read
 * cdin_alloc_failures() before calling cdin_alloc_fail_disable().
 */
void cdin_alloc_fail_after(unsigned long n);

/* Disarm, and reset the refusal counter. Puts the injector back exactly as a
 * fresh process would find it, so a test can assert a clean count after
 * disabling without having to know what ran before it. */
void cdin_alloc_fail_disable(void);

/* Whether injection is armed, and how many allocations remain allowed. */
int cdin_alloc_fail_is_armed(void);
unsigned long cdin_alloc_fail_after_get(void);

/* Number of allocations refused since the last arm. A test asserts this is
 * non-zero to prove injection was actually exercised rather than silently
 * inert — a NULL return on its own does not distinguish "refused" from
 * "refused for some other reason". */
unsigned long cdin_alloc_failures(void);

/* ── misuse counters ────────────────────────────────────────────────────
 *
 * Frees and reallocs refused because the pointer was not ours or was already
 * released, and blocks whose guard bytes were found clobbered. Monotonic, so
 * a test takes a before/after difference. Guard violations are only counted in
 * a debug build (see cdin_mem_debug_enabled). */
size_t cdin_mem_bad_frees(void);
size_t cdin_mem_guard_violations(void);

/* ── build configuration, so a test can adapt rather than assume ────────
 *
 * Whether this build has the live-block registry and the guard bytes. A test
 * for guard bytes has to be able to ask: compiled without them, the case must
 * report itself as not applicable rather than passing vacuously, which is the
 * failure mode a silently-inert test has. */
int cdin_mem_debug_enabled(void);

/* How many blocks are live right now. Distinct from cdin_mem_leak_report, which
 * prints: a reporting path that also wrote to the log would make `core:memory`
 * spam the log it is reporting on, and would turn a build without the registry
 * into a diagnostic on every call. Returns 0 in a build with no registry, which
 * is why it is paired with cdin_mem_debug_enabled. */
size_t cdin_mem_live_blocks(void);

/* ── leak report ────────────────────────────────────────────────────────
 *
 * Prints every live block with its subsystem and size to the logger, and
 * returns the number of blocks still allocated. main() calls it before exit;
 * the test runner calls it after every case. Returns the count rather than
 * only printing, so "0" is an assertion and not a thing to eyeball.
 *
 * Only meaningful in a build with CDIN_ALLOC_DEBUG (see alloc.c): without the
 * registry there is nothing to walk. It returns 0 there rather than pretending
 * to have checked. */
size_t cdin_mem_leak_report(void);

/* Returns every block held in the debug free-quarantine to the system. Called
 * by cdin_mem_leak_report; exposed so a test can end with nothing held. A no-op
 * in a release build. */
void cdin_mem_quarantine_drain(void);

#endif /* CDIN_BASE_ALLOC_H */
