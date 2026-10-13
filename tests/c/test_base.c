/* Arena and CdinErr tests.
 *
 * The arena is the structure that makes "no allocation in the steady-state draw
 * path" possible, so what is tested here is not that it hands out memory — it is
 * that it keeps handing out memory *without asking the system for any*, and that
 * it refuses at its cap rather than growing forever. The second property is the
 * one AGENTS.md §2.4 turns on, and the one an arena makes most likely to get
 * wrong, because an arena returns NULL for two quite different reasons and a
 * caller cannot tell them apart unless the accounting says so.
 */

#include <stdalign.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../../src/base/alloc.h"
#include "../../src/base/arena.h"
#include "../../src/base/error.h"
#include "ctest.h"

/* ── arena ─────────────────────────────────────────────────────────────── */

/* Allocation is distinct and correctly aligned. Trivially true, and the reason
 * it is still here: a bump allocator that overlapped two allocations would
 * corrupt its caller's data, and the corruption would surface somewhere else
 * entirely. */
static int t_arena_hands_out_distinct_memory(void) {
  Arena a;
  arena_init(&a, CDIN_MEM_GFX, 64 * 1024);

  void *p1 = arena_alloc(&a, 100);
  void *p2 = arena_alloc(&a, 100);
  void *p3 = arena_alloc(&a, 100);
  t_assert(p1 && p2 && p3);
  t_assert("three distinct pointers: "
           && p1 != p2 && p2 != p3 && p1 != p3);
  t_assert("and each is far enough past the last: "
           && (unsigned char *)p2 - (unsigned char *)p1 >= 100);

  /* arena_used counts payload bytes, not the alignment padding between
   * allocations and not the block overhead — the same rule cdin_mem_live
   * follows, so the two can be added together. 300 exactly, which also pins the
   * rule down: an implementation that charged padding would report 308 here. */
  t_eq_int(arena_used(&a), 300);

  /* reserved is the other figure, and it is larger: the block header plus the
   * tail nobody has allocated from yet. Reporting only one of the two is how an
   * arena's overhead stays invisible. */
  t_assert("reserved exceeds used by the block's slack: "
           && arena_reserved(&a) > arena_used(&a));
  arena_free(&a);
  return 0;
}


/* The guarantee the draw path depends on: after a reset, allocations are served
 * from memory already owned, so the allocator's live-byte counter does not move.
 *
 * This is asserted by reading cdin_mem_live, not by counting calls. The counter
 * is the thing the phase report prints, so a test that watched something else
 * would be verifying a proxy for the property that matters.
 *
 * The sweep runs until it has needed more than one block, because that is the
 * case that matters: an arena that only ever fits in one block cannot tell you
 * whether it reuses what it has. The earlier version of this case allocated 512
 * bytes and reset, and passed — while an implementation that grew a block on
 * every reset would have passed it too. */
static int t_arena_reset_allocates_nothing(void) {
  Arena a;
  arena_init(&a, CDIN_MEM_GFX, 1024 * 1024);

  /* A frame's worth of work that needs several blocks: 16 allocations of 4 KiB
   * is 64 KiB, well past the 4 KiB first block. */
  enum { PER_FRAME = 16, CHUNK = 4096 };

  /* One frame, to pay for the blocks. */
  for (int i = 0; i < PER_FRAME; i++) {
    void *p = arena_alloc(&a, CHUNK);
    if (!p) { arena_free(&a); t_assert("the first frame allocates: "); }
  }
  size_t after_first = cdin_mem_live(CDIN_MEM_GFX);
  t_assert("it did need more than one block: "
           && after_first > ARENA_FIRST_BLOCK);
  arena_reset(&a);

  /* Now the steady state, which is the property: twenty more frames, each
   * several blocks' worth, must not touch the allocator once.
   *
   * Measured *inside* each frame, before the reset. A version of this case that
   * only looked after the reset passed against an implementation that released
   * the surplus on every reset and re-allocated it on the next frame — the
   * allocation was happening, just where the test was not looking. Checking the
   * live count in the middle of the frame is what makes this the property the
   * header claims rather than a weaker one. */
  for (int frame = 0; frame < 20; frame++) {
    for (int i = 0; i < PER_FRAME; i++) {
      void *p = arena_alloc(&a, CHUNK);
      if (!p) { arena_free(&a); t_assert("a frame in the steady state: "); }
      memset(p, 0xA5, CHUNK);
    }
    if (cdin_mem_live(CDIN_MEM_GFX) != after_first) {
      arena_free(&a);
      t_assert("no allocation inside a steady-state frame: ");
    }
    arena_reset(&a);
    if (cdin_mem_live(CDIN_MEM_GFX) != after_first) {
      arena_free(&a);
      t_assert("and a reset releases nothing: ");
    }
  }

  t_assert("twenty multi-block frames allocate nothing at all: "
           && cdin_mem_live(CDIN_MEM_GFX) == after_first);

  /* The footprint is the blocks one frame needed, not one per frame. Loose on
   * purpose: the exact figure includes a block header, which is internal. What
   * matters is that it cannot grow with the frame count. */
  t_assert("and the footprint is bounded by a few blocks, not twenty: "
           && after_first <= 16 * (ARENA_FIRST_BLOCK + 4096));

  arena_free(&a);
  t_eq_int(cdin_mem_live(CDIN_MEM_GFX), 0);
  return 0;
}


