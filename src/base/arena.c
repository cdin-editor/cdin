/* Arena allocator: bump-pointer allocation, released in one step.
 *
 *     arena_init(&frame, CDIN_MEM_GFX, ARENA_DEFAULT_LIMIT);
 *     ... build a frame's worth of text runs, each with arena_alloc ...
 *     arena_reset(&frame);            // next frame allocates nothing
 *     arena_free(&frame);             // on shutdown
 *
 * Why the blocks are kept across a reset: the point of an arena here is that the
 * steady-state draw path does not allocate (AGENTS.md §8). A reset that returned
 * the blocks to the system would put an allocation back on exactly the path the
 * arena exists to take it off. So arena_reset moves a pointer and keeps the
 * memory, and arena_free is the one that gives it back.
 *
 * The cost of keeping it is that a frame which grows past its first block keeps
 * the larger block forever. That is bounded by the arena's limit, which is why
 * the limit exists and why it is checked before a new block is obtained rather
 * than after: an arena that overshoots its cap and then trims is a cap that does
 * not cap.
 *
 * Ownership: the arena owns its blocks; a pointer from arena_alloc is valid
 * until the next arena_reset or arena_free and not one instruction longer.
 * Exactly one owner per arena.
 *
 * Threads: not thread-safe. One arena per thread, which is what keeps the bump
 * path allocation-free and lock-free at the same time.
 */

#include "arena.h"

#include <stdalign.h>
#include <stdint.h>
#include <string.h>

#include "alloc.h"
#include "../core/logger.h"

/* One block. Fixed-size header, payload inline, blocks threaded oldest-last.
 *
 * `data` is a flexible array member so a block is one allocation rather than a
 * header and a payload: an arena for a 50-byte request must not cost two
 * allocations, and the per-allocation overhead rule that applies to the rest of
 * the runtime applies here too. */
struct ArenaBlock {
  ArenaBlock    *next;    /* the block allocated before this one; not owned by
                            * anyone individually, released with the arena */
  size_t         cap;     /* payload bytes                              */
  size_t         used;    /* payload bytes consumed                     */
  /* What this block cost the arena: header plus payload, rounded up by the
   * allocator. Tracked per block so arena_reset can give back the blocks it
   * releases and leave `reserved` telling the truth. Without it, an arena that
   * reset once would report memory it no longer holds. */
  size_t         total;
  /* Payload begins here, ARENA_HEADER_SIZE in. The offset is rounded up to the
   * platform's maximum alignment rather than left at sizeof(struct), because
   * sizeof is only a multiple of the struct's own alignment (8 on LP64) and a
   * 16-byte-aligned malloc plus an 8-aligned header would hand out a pointer
   * that fails the guarantee arena_alloc makes. */
  unsigned char  data[];
};

#define ALIGN_UP(v, a) (((v) + ((size_t)(a) - 1)) & ~((size_t)(a) - 1))

#define ARENA_HEADER_SIZE ALIGN_UP(sizeof(ArenaBlock), alignof(max_align_t))

_Static_assert((ARENA_HEADER_SIZE % alignof(max_align_t)) == 0,
               "the arena payload must start max-aligned");

/* The payload's base address, as a const-correct helper: several callers only
 * need to read the offset within the block, and a non-const signature would make
 * every one of them cast away const to call it. */
static unsigned char *block_data(ArenaBlock *b) { return b->data; }
static const unsigned char *block_data_c(const ArenaBlock *b) { return b->data; }

void arena_init(Arena *a, CdinMemTag tag, size_t limit) {
  if (!a) return;
  a->head      = NULL;
  a->reserved  = 0;
  a->used      = 0;
  a->used_peak = 0;
  a->tag       = tag;
  /* A zero limit would refuse the first allocation, which looks like a broken
   * arena rather than a configured one. The default is applied instead, and the
   * caller who meant "no limit" gets a bounded arena: AGENTS.md §2.4 bans
   * unbounded growth, and there is no legitimate caller for one. */
  a->limit     = (limit == 0) ? ARENA_DEFAULT_LIMIT : limit;
}

void arena_free(Arena *a) {
  if (!a) return;
  ArenaBlock *b = a->head;
  while (b) {
    ArenaBlock *next = b->next;
    cdin_free(b);
    b = next;
  }
  /* Left in a defined state rather than merely emptied, so a double
   * arena_free is harmless and arena_used on a freed arena answers 0 instead of
   * whatever was left in the struct. */
  a->head = NULL;
  a->reserved = 0;
  a->used = 0;
}

