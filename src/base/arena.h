/* Arena allocator: one allocation for many, released at once.
 *
 * What it is for. AGENTS.md §8 forbids allocating in the steady-state draw path
 * and on the per-keystroke path. That is only achievable if the allocations are
 * already there, and "already there" needs somewhere to live that is not the
 * heap and not the stack. That somewhere is an arena: one block, handed out by
 * bumping a pointer, thrown away in one step.
 *
 * What it is not for. It is not a general allocator and must not be used as one:
 * nothing can free an individual allocation, so a loop that puts something in an
 * arena and then keeps going grows the arena until the process dies. If code
 * needs to free one thing, it needs cdin_alloc.
 *
 * The type of the pointer an arena hands back is deliberately unspecified —
 * callers get a void *, so nothing can accidentally be passed to free() and no
 * caller can reach into another allocation. Arena memory is char-aligned, which
 * is enough for a rope node or a token record; a caller that needs a stricter
 * alignment must over-allocate and round up itself, and the two functions for
 * that are named arena_alloc_aligned and arena_size_aligned so the cost is
 * visible at the call site rather than buried.
 *
 * Every arena carries a hard cap. AGENTS.md §2.4 bans unbounded growth, and an
 * arena that is fed by a loop over a file is the easiest place in the codebase
 * to have one: it never returns an error, so a runaway loop looks exactly like a
 * healthy one until the process dies. The cap turns that into a refusal at a
 * size the caller can recover from, and the refusal is reported rather than
 * swallowed.
 *
 * Ownership: the arena owns its blocks. A pointer from arena_alloc is valid
 * until the next arena_reset or arena_free — not merely until "the caller is
 * done", because there is no way for the arena to know. Exactly one owner per
 * arena; the type is a plain struct so it can live on the stack or inside
 * another struct, and the caller must not copy one after first use.
 *
 * Threads: not thread-safe, and not meant to be. An arena belongs to the thread
 * that allocates from it; that is what makes the bump-pointer path allocation-
 * free. Phase 3's worker pool gets one arena per worker rather than a lock.
 */

#ifndef CDIN_BASE_ARENA_H
#define CDIN_BASE_ARENA_H

#include <stddef.h>

#include "alloc.h"
#include "error.h"

/* First block size. Small enough that a caller's first stack frame's worth of
 * scratch does not ask the system for a page, large enough that a few dozen
 * small allocations come from one block. */
#define ARENA_FIRST_BLOCK   4096u

/* Ceiling on the bytes one arena will hold across all its blocks. The default is
 * deliberately modest: an arena that is a per-frame or per-command scratch pool
 * has no business exceeding a few hundred KiB, and a cap that is too generous
 * is not a cap. A caller that genuinely needs more passes its own — and then
 * says so in the code, which is the point. */
#define ARENA_DEFAULT_LIMIT (4u * 1024u * 1024u)

typedef struct ArenaBlock ArenaBlock;

typedef struct {
  ArenaBlock *head;        /* newest block; allocations come from here       */
  size_t      limit;       /* bytes across all blocks, blocks included       */
  CdinMemTag  tag;        /* subsystem these bytes are accounted to          */
  /* Bytes obtained from the system allocator, blocks and block headers
   * included. Kept separately from the offset arithmetic below so that the
   * accounting includes what the caller never asked for, which is the only
   * figure comparable with the allocator's own numbers. */
  size_t      reserved;
  /* Handed out since the last arena_reset. Zeroed by a reset, unlike
   * used_peak. */
  size_t      used;
  /* Consumed and then reset: the high-water mark of the bump pointer. Not the
   * same as the largest live amount — it counts bytes handed out even after a
   * reset, which is the number that tells you whether the cap is close. Never
   * decreases, so it is a peak and not a level. */
  size_t      used_peak;
} Arena;

/* An arena that has been reset is as good as new, and its reserved blocks are
 * kept for reuse — that reuse is the whole point, since the steady-state draw
 * path must not allocate. `tag` is the subsystem the bytes are accounted to;
 * pass CDIN_MEM_GFX for a frame's scratch, CDIN_MEM_BASE if unsure. */
void arena_init(Arena *a, CdinMemTag tag, size_t limit);