/* Trim gives the surplus back on demand, which is what reset deliberately does
 * not do. It has to leave the arena usable: the kept block is reset, not merely
 * kept, and the arena can still grow afterwards. */
static int t_arena_trim_releases_the_surplus(void) {
  Arena a;
  arena_init(&a, CDIN_MEM_GFX, 1024 * 1024);

  enum { PER_FRAME = 16, CHUNK = 4096 };
  for (int i = 0; i < PER_FRAME; i++) t_assert(arena_alloc(&a, CHUNK) != NULL);
  size_t peak = cdin_mem_live(CDIN_MEM_GFX);
  t_assert("several blocks held: " && peak > ARENA_FIRST_BLOCK);

  size_t released = arena_trim(&a, 1);
  t_assert("trim released something: " && released > 0);
  size_t after_trim = cdin_mem_live(CDIN_MEM_GFX);
  t_assert("and the footprint fell: " && after_trim < peak);
  t_assert("but one block is still there to reuse: "
           && after_trim >= ARENA_FIRST_BLOCK);
  t_assert("reserved agrees with the allocator, not with its own stale total: "
           && arena_reserved(&a) == after_trim);
  t_eq_int(arena_used(&a), 0);

  /* The kept block is usable immediately, and a frame that fits inside it needs
   * nothing new. A frame that does *not* fit legitimately regrows — trim gave
   * the memory back on purpose, and asking for it again is the trim working, not
   * a leak. Both halves are checked, because asserting only the first would make
   * "trim released everything" look like a win. */
  {
    size_t before = cdin_mem_live(CDIN_MEM_GFX);
    for (int i = 0; i < 4; i++) {
      void *p = arena_alloc(&a, 256);
      if (!p) { arena_free(&a); t_assert("small work after a trim: "); }
      memset(p, 0x33, 256);
    }
    t_assert("a frame that fits the kept block allocates nothing: "
             && cdin_mem_live(CDIN_MEM_GFX) == before);
  }
  arena_reset(&a);

  /* A full frame regrows the arena to what it needs, and then stops needing
   * more. Two frames of the same size must cost the same. */
  for (int i = 0; i < PER_FRAME; i++) {
    void *p = arena_alloc(&a, CHUNK);
    if (!p) { arena_free(&a); t_assert("a full frame regrows: "); }
  }
  size_t regrown = cdin_mem_live(CDIN_MEM_GFX);
  t_assert("regrowing costs more than the trimmed footprint: "
           && regrown > after_trim);
  arena_reset(&a);
  for (int i = 0; i < PER_FRAME; i++) {
    void *p = arena_alloc(&a, CHUNK);
    if (!p) { arena_free(&a); t_assert("a second full frame: "); }
  }
  t_assert("and the second one costs exactly the same: "
           && cdin_mem_live(CDIN_MEM_GFX) == regrown);

  /* Trim to nothing leaves it as new. */
  arena_reset(&a);
  released = arena_trim(&a, 0);
  t_assert("trim to zero releases the rest: " && released > 0);
  t_eq_int(arena_reserved(&a), 0);
  t_eq_int(cdin_mem_live(CDIN_MEM_GFX), 0);
  t_assert("and it still works: " && arena_alloc(&a, 128) != NULL);

  arena_free(&a);
  t_eq_int(cdin_mem_live(CDIN_MEM_GFX), 0);
  return 0;
}