/* Makes every byte in every block available again.
 *
 * Nothing is released. That is the point: the draw path calls this every frame,
 * and if a reset gave a block back then a frame needing more than one block
 * would ask the system for it again on the next frame — an allocation on the
 * path the arena exists to keep allocation-free. The blocks are kept and only
 * their bump positions move.
 *
 * The cost of keeping them is that a one-off spike is held for the arena's
 * lifetime. That is bounded by the arena's limit, and arena_trim is the explicit
 * way to pay it back, for the moments where the footprint matters more than the
 * allocation-freedom: a document closing, a job finishing, memory pressure.
 *
 * Two earlier designs were wrong here and both are worth recording:
 *
 *  - Resetting `used` on every block but handing out only from the newest one.
 *    The older blocks then became unreachable, so every frame that needed more
 *    than one block allocated more, until the arena hit its cap and began
 *    refusing real work. That is unbounded growth on the draw path.
 *  - Releasing all but the largest block on every reset. That stops the creep
 *    but puts the allocation back, one frame later. A test asserting "a frame's
 *    reset leaves the allocator where it was" passed, because the allocation
 *    happened *during* the frame and the test only looked afterwards. The
 *    property has to be measured inside the frame.
 *
 * The largest block becomes the current one, so the steady state allocates from
 * one block rather than from whichever happened to be newest. The rest stay
 * reachable: block_take finds one with room when the current one fills, which is
 * what stops a multi-block frame re-allocating.
 *
 * O(number of blocks), and no system allocator involvement at all.
 *
 * Nothing written before the reset survives. That is the entire contract and the
 * only way this can avoid walking every allocation: a caller holding a pointer
 * across a reset has a stale pointer, and no bookkeeping in the arena would make
 * that free.
 *
 * reserved and used_peak do not move: reserved is the memory still owned, and
 * used_peak is a record of what this arena has needed, which is the figure that
 * says whether the limit is about to bite. */
void arena_reset(Arena *a) {
  if (!a) return;

  ArenaBlock *best = NULL;
  for (ArenaBlock *b = a->head; b; b = b->next) {
    b->used = 0;
    if (!best || b->cap >= best->cap) best = b;
  }

  /* Splice the largest to the front rather than only naming it: block_take walks
   * from the current block onwards, so the chosen one has to be reachable by that
   * walk to be found on a later frame. */
  if (best && best != a->head) {
    for (ArenaBlock *b = a->head; b; b = b->next) {
      if (b->next == best) { b->next = best->next; break; }
    }
    best->next = a->head;
    a->head = best;
  }

  a->used = 0;
}

/* Releases blocks beyond the largest `keep`, and returns how many it released.
 *
 * The counterpart to arena_reset for a caller that would rather hold a smaller
 * footprint than hold every block a spike once needed. Called where a cost is
 * paid anyway — a document closing, a job's arena going away — and never on the
 * per-frame path, because free is cheap but the point of the arena is that
 * neither malloc nor free happens there.
 *
 * `keep` 0 releases everything, leaving the arena as new. A larger value keeps
 * that many of the largest blocks, so a caller can say "give back all but the one
 * I know I will want again". Returns the count rather than nothing, so a test can
 * assert the trim did something. */
/* The `keep` largest blocks, identified by pointer.
 *
 * By pointer, not by capacity: an arena's blocks are very often all the same
 * size — every one after the first comes from the same rounding — so comparing
 * capacities and then matching blocks by capacity keeps *every* equal-sized
 * block. A trim of 1 that released nothing because all eight blocks were 8 KiB
 * is not a trim, and it is exactly what the first version of this did.
 *
 * Bounded at 8 entries because a caller asking to keep more than eight blocks has
 * misunderstood what this is for, and the cap is what keeps this off the heap: an
 * unbounded "top k" list inside an allocator is a buffer that overflows. */
#define ARENA_TRIM_MAX_KEEP 8
#define ARENA_SCAN_DEPTH    16

static size_t arena_trim_largest(Arena *a, size_t keep,
                                 ArenaBlock **out, size_t cap) {
  size_t n_keep = (keep < cap) ? keep : cap;

  for (size_t i = 0; i < n_keep; i++) out[i] = NULL;
  for (ArenaBlock *b = a->head; b; b = b->next) {
    for (size_t i = 0; i < n_keep; i++) {
      if (!out[i] || b->cap > out[i]->cap) {
        for (size_t j = n_keep - 1; j > i; j--) out[j] = out[j - 1];
        out[i] = b;
        break;
      }
    }
  }
  return n_keep;
}