/* Releases every block. The arena is unusable afterwards without another
 * arena_init, and saying so here is why there is no arena_close: one name for
 * one lifetime, so a reader cannot wonder whether "reset" also frees. */
void arena_free(Arena *a);

/* Hands back `size` bytes, or NULL if the arena's limit is reached. The pointer
 * is aligned for any scalar type; use arena_alloc_aligned for anything stricter.
 *
 * A NULL return is not exceptional: an arena at its cap is a normal outcome of
 * feeding it too much, and the caller is expected to either flush what it has
 * already built or give up cleanly. */
void *arena_alloc(Arena *a, size_t size);

/* As arena_alloc, with the payload aligned to `align` (a power of two). The
 * alignment padding is counted against the limit, so a caller that asks for a
 * max-aligned block is charged for the padding rather than getting it free. */
void *arena_alloc_aligned(Arena *a, size_t size, size_t align);

/* The bytes a call to arena_alloc_aligned would consume for `size` at `align`,
 * including padding. Lets a caller check against the limit before allocating,
 * which matters when the answer decides whether to do the work at all. */
size_t arena_size_aligned(size_t size, size_t align);

/* Makes every byte in every block available again. Nothing is released, and that
 * is the point: the draw path calls this every frame, and a reset that gave a
 * block back would have a multi-block frame asking the system for it again on the
 * next frame. Blocks are found by search, not by always taking the newest, so a
 * frame that needs more than one block reuses the blocks the last one grew.
 *
 * The cost is that a one-off spike is held for the arena's lifetime, bounded by
 * the limit. arena_trim is the explicit way to give it back.
 *
 * O(number of blocks), and no system allocator involvement.
 *
 * Nothing written before a reset survives it. That is the whole contract and the
 * only way a reset can avoid walking every allocation: a caller holding a pointer
 * across a reset has a stale pointer, and no bookkeeping in the arena would make
 * that free.
 *
 * arena_used drops to zero. arena_reserved and arena_used_peak do not move —
 * reserved is the memory still owned, and used_peak is a record of what this
 * arena has needed, which is the figure that says whether the limit is about to
 * bite. */
void arena_reset(Arena *a);

/* Releases blocks beyond the largest `keep`, and returns how many it released.
 *
 * For a caller that would rather hold a smaller footprint than hold every block a
 * spike once needed. Called where a cost is paid anyway — a document closing, a
 * job's arena going away — and never on the per-frame path.
 *
 * `keep` 0 releases everything, leaving the arena as new; the usual value is 1,
 * for "give back all but the block I will want again". Kept blocks keep their
 * memory but lose their contents, exactly as a reset would. Returns the count so
 * a caller or a test can tell that it did something.
 *
 * Capped at keeping 8 blocks: a caller asking for more has misunderstood what
 * this is for, and the cap is what keeps this function's bookkeeping off the
 * heap. */
size_t arena_trim(Arena *a, size_t keep);

/* Reserves capacity for at least `bytes` without handing any of it out, so a
 * later sequence of small allocations cannot fail partway through. Cheap when
 * the current blocks already fit — returns CDIN_OK and allocates nothing — which
 * is what makes it usable on a path that must not allocate, to ensure it does not
 * have to. */
CdinErr arena_reserve(Arena *a, size_t bytes);

/* Bytes handed out since the last arena_reset, not counting block overhead and
 * not counting the padding between aligned allocations. Payload bytes, so this
 * sums with cdin_mem_live's "live" figures rather than double-counting the
 * headers the allocator also charged for.
 *
 * The gap between this and arena_reserved is the arena's real overhead, and it
 * is mostly the unused tail of the current block — which is why the two numbers
 * are both reported rather than one derived from the other. */
size_t arena_used(const Arena *a);

/* Bytes obtained from the allocator, blocks included. Compare against
 * cdin_mem_live(a->tag) when asking what an arena cost — this number alone
 * understates it, because it excludes the block headers. */
size_t arena_reserved(const Arena *a);

/* The largest arena_used has reached. Never decreases; a value above 90% of the
 * limit is the signal that the cap is about to refuse real work. */
size_t arena_used_peak(const Arena *a);

#endif /* CDIN_BASE_ARENA_H */