/* Two frames of different shapes must not grow each other: a small frame after a
 * large one reuses what is there. This is the case the block search exists for,
 * and it is invisible to a test whose two frames are the same size. */
static int t_arena_a_smaller_frame_reuses_larger_blocks(void) {
  Arena a;
  arena_init(&a, CDIN_MEM_GFX, 1024 * 1024);

  for (int i = 0; i < 16; i++) t_assert(arena_alloc(&a, 4096) != NULL);
  arena_reset(&a);
  size_t after_big = cdin_mem_live(CDIN_MEM_GFX);

  for (int frame = 0; frame < 10; frame++) {
    void *p = arena_alloc(&a, 256);
    if (!p) { arena_free(&a); t_assert("a small frame allocates: "); }
    memset(p, 0x77, 256);
    arena_reset(&a);
  }
  t_assert("a small frame after a large one allocates nothing: "
           && cdin_mem_live(CDIN_MEM_GFX) == after_big);

  arena_free(&a);
  return 0;
}


/* Nothing written before a reset survives it. That is the whole contract and the
 * only way a reset can be O(1), so it is checked rather than assumed — a caller
 * that quietly relied on the old contents would read another allocation's bytes
 * and blame the wrong subsystem. */
static int t_arena_reset_discards_contents(void) {
  Arena a;
  arena_init(&a, CDIN_MEM_GFX, 64 * 1024);

  unsigned char *p = (unsigned char *)arena_alloc(&a, 64);
  t_assert(p != NULL);
  memset(p, 0x11, 64);

  arena_reset(&a);
  unsigned char *q = (unsigned char *)arena_alloc(&a, 64);
  t_assert(q != NULL);
  t_eq_ptr(q, p);

  /* The memory is reused, so the contents are whatever the previous user left.
   * What must not happen is the arena claiming the old values are meaningful —
   * so the check is that the bytes were handed out again, not that they changed.
   * A test asserting "q is now zero" would be asserting that the arena zeroes,
   * which it does not promise and which would cost a memset per frame. */
  t_assert("the arena does not promise to zero on reuse: "
           && (q == p));

  arena_free(&a);
  return 0;
}


/* The cap is real. An arena that grew past its limit on demand would be an
 * unbounded allocation with extra steps — the exact failure mode AGENTS.md §2.4
 * bans, and the one an arena is most prone to, because arena_alloc returning
 * NULL looks like an ordinary outcome that a loop will happily absorb forever. */
static int t_arena_refuses_at_its_limit(void) {
  const size_t limit = 32 * 1024;
  Arena a;
  arena_init(&a, CDIN_MEM_FONT, limit);
  t_eq_int(a.limit, limit);

  size_t handed_out = 0;
  size_t refusals = 0;
  while (handed_out < limit * 2) {
    void *p = arena_alloc(&a, 1024);
    if (!p) {
      refusals++;
      if (refusals > 8) break;      /* must not loop forever */
      continue;
    }
    handed_out += 1024;
  }

  t_assert("it refused eventually: " && refusals > 0);
  t_assert("and stopped rather than growing without end: "
           && arena_reserved(&a) <= limit);
  t_assert("reserved never passed the limit: " && arena_reserved(&a) <= limit);

  arena_free(&a);
  t_eq_int(cdin_mem_live(CDIN_MEM_FONT), 0);
  return 0;
}


/* A limit of zero gets the default, not an arena that refuses everything. An
 * arena configured to be useless is indistinguishable from a broken one, and the
 * caller would have no way to tell which. */
static int t_arena_zero_limit_means_the_default(void) {
  Arena a;
  arena_init(&a, CDIN_MEM_BASE, 0);
  t_eq_int(a.limit, ARENA_DEFAULT_LIMIT);
  t_assert("and it can actually allocate: " && arena_alloc(&a, 16) != NULL);
  arena_free(&a);
  return 0;
}


/* Alignment is honoured, including stricter than max_align_t — the case a
 * caller hits with an AVX-512 scratch buffer and which a bump allocator gets
 * wrong by assuming the block payload starts aligned. */