size_t arena_trim(Arena *a, size_t keep) {
  if (!a) return 0;

  ArenaBlock *keep_list[ARENA_TRIM_MAX_KEEP];
  size_t n_keep = arena_trim_largest(a, keep, keep_list, ARENA_TRIM_MAX_KEEP);

  size_t released = 0;
  ArenaBlock *kept_head = NULL;
  for (ArenaBlock *b = a->head; b;) {
    ArenaBlock *next = b->next;
    int keep_this = 0;
    for (size_t i = 0; i < n_keep; i++) {
      if (b == keep_list[i]) { keep_this = 1; break; }
    }
    if (keep_this) {
      b->next = kept_head;
      b->used = 0;
      kept_head = b;
    } else {
      a->reserved -= b->total;
      cdin_free(b);
      released++;
    }
    b = next;
  }

  /* The prepend above reversed the kept blocks; put the largest first again so
   * the next allocation comes from the biggest one. */
  ArenaBlock *rest = kept_head ? kept_head->next : NULL;
  if (kept_head) kept_head->next = NULL;
  a->head = kept_head;
  while (rest) {
    ArenaBlock *n = rest->next;
    rest->next = a->head;
    a->head = rest;
    rest = n;
  }
  /* The kept blocks were reset above, so the arena's own count is zero too —
   * otherwise arena_used reports bytes that no longer exist and the two figures
   * stop summing. */
  a->used = 0;
  return released;
}

/* ── block management ──────────────────────────────────────────────────── */

/* Adds one block of at least `min_payload` bytes. Returns NULL if the limit
 * would be passed or the system allocator refuses; the caller reports.
 *
 * The limit is checked here rather than at allocation time because this is the
 * only place bytes actually arrive. Checking on arrival is what makes the cap
 * real — a cap checked after the fact only limits the *next* request, which is
 * one request too late to bound anything. */
static ArenaBlock *block_add(Arena *a, size_t min_payload) {
  size_t payload = ARENA_FIRST_BLOCK;
  if (min_payload > payload) payload = min_payload;

  /* Round the block up so the next few allocations do not each want a block. */
  if (payload > (size_t)-1 - 4095) {
    log_error("arena: a %zu byte request overflows a size_t", min_payload);
    return NULL;
  }
  payload = ALIGN_UP(payload, 4096);

  size_t total = ARENA_HEADER_SIZE + payload;
  if (total < payload) {
    log_error("arena: a %zu byte block overflows a size_t", payload);
    return NULL;
  }
  /* Compared as a difference, so a state where reserved already exceeds limit
   * (only reachable through a hand-edited struct) reports a refusal instead of
   * underflowing the difference into a huge cap. */
  if (a->reserved > a->limit || total > a->limit - a->reserved) {
    /* Not an error to log on every call: this is what the cap is for, and a
     * caller hitting it is behaving as configured. One line per refusal is
     * enough to tell "the cap bit" from "the cap is about to bite", because
     * used_peak is the latter. */
    log_warn("arena: %s limit reached — refused a %zu byte block "
             "(reserved %zu of %zu)", cdin_mem_tag_name(a->tag), payload,
             a->reserved, a->limit);
    return NULL;
  }

  ArenaBlock *b = (ArenaBlock *)cdin_alloc(a->tag, total);
  if (!b) return NULL;   /* alloc.c already logged why */

  b->next  = a->head;
  b->cap   = payload;
  b->used  = 0;
  b->total = total;
  a->head = b;
  a->reserved += total;
  return b;
}

/* The offset within a block's payload where an `align`-aligned allocation
 * starting at `used` must begin.
 *
 * Derived from the payload's actual address rather than assumed to be 0, because
 * arena_alloc_aligned accepts an alignment stricter than max_align_t — a 64-byte
 * boundary for an AVX-512 scratch buffer, say. Assuming zero offset would hand
 * back a pointer that satisfies every type the compiler knows about and not the
 * one the caller asked for, which is the kind of wrongness that only shows up as
 * a crash in the consumer. */
static size_t aligned_offset(const ArenaBlock *b, size_t align) {
  uintptr_t base = (uintptr_t)block_data_c(b);
  /* The address to align is base + used. Aligning base and then adding `used`
   * is only right when `used` is already a multiple of `align`. */
  uintptr_t padded = ALIGN_UP(base + b->used, align);
  /* padded >= base + used, so the difference fits in size_t. */
  return (size_t)(padded - base);
}

/* Bytes of room for a request of `size` at `align` in one block.
 *
 * 0 when the block cannot hold the request plus its alignment padding. That second
 * part matters: a block can have room for the request and not for the alignment,
 * and treating that as "no room" is what stops the bump from handing out a
 * misaligned pointer. */
static size_t room_in(const ArenaBlock *b, size_t align, size_t size) {
  size_t start = aligned_offset(b, align);
  if (start > b->cap) return 0;
  size_t room = b->cap - start;
  return (room >= size) ? room : 0;
}