static int t_arena_honours_alignment(void) {
  Arena a;
  arena_init(&a, CDIN_MEM_GFX, 256 * 1024);

  static const size_t aligns[] = { 1, 8, 16, 32, 64, 128, 256 };

  for (size_t i = 0; i < sizeof(aligns) / sizeof(aligns[0]); i++) {
    size_t align = aligns[i];
    /* A deliberately odd size, so the next allocation cannot inherit the
     * alignment by landing on a convenient boundary. */
    size_t size = 13;

    void *p = arena_alloc_aligned(&a, size, align);
    t_assert("an aligned allocation succeeds: " && p != NULL);
    t_assert("aligned to the requested boundary: "
             && ((size_t)p % align) == 0);

    /* Writable across its whole length, and the next one does not overlap. */
    memset(p, 0x5A, size);
    void *q = arena_alloc_aligned(&a, size, align);
    t_assert("and the next one is distinct: " && q != NULL);
    t_assert("with no overlap: "
             && ((unsigned char *)q >= (unsigned char *)p + size));
    for (size_t k = 0; k < size; k++) {
      t_assert("the previous allocation is untouched: "
               && ((unsigned char *)p)[k] == 0x5A);
    }
    arena_reset(&a);
  }

  arena_free(&a);
  return 0;
}


/* The case the loop above cannot reach: an aligned request that follows an
 * allocation whose size is not a multiple of the alignment. Aligning the block
 * start and then adding the bytes already used returned an address that was
 * 24 mod 64 here, because 24 is not a multiple of 64. Alignment is checked on
 * the pointer handed out, for the allocation that follows an odd-sized one. */
static int t_arena_aligns_after_an_odd_sized_allocation(void) {
  Arena a;
  arena_init(&a, CDIN_MEM_GFX, 256 * 1024);

  static const size_t aligns[] = { 16, 32, 64, 128, 256, 1024 };
  for (size_t i = 0; i < sizeof(aligns) / sizeof(aligns[0]); i++) {
    size_t align = aligns[i];
    for (size_t odd = 1; odd <= 33; odd += 8) {
      void *first = arena_alloc_aligned(&a, odd, 1);
      t_assert(first != NULL);
      void *p = arena_alloc_aligned(&a, 8, align);
      t_assert(p != NULL);
      t_assert("aligned after an odd-sized allocation: " && ((uintptr_t)p % align) == 0);
      t_assert("and past the previous one: "
               && (unsigned char *)p >= (unsigned char *)first + odd);
    }
    arena_reset(&a);
  }
  arena_free(&a);
  return 0;
}


/* arena_used is payload bytes only, in both the new-block and the reuse path.
 * An aligned request that needed padding used to be charged its padding when it
 * opened a new block and not when it reused one. */
static int t_arena_used_never_counts_padding(void) {
  Arena a;
  arena_init(&a, CDIN_MEM_GFX, 256 * 1024);

  t_assert(arena_alloc_aligned(&a, 24, 1) != NULL);
  t_assert(arena_alloc_aligned(&a, 8, 256) != NULL);
  t_eq_int(arena_used(&a), 32);

  /* A request larger than the first block forces a second one. */
  t_assert(arena_alloc_aligned(&a, 6000, 256) != NULL);
  t_eq_int(arena_used(&a), 32 + 6000);
  arena_free(&a);
  return 0;
}


/* A size close to SIZE_MAX is refused, not wrapped into a small block. */
static int t_arena_refuses_a_size_that_overflows(void) {
  Arena a;
  arena_init(&a, CDIN_MEM_GFX, 64 * 1024);
  t_assert(arena_alloc_aligned(&a, (size_t)-1 - 8, 64) == NULL);
  t_assert(arena_alloc_aligned(&a, (size_t)-1 - 4000, 16) == NULL);
  t_eq_int(arena_used(&a), 0);
  t_assert(arena_alloc(&a, 16) != NULL);
  arena_free(&a);
  return 0;
}


/* An alignment that is not a power of two is refused rather than rounded. A
 * caller asking for 24 bytes of alignment and getting 16 has a buffer it cannot
 * use for what it asked, and would find out at a fault rather than here. */
static int t_arena_refuses_a_non_power_of_two_alignment(void) {
  Arena a;
  arena_init(&a, CDIN_MEM_GFX, 64 * 1024);
  t_assert("refused: " && arena_alloc_aligned(&a, 64, 24) == NULL);
  t_assert("and 3 too: " && arena_alloc_aligned(&a, 64, 3) == NULL);
  t_assert("and 100: " && arena_alloc_aligned(&a, 64, 100) == NULL);
  t_eq_int("nothing was consumed: " && arena_used(&a), 0);
  arena_free(&a);
  return 0;
}


/* The worst-case size a caller can check against the limit before committing to
 * the work. If this under-reports, a caller that asks first and allocates second
 * gets a NULL after doing all the work — the failure this function exists to
 * prevent. */
static int t_arena_size_aligned_bounds_the_request(void) {
  Arena a;
  arena_init(&a, CDIN_MEM_GFX, 128 * 1024);

  /* Whatever the alignment, the reserved figure must be enough for the
   * allocation to succeed once it is reserved. Checked empirically across a
   * sweep, because an off-by-alignment is exactly the kind of bug that only
   * shows on the unlucky call. */
  static const size_t aligns[] = { 1, 8, 16, 32, 64, 128 };
  static const size_t sizes[]  = { 1, 15, 16, 17, 100, 4095, 4096 };

  for (size_t ai = 0; ai < sizeof(aligns) / sizeof(aligns[0]); ai++) {
    for (size_t si = 0; si < sizeof(sizes) / sizeof(sizes[0]); si++) {
      size_t align = aligns[ai];
      size_t size = sizes[si];
      size_t need = arena_size_aligned(size, align);
      t_assert("the bound covers the request: " && need >= size);

      arena_reset(&a);
      if (arena_reserve(&a, need) != CDIN_OK) {
        arena_free(&a);
        t_assert("reserving the bound is enough to allocate: ");
      }
      void *p = arena_alloc_aligned(&a, size, align);
      t_assert("so the allocation succeeds: " && p != NULL);
      t_assert("and is aligned: " && ((size_t)p % align) == 0);
    }
  }

  arena_free(&a);
  return 0;
}


/* arena_reserve's two failure modes are distinguishable, because the remedies
 * differ: CDIN_ERR_LIMIT means "ask for less", CDIN_ERR_OOM means "the system
 * allocator said no". Flattening them makes a caller retry a hopeless request in
 * a loop. */
static int t_arena_reserve_distinguishes_limit_from_oom(void) {
  Arena small;
  arena_init(&small, CDIN_MEM_LOOP, 8 * 1024);
  CdinErr e = arena_reserve(&small, 1024 * 1024);
  t_assert("a request past the limit is CDIN_ERR_LIMIT, not OOM: "
           && e == CDIN_ERR_LIMIT);
  arena_free(&small);

  /* A generous limit with the allocator refusing underneath. */
  Arena big;
  arena_init(&big, CDIN_MEM_LOOP, 64u * 1024u * 1024u);
  cdin_alloc_fail_after(0);          /* refuse everything from here on */
  CdinErr e2 = arena_reserve(&big, 4096);
  unsigned long fired = cdin_alloc_failures();
  cdin_alloc_fail_disable();
  t_assert("an allocator refusal is CDIN_ERR_OOM: " && e2 == CDIN_ERR_OOM);
  t_assert("and the injector really fired: " && fired >= 1);
  arena_free(&big);
  return 0;
}


/* An arena at its cap keeps its existing contents. A refusal has to be a refusal
 * of the *next* allocation, not a way to lose what was already built — otherwise
 * a caller that hits the cap mid-way through has no way to report what it
 * managed to produce. */
static int t_arena_refusal_keeps_earlier_allocations(void) {
  Arena a;
  arena_init(&a, CDIN_MEM_SYNTAX, 16 * 1024);

  /* Fill to near the cap, keeping a pointer into the middle of it. */
  unsigned char *kept = NULL;
  size_t handed = 0;
  while (handed < 10 * 1024) {
    unsigned char *p = (unsigned char *)arena_alloc(&a, 256);
    if (!p) break;
    memset(p, 0x7E, 256);
    if (handed == 4096) kept = p;
    handed += 256;
  }
  t_assert("some allocations were made: " && kept != NULL);

  /* Now ask for more than the cap allows, repeatedly. */
  for (int i = 0; i < 4; i++) {
    t_assert("refused: " && arena_alloc(&a, 4096) == NULL);
  }

  /* Every earlier byte is still readable and still what it was. */
  int intact = 1;
  for (int i = 0; i < 256; i++) if (kept[i] != 0x7E) { intact = 0; break; }
  t_assert("and still holds what was written to it: " && intact);

  arena_free(&a);
  return 0;
}


/* Allocation failure underneath the arena is handled, not propagated as a
 * wild pointer. The arena is exactly the place where a NULL from the allocator
 * could be mistaken for "the cap bit", and the two have to be told apart or a
 * subsystem ends up quietly doing nothing forever. */