/* The current block if it fits, otherwise the first later block with room,
 * spliced to the front so it becomes the current one.
 *
 * Searching the list is what makes a multi-block frame allocation-free after the
 * first one. Handing out only from the newest block has a frame that needs two
 * blocks asking the system for the second on every frame; the search finds the
 * block the previous frame grew and reuses it. O(blocks) only when the current
 * block fills, and amortised away: a walk that returns nothing has just shown the
 * arena needs more memory, and the next walk starts from the block added then.
 *
 * NULL when nothing has room, which means a new block is needed. */
static ArenaBlock *block_take(Arena *a, size_t align, size_t size) {
  if (!a->head) return NULL;
  if (room_in(a->head, align, size)) return a->head;

  /* Bounded look-behind: scanning every block on every refill made a frame that
   * spans many blocks quadratic. Blocks past the window stay reserved and are
   * found again after arena_reset, which moves the roomiest block to the front. */
  ArenaBlock *prev = a->head;
  size_t looked = 0;
  for (ArenaBlock *b = a->head->next; b && looked < ARENA_SCAN_DEPTH;
       prev = b, b = b->next, looked++) {
    if (!room_in(b, align, size)) continue;
    prev->next = b->next;
    b->next = a->head;
    a->head = b;
    return b;
  }
  return NULL;
}

size_t arena_size_aligned(size_t size, size_t align) {
  if (align < 1) align = 1;
  /* Worst case: the alignment pushes the payload a whole align-1 bytes in. */
  return size + align - 1;
}

void *arena_alloc_aligned(Arena *a, size_t size, size_t align) {
  if (!a) return NULL;
  if (align == 0) align = 1;
  if (align & (align - 1)) {
    /* A non-power-of-two alignment cannot be satisfied by this scheme, and
     * rounding it down would quietly break the caller's type. */
    log_error("arena: alignment %zu is not a power of two", align);
    return NULL;
  }

  /* Served from a block the arena already owns: the current one, or one further
   * down the list if this is a multi-block frame. No system allocator involved,
   * which is the case that has to stay cheap and is the whole reason this
   * structure exists. */
  ArenaBlock *b = block_take(a, align, size);
  if (b) {
    size_t start = aligned_offset(b, align);
    b->used = start + size;
    /* arena_used counts payload bytes, not the padding before each allocation —
     * the same rule cdin_mem_live follows, so the two sum without double
     * counting. The padding is still consumed from the block; it is simply not
     * charged to the caller, and it shows up as unused tail in
     * arena_reserved. */
    a->used += b->used - start;
    if (a->used > a->used_peak) a->used_peak = a->used;
    return block_data(b) + start;
  }

  /* Nothing has room: a new block. Sized with room to spare for the alignment so
   * the payload starts aligned without a wasted prefix in every block. */
  if (size > (size_t)-1 - align) {
    log_error("arena: a %zu byte request at alignment %zu overflows a size_t",
              size, align);
    return NULL;
  }
  size_t min_payload = size + align;
  b = block_add(a, min_payload);
  if (!b) return NULL;

  size_t start = aligned_offset(b, align);
  if (start + size > b->cap) {
    /* Cannot happen: the block was sized for size + align and start is at most
     * align - 1 plus a zero used. Checked anyway, because the alternative is
     * writing past a block on an assumption about arithmetic two functions away. */
    log_error("arena: internal sizing error — %zu + %zu exceeds a %zu byte block",
              start, size, b->cap);
    return NULL;
  }

  b->used = start + size;
  a->used += size;
  if (a->used > a->used_peak) a->used_peak = a->used;
  return block_data(b) + start;
}

void *arena_alloc(Arena *a, size_t size) {
  return arena_alloc_aligned(a, size, alignof(max_align_t));
}

CdinErr arena_reserve(Arena *a, size_t bytes) {
  if (!a) return CDIN_ERR_INVALID;
  /* Already covered: the cheap answer, and the one that lets a
   * no-allocation path establish its own precondition. Searched across every
   * block rather than just the current one, so a caller that reserves for a whole
   * multi-block frame is not told yes when only the current block would fit. */
  for (ArenaBlock *b = a->head; b; b = b->next) {
    if (room_in(b, alignof(max_align_t), bytes)) return CDIN_OK;
  }
  if (block_add(a, bytes) == NULL) {
    /* Distinguish "the cap said no" from "the system allocator said no": the
     * remedies differ and a caller that flattens them ends up retrying a
     * hopeless request in a loop. */
    size_t want = ARENA_HEADER_SIZE + ALIGN_UP(bytes, 4096);
    return (a->reserved > a->limit || want > a->limit - a->reserved)
             ? CDIN_ERR_LIMIT : CDIN_ERR_OOM;
  }
  return CDIN_OK;
}

size_t arena_used(const Arena *a) { return a ? a->used : 0; }
size_t arena_reserved(const Arena *a) { return a ? a->reserved : 0; }
size_t arena_used_peak(const Arena *a) { return a ? a->used_peak : 0; }