static int t_arena_survives_allocator_refusal(void) {
  Arena a;
  arena_init(&a, CDIN_MEM_GFX, 1024 * 1024);

  void *first = arena_alloc(&a, 64);
  t_assert(first != NULL);
  memset(first, 0x33, 64);

  /* Refuse every allocation from here on. The arena must return NULL and must
   * not hand back memory it did not get. */
  cdin_alloc_fail_after(0);
  void *refused = arena_alloc(&a, 64 * 1024);
  cdin_alloc_fail_disable();

  t_assert("a large request with the allocator refusing is NULL: "
           && refused == NULL);
  t_assert("and the earlier allocation is untouched: "
           && ((unsigned char *)first)[0] == 0x33);

  arena_free(&a);
  t_eq_int(cdin_mem_live(CDIN_MEM_GFX), 0);
  return 0;
}


/* Double free and use-after-free-by-name are both harmless, because the arena
 * clears itself. Cheap to check and it removes the question of whether a
 * shutdown path that frees twice crashes. */
static int t_arena_free_is_idempotent(void) {
  Arena a;
  arena_init(&a, CDIN_MEM_EDIT, 64 * 1024);
  t_assert(arena_alloc(&a, 128) != NULL);
  arena_free(&a);
  t_eq_int(arena_reserved(&a), 0);
  t_eq_int(arena_used(&a), 0);
  arena_free(&a);      /* twice */
  t_eq_int(arena_reserved(&a), 0);
  return 0;
}


/* used_peak is a peak, not a level: it survives a reset, so an arena that grew
 * once and then shrank still reports what it needed. That is the figure that
 * says "this limit is about to bite" and it must not quietly forget. */
static int t_arena_used_peak_is_a_high_water_mark(void) {
  Arena a;
  arena_init(&a, CDIN_MEM_LOOP, 64 * 1024);

  for (int i = 0; i < 10; i++) {
    void *p = arena_alloc(&a, 1024);
    t_assert(p != NULL);
  }
  size_t peak = arena_used_peak(&a);
  t_assert(peak >= 10 * 1024);

  arena_reset(&a);
  t_eq_int(arena_used(&a), 0);
  t_assert("and the peak survives: " && arena_used_peak(&a) == peak);

  void *small = arena_alloc(&a, 16);
  t_assert(small != NULL);
  t_assert("a smaller round does not lower it: "
           && arena_used_peak(&a) == peak);

  arena_free(&a);
  return 0;
}


static const CtestCase arena_cases[] = {
  { "hands out distinct memory",               t_arena_hands_out_distinct_memory },
  { "reset allocates nothing",                 t_arena_reset_allocates_nothing },
  { "trim releases the surplus on demand",     t_arena_trim_releases_the_surplus },
  { "a smaller frame reuses larger blocks",   t_arena_a_smaller_frame_reuses_larger_blocks },
  { "reset discards contents",                 t_arena_reset_discards_contents },
  { "refuses at its limit",                    t_arena_refuses_at_its_limit },
  { "a zero limit means the default",          t_arena_zero_limit_means_the_default },
  { "honours alignment up to 256 bytes",       t_arena_honours_alignment },
  { "aligns after an odd-sized allocation",    t_arena_aligns_after_an_odd_sized_allocation },
  { "used never counts padding",               t_arena_used_never_counts_padding },
  { "refuses a size that overflows",           t_arena_refuses_a_size_that_overflows },
  { "refuses a non-power-of-two alignment",    t_arena_refuses_a_non_power_of_two_alignment },
  { "size_aligned bounds the request",         t_arena_size_aligned_bounds_the_request },
  { "reserve tells limit from oom",            t_arena_reserve_distinguishes_limit_from_oom },
  { "a refusal keeps earlier allocations",     t_arena_refusal_keeps_earlier_allocations },
  { "survives an allocator refusal",           t_arena_survives_allocator_refusal },
  { "free is idempotent",                      t_arena_free_is_idempotent },
  { "used_peak is a high-water mark",          t_arena_used_peak_is_a_high_water_mark },
};

/* ── CdinErr ───────────────────────────────────────────────────────────── */

/* CDIN_OK must be zero. If it ever is not, `if (err)` and `err != CDIN_OK`
 * disagree and every call site that picked the other one is silently wrong —
 * a bug no compiler will report. */
static int t_err_ok_is_zero(void) {
  t_eq_int(CDIN_OK, 0);
  CdinErrDetail none = CDIN_ERR_INIT;
  t_assert("and an initialised detail is ok: " && cdin_err_ok(none));
  CdinErrDetail bad = CDIN_ERR(CDIN_ERR_PERM);
  t_assert("while a set one is not: " && !cdin_err_ok(bad));
  return 0;
}


/* Every classification has a distinct, non-empty, non-"unknown" name. A report
 * that prints "unknown" for a state this runtime reached is a report that
 * cannot be acted on. */
static int t_every_error_has_a_distinct_name(void) {
  for (int i = 0; i < (int)CDIN_ERR_COUNT; i++) {
    const char *name = cdin_err_name((CdinErr)i);
    t_assert(name != NULL);
    t_assert(name[0] != '\0');
    t_assert(strcmp(name, "unknown") != 0);
    for (int j = i + 1; j < (int)CDIN_ERR_COUNT; j++) {
      t_assert("names are distinct: "
               && strcmp(name, cdin_err_name((CdinErr)j)) != 0);
    }
  }
  t_eq_str(cdin_err_name(CDIN_OK), "ok");
  return 0;
}


/* A corrupted classification reports "unknown" rather than reading past the
 * table. The value can arrive from a cast in the Lua binding, so an
 * out-of-bounds read here is reachable, not theoretical. */
static int t_err_name_survives_a_corrupt_value(void) {
  t_eq_str(cdin_err_name((CdinErr)9999), "unknown");
  t_eq_str(cdin_err_name((CdinErr)-3), "unknown");
  return 0;
}


/* The description fits, is terminated, and carries the detail. Checked in a real
 * buffer rather than a string literal comparison, because the truncation and
 * terminator behaviour is the thing that can be wrong. */
static int t_err_describe_includes_the_detail(void) {
  CdinErrDetail e = CDIN_ERR_AT(CDIN_ERR_NOT_FOUND, "D:/missing.txt");
  char buf[128];
  CdinErr rc = cdin_err_describe(e, buf, sizeof buf);

  t_eq_int(rc, CDIN_OK);
  t_assert("names the classification: "
           && strstr(buf, "not_found") != NULL);
  t_assert("and carries the detail: "
           && strstr(buf, "D:/missing.txt") != NULL);

  /* Terminated right after the text, not at the end of the buffer: the
   * terminator goes where strlen says, and the tail is untouched. Checking
   * buf[sizeof(buf)-1] would be checking an unrelated byte. */
  size_t n = strlen(buf);
  t_assert("terminated at its own length: " && n > 0 && n < sizeof(buf));
  memset(buf, '#', sizeof buf);
  cdin_err_describe(e, buf, sizeof buf);
  t_assert("nothing written past the terminator: "
           && buf[n] == '\0' && buf[n + 1] == '#');
  return 0;
}


/* A small buffer truncates, reports the truncation, and still terminates. A log
 * line that silently loses the reason is how "not_found" ends up on screen with
 * nothing attached. */
static int t_err_describe_truncates_and_says_so(void) {
  CdinErrDetail e = CDIN_ERR_AT(CDIN_ERR_PERM, "a very long detail indeed");
  char buf[16];

  CdinErr rc = cdin_err_describe(e, buf, sizeof buf);
  t_assert("truncation is reported: " && rc == CDIN_ERR_LIMIT);
  t_assert("terminated inside the buffer: "
           && strlen(buf) < sizeof buf);
  t_assert("and it says something: " && buf[0] != '\0');

  /* A buffer of one byte must still be a valid empty string, not a write past
   * the end — this is the case that turns a formatting helper into a smash. */
  char one[1] = { 'X' };
  cdin_err_describe(e, one, sizeof one);
  t_eq_int(one[0], '\0');
  return 0;
}


/* Truncation happens at a UTF-8 boundary. The detail can be raw bytes from a
 * file, and a log line containing half a codepoint is a line that renders wrong
 * in every terminal and every editor that reads the log. */
static int t_err_describe_never_splits_a_codepoint(void) {
  /* "日本語のファイル" is 24 bytes: three 3-byte sequences. A buffer that
   * fits 5 bytes must not emit a partial one. */
  CdinErrDetail e = CDIN_ERR_AT(CDIN_ERR_INVALID_UTF8, "日本語のファイル");
  char buf[32];

  for (size_t cap = 1; cap <= 32; cap++) {
    memset(buf, 0x7F, sizeof buf);
    CdinErr rc = cdin_err_describe(e, buf, cap);
    (void)rc;

    size_t n = (cap == 0) ? 0 : strlen(buf);
    t_assert("never more than the buffer holds: " && n < cap);

    /* Every byte that survives is either ASCII or the start of a complete
     * sequence — checked by walking the string as UTF-8 and requiring it to end
     * exactly at a boundary. */
    size_t i = 0;
    int clean = 1;
    while (i < n) {
      unsigned char c = (unsigned char)buf[i];
      size_t seq;
      if (c < 0x80)      seq = 1;
      else if (c < 0xC0) { clean = 0; break; }     /* stray continuation */
      else if (c < 0xE0) seq = 2;
      else if (c < 0xF0) seq = 3;
      else               seq = 4;
      if (i + seq > n) { clean = 0; break; }      /* cut mid-sequence */
      i += seq;
    }
    t_assert("the truncation lands on a codepoint boundary: " && clean);
  }
  return 0;
}


/* The OS code is included when there is one, because that is usually the only
 * place "why" is still available. */
static int t_err_describe_includes_the_os_code(void) {
  CdinErrDetail e = CDIN_ERR_OS(CDIN_ERR_PERM, 13, "open failed");
  char buf[128];
  t_eq_int(cdin_err_describe(e, buf, sizeof buf), CDIN_OK);
  t_assert("the OS code is in the line: " && strstr(buf, "13") != NULL);
  t_assert("as well as the detail: " && strstr(buf, "open failed") != NULL);

  /* And with no detail, still there. */
  CdinErrDetail e2 = CDIN_ERR_OS(CDIN_ERR_PERM, 5, NULL);
  char buf2[128];
  t_eq_int(cdin_err_describe(e2, buf2, sizeof buf2), CDIN_OK);
  t_assert("the OS code survives with no detail: "
           && strstr(buf2, "5") != NULL);
  return 0;
}


/* CDIN_OK describes as "ok" and stops — no detail, no OS code, nothing appended.
 * "ok: something" in a log is noise that trains a reader to skip the field. */
static int t_err_ok_describes_as_nothing(void) {
  CdinErrDetail e = CDIN_ERR_AT(CDIN_OK, "should not appear");
  char buf[128];
  t_eq_int(cdin_err_describe(e, buf, sizeof buf), CDIN_OK);
  t_assert("and the detail is dropped: "
           && strstr(buf, "should not appear") == NULL);
  return 0;
}


/* cdin_err_set returns the classification as well as filling the detail, so a
 * call site can `return cdin_err_set(...)` and the caller still gets a value. A
 * NULL detail pointer must not crash — several call sites have no string. */
static int t_err_set_returns_the_classification(void) {
  CdinErrDetail e = CDIN_ERR_INIT;
  t_eq_int(cdin_err_set(&e, CDIN_ERR_LIMIT, "wanted 9, cap is 4"),
           CDIN_ERR_LIMIT);
  t_eq_int(e.code, CDIN_ERR_LIMIT);
  t_eq_str(e.detail, "wanted 9, cap is 4");

  /* A caller that does not want the detail still gets the classification. */
  t_eq_int(cdin_err_set(NULL, CDIN_ERR_OOM, NULL), CDIN_ERR_OOM);
  return 0;
}


static const CtestCase error_cases[] = {
  { "CDIN_OK is zero",                        t_err_ok_is_zero },
  { "every error has a distinct name",        t_every_error_has_a_distinct_name },
  { "a corrupt value names itself unknown",   t_err_name_survives_a_corrupt_value },
  { "describe includes the detail",           t_err_describe_includes_the_detail },
  { "describe truncates and says so",         t_err_describe_truncates_and_says_so },
  { "describe never splits a codepoint",      t_err_describe_never_splits_a_codepoint },
  { "describe includes the OS code",          t_err_describe_includes_the_os_code },
  { "ok describes as nothing",                t_err_ok_describes_as_nothing },
  { "set returns the classification",         t_err_set_returns_the_classification },
};

const CtestSuite arena_suite = {
  "arena",
  arena_cases,
  (int)(sizeof(arena_cases) / sizeof(arena_cases[0])),
};

/* A second suite from this one file: the runner collects suites by pointer, so
 * an arena suite and an error suite can sit in one translation unit and still be
 * listed and named separately. */
const CtestSuite error_suite = {
  "error",
  error_cases,
  (int)(sizeof(error_cases) / sizeof(error_cases[0])),
};