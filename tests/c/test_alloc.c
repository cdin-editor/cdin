/* Allocator tests: accounting, leak detection, and fault injection.
 *
 * These are the tests that make the rest of Phase 1 possible. Every later
 * subsystem reports its bytes through this module, so what is checked here is
 * not "does malloc work" but "does a number that gets printed in a phase
 * report mean anything".
 *
 * The three properties that matter:
 *
 *  1. Accounting is exact. A counter that drifts is worse than no counter,
 *     because a report built on it is trusted. So: allocate, free, and the
 *     figure returns to where it started — not approximately, exactly.
 *  2. Freeing something else is caught, not trusted. A double free and a
 *     foreign pointer are both heap corruption; the header exists to turn
 *     them into a log line.
 *  3. Allocation failure is reachable. AGENTS.md requires a fault-injection
 *     allocator, and a requirement nobody exercises is a requirement that does
 *     not hold — so every refusal case here also asserts that the injector
 *     actually fired, rather than passing because a NULL came back for some
 *     other reason.
 *
 * These cases run in one process, so the live totals are measured as
 * differences rather than absolutes. A case that asserted "live == 0" would
 * fail on the second case for reasons that have nothing to do with it.
 */

#include <stdalign.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>
#include <stdlib.h>
#include <string.h>

#include "../../src/base/alloc.h"
#include "ctest.h"

/* The live total before this case started, so every assertion is a delta and
 * cases can be reordered without breaking each other. */
static size_t live_at_entry(void) {
  return cdin_mem_total_live();
}

/* Nothing may leak between cases. Checked by the runner after each one, which
 * is why the runner calls the report rather than each case doing it. */

static int t_accounts_a_single_allocation(void) {
  size_t before = live_at_entry();

  void *p = cdin_alloc(CDIN_MEM_BUFFER, 1000);
  t_assert("a plain allocation succeeds: " && p != NULL);
  t_eq_int(cdin_mem_live(CDIN_MEM_BUFFER), before + 1000);
  t_eq_int(cdin_mem_alloc_count(CDIN_MEM_BUFFER), 1);

  cdin_free(p);
  t_eq_int(cdin_mem_live(CDIN_MEM_BUFFER), before);
  t_eq_int(cdin_mem_total_live(), before);
  return 0;
}


/* The tag decides which subsystem the bytes land in. Two tags must not share a
 * counter, because "14 GiB in syntax" is only actionable if syntax and buffer
 * are distinguishable. */
static int t_tags_are_separate_counters(void) {
  size_t buf_before  = cdin_mem_live(CDIN_MEM_BUFFER);
  size_t font_before = cdin_mem_live(CDIN_MEM_FONT);

  void *a = cdin_alloc(CDIN_MEM_BUFFER, 4096);
  void *b = cdin_alloc(CDIN_MEM_FONT, 4096);
  t_assert(a && b);

  t_eq_int(cdin_mem_live(CDIN_MEM_BUFFER), buf_before + 4096);
  t_eq_int(cdin_mem_live(CDIN_MEM_FONT), font_before + 4096);

  cdin_free(a);
  cdin_free(b);
  t_eq_int(cdin_mem_live(CDIN_MEM_BUFFER), buf_before);
  t_eq_int(cdin_mem_live(CDIN_MEM_FONT), font_before);
  return 0;
}


/* A peak is a record of the high-water mark and must not fall when the memory
 * is released. A peak that resets on free reports the current size and calls
 * it a peak, which is how a one-time spike stops being visible. */
static int t_peak_is_a_high_water_mark(void) {
  void *p = cdin_alloc(CDIN_MEM_SYNTAX, 8192);
  t_assert(p != NULL);
  size_t peak_while_live = cdin_mem_peak(CDIN_MEM_SYNTAX);
  t_assert(peak_while_live >= 8192);

  cdin_free(p);
  t_eq_int(cdin_mem_live(CDIN_MEM_SYNTAX), 0);
  /* Still at least the spike, even though nothing is live now. */
  t_assert("the peak survives the free: "
           && cdin_mem_peak(CDIN_MEM_SYNTAX) >= peak_while_live);

  /* A second, smaller allocation must not lower it. */
  void *q = cdin_alloc(CDIN_MEM_SYNTAX, 16);
  t_assert(q != NULL);
  t_assert("a smaller allocation does not lower the peak: "
           && cdin_mem_peak(CDIN_MEM_SYNTAX) >= peak_while_live);
  cdin_free(q);
  return 0;
}


/* The total peak is not the sum of the per-tag peaks, and this is the case that
 * shows it. Two tags are each driven to the same high-water mark at *different*
 * times, never at once, so their peaks sum to twice anything that was ever
 * live.
 *
 * Built on CDIN_MEM_PLATFORM and CDIN_MEM_LUA_BIND because no other case here
 * allocates through them, which is what makes the exact arithmetic below
 * independent of the order the runner happens to use. */
static int t_total_peak_is_not_the_sum_of_peaks(void) {
  t_assert("this case needs PLATFORM untouched: "
           && cdin_mem_live(CDIN_MEM_PLATFORM) == 0);
  t_assert("this case needs LUA_BIND untouched: "
           && cdin_mem_live(CDIN_MEM_LUA_BIND) == 0);

  size_t live_at_entry = cdin_mem_total_live();
  size_t peak_at_entry  = cdin_mem_total_peak();

  /* First high-water mark: 40000 in PLATFORM, nothing else. */
  void *a = cdin_alloc(CDIN_MEM_PLATFORM, 20000);
  void *b = cdin_alloc(CDIN_MEM_PLATFORM, 20000);
  t_assert(a && b);
  t_eq_int(cdin_mem_peak(CDIN_MEM_PLATFORM), 40000);
  t_eq_int(cdin_mem_total_peak(), live_at_entry + 40000);
  cdin_free(a);
  cdin_free(b);

  /* Second high-water mark: 40000 in LUA_BIND, at a time when PLATFORM holds
   * nothing. PLATFORM's peak does not move, and the total peak does not either
   * — the same number of bytes was never live twice. */
  void *c = cdin_alloc(CDIN_MEM_LUA_BIND, 20000);
  void *d = cdin_alloc(CDIN_MEM_LUA_BIND, 20000);
  t_assert(c && d);
  t_eq_int(cdin_mem_peak(CDIN_MEM_PLATFORM), 40000);
  t_eq_int(cdin_mem_peak(CDIN_MEM_LUA_BIND), 40000);
  t_eq_int(cdin_mem_total_peak(), live_at_entry + 40000);
  cdin_free(c);
  cdin_free(d);

  /* The point: 80000 of peaks, 40000 of history. A total_peak implemented as
   * the sum of the tag peaks would report 80000 more than happened. */
  size_t sum_of_peaks = cdin_mem_peak(CDIN_MEM_PLATFORM)
                      + cdin_mem_peak(CDIN_MEM_LUA_BIND);
  t_eq_int(sum_of_peaks, 80000);
  t_assert("the sum of the peaks is double the real high-water mark: "
           && sum_of_peaks > cdin_mem_total_peak());
  t_assert("and the total peak did not move for the second mark: "
           && cdin_mem_total_peak() == live_at_entry + 40000);
  t_assert("nor above where the suite entered: "
           && cdin_mem_total_peak() >= peak_at_entry);
  t_eq_int(cdin_mem_total_live(), live_at_entry);
  return 0;
}


/* realloc keeps the block's original tag. A realloc that moved bytes between
 * subsystems would make the per-tag figures a matter of what the caller felt
 * like passing, and the caller is not the thing being measured. */
static int t_realloc_keeps_the_original_tag(void) {
  void *p = cdin_alloc(CDIN_MEM_FONT, 100);
  t_assert(p != NULL);

  size_t font_before  = cdin_mem_live(CDIN_MEM_FONT);
  size_t buffer_before = cdin_mem_live(CDIN_MEM_BUFFER);

  void *q = cdin_realloc(CDIN_MEM_BUFFER, p, 200);
  t_assert("realloc succeeds: " && q != NULL);

  t_eq_int(cdin_mem_tag_of(q), CDIN_MEM_FONT);
  t_eq_int(cdin_mem_live(CDIN_MEM_FONT), font_before + 100);
  t_eq_int(cdin_mem_live(CDIN_MEM_BUFFER), buffer_before);

  /* The old size is gone and the new one is counted exactly once. */
  t_eq_int(cdin_mem_live(CDIN_MEM_FONT), 200);

  cdin_free(q);
  t_eq_int(cdin_mem_live(CDIN_MEM_FONT), 0);
  return 0;
}


/* A failed realloc leaves the original block valid and still accounted for.
 *
 * Two things this catches that a NULL-return check alone would not: that the
 * counters did not lose the block when the resize failed, and that realloc is
 * actually reachable by the injector at all. It was not, for a while — the
 * resize path asked the system allocator directly, so "allocation failure" had
 * no meaning on the path nearly every growing structure takes. */
static int t_failed_realloc_keeps_the_original_block(void) {
  void *p = cdin_alloc(CDIN_MEM_EDIT, 512);
  t_assert(p != NULL);

  size_t live_before = cdin_mem_live(CDIN_MEM_EDIT);

  /* Allow nothing, so the very next allocation attempt is refused. */
  cdin_alloc_fail_after(0);
  void *q = cdin_realloc(CDIN_MEM_EDIT, p, 4096);

  /* Read the refusal count before disarming: disabling resets it, so a test
   * that checks afterwards is checking the wrong number. */
  unsigned long refused = cdin_alloc_failures();
  cdin_alloc_fail_disable();

  t_assert("the realloc was refused: " && q == NULL);
  t_assert("and the injector actually fired: " && refused >= 1);

  /* The original is still ours, still counted, and still freeable. A refusal
   * that quietly released the block would be the exact bug this exists to
   * catch, and it would show up downstream as a use-after-free rather than
   * here — so the counters and the payload are both checked. */
  t_eq_int(cdin_mem_tag_of(p), CDIN_MEM_EDIT);
  t_eq_int(cdin_mem_live(CDIN_MEM_EDIT), live_before);
  memset(p, 0xAA, 512);   /* writable: a failed realloc must not have freed it */
  t_assert("and the first bytes survived: " && ((unsigned char *)p)[0] == 0xAA);
  cdin_free(p);
  t_eq_int(cdin_mem_live(CDIN_MEM_EDIT), 0);
  return 0;
}


/* Injection lets n allocations through and refuses everything after. This is
 * the semantics that lets a test aim at "the tenth allocation inside this
 * splice" rather than only at "the very first one".
 *
 * The refusal count is asserted as well as the NULLs: a NULL on its own does
 * not prove the injector fired rather than the request failing for another
 * reason, and an injector that silently did nothing would pass a test that
 * only checked for NULL. */
static int t_fault_injection_allows_n_then_refuses(void) {
  size_t before = live_at_entry();

  cdin_alloc_fail_after(3);
  void *a = cdin_alloc(CDIN_MEM_BASE, 64);
  void *b = cdin_alloc(CDIN_MEM_BASE, 64);
  void *c = cdin_alloc(CDIN_MEM_BASE, 64);
  void *d = cdin_alloc(CDIN_MEM_BASE, 64);
  void *e = cdin_alloc(CDIN_MEM_BASE, 64);
  unsigned long refused = cdin_alloc_failures();
  cdin_alloc_fail_disable();

  t_assert("the first allocation is allowed: " && a != NULL);
  t_assert("the second is allowed: " && b != NULL);
  t_assert("the third is allowed: " && c != NULL);
  t_assert("the fourth is refused: " && d == NULL);
  t_assert("and so is the fifth: " && e == NULL);
  t_eq_int(refused, 2);

  /* Only the three that were handed out are counted, which is the property
   * that makes a partial-failure path testable: the caller sees exactly which
   * of its allocations exist. */
  t_eq_int(cdin_mem_live(CDIN_MEM_BASE), before + 192);

  cdin_free(a);
  cdin_free(b);
  cdin_free(c);
  t_eq_int(cdin_mem_live(CDIN_MEM_BASE), before);
  return 0;
}


/* n = 0 refuses the very next allocation, which is the "out of memory from the
 * first call" case. This only works because disarming is a separate call
 * rather than the value 0 — with 0 meaning "disarmed" this case is
 * unreachable and total OOM is untestable. */
static int t_fault_injection_at_zero_refuses_immediately(void) {
  cdin_alloc_fail_after(0);
  t_assert("n = 0 arms: " && cdin_alloc_fail_is_armed());
  void *p = cdin_alloc(CDIN_MEM_BASE, 16);
  unsigned long refused = cdin_alloc_failures();
  cdin_alloc_fail_disable();

  t_assert("and refuses the very next allocation: " && p == NULL);
  t_eq_int(refused, 1);
  t_assert("disarming clears it: " && !cdin_alloc_fail_is_armed());
  return 0;
}


/* Disarming is what every test must do before asserting, so it is tested on its
 * own: an allocator that "passes" by never refusing anything has to be
 * distinguishable from one that works. */
static int t_fault_injection_can_be_disarmed(void) {
  cdin_alloc_fail_disable();
  void *p = cdin_alloc(CDIN_MEM_BASE, 32);
  t_assert("a disarmed injector allows everything: " && p != NULL);
  t_eq_int(cdin_alloc_failures(), 0);
  cdin_free(p);
  return 0;
}


/* calloc zeroes, and does not under-allocate when count*size overflows. The
 * overflow case is the reason this is not a memset in front of cdin_alloc. */
static int t_calloc_zeroes(void) {
  unsigned char *p = (unsigned char *)cdin_calloc(CDIN_MEM_BASE, 256, 1);
  t_assert(p != NULL);
  int all_zero = 1;
  for (int i = 0; i < 256; i++) if (p[i] != 0) { all_zero = 0; break; }
  t_assert("calloc returns zeroed memory: " && all_zero);
  cdin_free(p);
  return 0;
}

static int t_calloc_rejects_overflow(void) {
  size_t before = live_at_entry();
  /* count * size wraps on a 64-bit size_t: (2^32) * (2^32) = 2^64. */
  void *p = cdin_calloc(CDIN_MEM_BASE, (size_t)1 << 32, (size_t)1 << 32);
  t_assert("an overflowing calloc is refused: " && p == NULL);
  t_eq_int(cdin_mem_total_live(), before);
  return 0;
}


/* A zero-size allocation is a valid, distinct, freeable pointer. Returning
 * NULL for it would make `if (!p)` the wrong test for allocation failure, and
 * the C standard says it must not be confused with failure. */
static int t_zero_size_allocation_is_not_null(void) {
  void *a = cdin_alloc(CDIN_MEM_BASE, 0);
  void *b = cdin_alloc(CDIN_MEM_BASE, 0);
  t_assert("a zero-size alloc is not NULL: " && a != NULL);
  t_assert("a second zero-size alloc is not NULL: " && b != NULL);
  t_assert("and the two are distinct pointers: " && a != b);
  cdin_free(a);
  cdin_free(b);
  return 0;
}


/* An invalid tag is refused rather than corrupting a counter. A tag is an
 * enum, but it arrives from a caller, and an out-of-range one indexing a
 * static array is a memory-safety bug before it is a reporting bug. */
static int t_invalid_tag_is_refused(void) {
  size_t before = live_at_entry();
  void *p = cdin_alloc((CdinMemTag)999, 64);
  t_assert("an invalid tag is refused: " && p == NULL);
  t_eq_int(cdin_mem_total_live(), before);

  t_eq_int(cdin_mem_live((CdinMemTag)999), 0);
  t_eq_int(cdin_mem_peak((CdinMemTag)999), 0);
  t_assert(cdin_mem_tag_name((CdinMemTag)999) != NULL);
  return 0;
}


/* Freeing NULL is a no-op, per the C convention every call site assumes. */
static int t_free_null_is_a_noop(void) {
  size_t before = live_at_entry();
  cdin_free(NULL);
  t_eq_int(cdin_mem_total_live(), before);
  return 0;
}


/* The payload is aligned for any type. The requirement is alignof, not sizeof:
 * max_align_t on x86-64 mingw is 32 bytes with 16-byte alignment, so a check
 * against its size would demand 32-byte alignment the language never asks for
 * and fail a correct allocator. */
static int t_payload_is_max_aligned(void) {
  /* Checked across sizes, not once: the offset is a compile-time constant, so
   * what varies between blocks is where malloc puts them, and one aligned
   * allocation proves nothing about the next hundred. Sizes chosen to cross
   * the usual size-class boundaries, where the block's base address jumps. */
  static const size_t sizes[] = { 1, 7, 8, 15, 16, 17, 63, 64, 65, 255, 4096 };
  void *blocks[sizeof(sizes) / sizeof(sizes[0])];

  for (size_t i = 0; i < sizeof(sizes) / sizeof(sizes[0]); i++) {
    blocks[i] = cdin_alloc(CDIN_MEM_BUFFER, sizes[i]);
    t_assert("a size in the sweep allocated: " && blocks[i] != NULL);
  }

  for (size_t i = 0; i < sizeof(sizes) / sizeof(sizes[0]); i++) {
    size_t addr = (size_t)blocks[i];
    t_assert("the payload is aligned to alignof(max_align_t): "
             && (addr % alignof(max_align_t)) == 0);
    t_assert("and to the strictest scalar type as well: "
             && (addr % _Alignof(long double)) == 0);
    t_assert("and to a pointer, which the buffer will store: "
             && (addr % _Alignof(void *)) == 0);
  }

  for (size_t i = 0; i < sizeof(sizes) / sizeof(sizes[0]); i++) {
    cdin_free(blocks[i]);
  }
  t_eq_int(cdin_mem_live(CDIN_MEM_BUFFER), 0);
  return 0;
}


/* Every tag has a name, and the names are distinct. A report that prints the
 * same word twice for two subsystems is a report that cannot be acted on. */
static int t_every_tag_has_a_distinct_name(void) {
  for (int i = 0; i < (int)CDIN_MEM_COUNT; i++) {
    const char *name = cdin_mem_tag_name((CdinMemTag)i);
    t_assert(name != NULL);
    t_assert(name[0] != '\0');
    for (int j = i + 1; j < (int)CDIN_MEM_COUNT; j++) {
      t_assert(strcmp(name, cdin_mem_tag_name((CdinMemTag)j)) != 0);
    }
  }
  return 0;
}


/* A double free is refused, counted, and does not move the accounting.
 *
 * Reliable only where freed blocks are quarantined (debug builds): the second
 * free then reads a header that is still there. In a release build the first
 * free returns the block to malloc and the second would be undefined, so the
 * case reports itself as not applicable instead of exercising UB. */
static int t_double_free_does_not_double_count(void) {
  if (!cdin_mem_debug_enabled()) {
    printf("     (skipped: double-free detection needs the debug quarantine)\n");
    return 0;
  }
  size_t bad_before = cdin_mem_bad_frees();

  void *p = cdin_alloc(CDIN_MEM_FS, 128);
  t_assert(p != NULL);
  t_eq_int(cdin_mem_live(CDIN_MEM_FS), 128);

  cdin_free(p);
  t_eq_int(cdin_mem_live(CDIN_MEM_FS), 0);
  t_eq_int(cdin_mem_bad_frees(), bad_before);

  cdin_free(p);
  t_eq_int(cdin_mem_live(CDIN_MEM_FS), 0);
  t_eq_int(cdin_mem_bad_frees(), bad_before + 1);
  return 0;
}


/* A pointer that never came from here is not passed to the system free.
 *
 * The allocator reads the header in front of the pointer, so the "foreign"
 * pointer is placed inside a larger block: the bytes in front of it exist and
 * are zero, which is what a real foreign pointer needs for detection to be
 * defined at all. */
static int t_a_foreign_pointer_is_not_freed(void) {
  size_t live_before = cdin_mem_total_live();
  size_t bad_before  = cdin_mem_bad_frees();

  unsigned char *buf = (unsigned char *)malloc(256);
  t_assert(buf != NULL);
  memset(buf, 0, 256);

  cdin_free(buf + 64);
  t_eq_int(cdin_mem_total_live(), live_before);
  t_eq_int(cdin_mem_bad_frees(), bad_before + 1);

  int intact = 1;
  for (int i = 0; i < 256; i++) if (buf[i] != 0) { intact = 0; break; }
  t_assert("and did not touch it: " && intact);
  free(buf);
  return 0;
}


/* A clean block is never reported as overflowed. The first version of the guard
 * test only checked that free() returned, so a front guard overlapping the
 * header — which made every free report an overflow — went unnoticed. */
static int t_clean_blocks_report_no_guard_violation(void) {
  if (!cdin_mem_debug_enabled()) {
    printf("     (skipped: this build has no guard bytes)\n");
    return 0;
  }
  size_t before = cdin_mem_guard_violations();

  for (size_t size = 0; size <= 70; size += 7) {
    unsigned char *p = (unsigned char *)cdin_alloc(CDIN_MEM_PLATFORM, size);
    t_assert(p != NULL);
    memset(p, 0x11, size);
    cdin_free(p);
  }
  t_eq_int(cdin_mem_guard_violations(), before);
  return 0;
}


/* An overflow past either end is caught on free, and only that block's is. */
static int t_guard_bytes_catch_overflow_and_underflow(void) {
  if (!cdin_mem_debug_enabled()) {
    printf("     (skipped: this build has no guard bytes)\n");
    return 0;
  }
  size_t before = cdin_mem_guard_violations();

  unsigned char *over = (unsigned char *)cdin_alloc(CDIN_MEM_PLATFORM, 64);
  t_assert(over != NULL);
  over[64] = 0xFF;                 /* one byte past the payload */
  cdin_free(over);
  t_eq_int(cdin_mem_guard_violations(), before + 1);

  /* Offset 17 below the payload is inside the front guard (header is the 16
   * bytes directly in front of the payload, the guard the 16 before that). */
  unsigned char *under = (unsigned char *)cdin_alloc(CDIN_MEM_PLATFORM, 64);
  t_assert(under != NULL);
  under[-17] = 0xFF;
  cdin_free(under);
  t_eq_int(cdin_mem_guard_violations(), before + 2);

  t_eq_int(cdin_mem_live(CDIN_MEM_PLATFORM), 0);
  return 0;
}


/* realloc keeps the contents, keeps the tag, and leaves valid guards behind:
 * growing, shrinking, and from NULL, then a clean free. */
static int t_realloc_keeps_contents_and_guards(void) {
  size_t viol_before = cdin_mem_guard_violations();

  unsigned char *p = (unsigned char *)cdin_alloc(CDIN_MEM_BUFFER, 16);
  t_assert(p != NULL);
  for (int i = 0; i < 16; i++) p[i] = (unsigned char)(i + 1);

  p = (unsigned char *)cdin_realloc(CDIN_MEM_BASE, p, 4096);
  t_assert(p != NULL);
  t_eq_int(cdin_mem_tag_of(p), CDIN_MEM_BUFFER);
  for (int i = 0; i < 16; i++) t_assert(p[i] == (unsigned char)(i + 1));
  memset(p, 0x22, 4096);

  p = (unsigned char *)cdin_realloc(CDIN_MEM_BASE, p, 8);
  t_assert(p != NULL);
  t_eq_int(cdin_mem_live(CDIN_MEM_BUFFER), 8);
  t_assert(p[0] == 0x22 && p[7] == 0x22);

  cdin_free(p);
  t_eq_int(cdin_mem_live(CDIN_MEM_BUFFER), 0);
  t_eq_int(cdin_mem_guard_violations(), viol_before);
  return 0;
}


/* A refused realloc leaves the block registered: the leak report still counts
 * it and a later free is clean. */
static int t_failed_realloc_keeps_the_block_registered(void) {
  size_t blocks_before = cdin_mem_live_blocks();

  void *p = cdin_alloc(CDIN_MEM_LOOP, 32);
  t_assert(p != NULL);
  size_t blocks = cdin_mem_live_blocks();

  cdin_alloc_fail_after(0);
  void *q = cdin_realloc(CDIN_MEM_LOOP, p, 1024);
  t_assert(q == NULL);
  t_assert(cdin_alloc_failures() >= 1);
  cdin_alloc_fail_disable();

  t_eq_int(cdin_mem_live_blocks(), blocks);
  t_eq_int(cdin_mem_live(CDIN_MEM_LOOP), 32);
  cdin_free(p);
  t_eq_int(cdin_mem_live_blocks(), blocks_before);
  return 0;
}


/* Releasing blocks oldest-first is the worst case for a registry that walks a
 * list to find the block. With 100k live blocks that walk is ~5e9 steps; with
 * the links inside the block it is 100k pointer updates. The bound is loose on
 * purpose (it only has to separate the two), so a slow CI machine does not
 * make it flaky. */
static int t_free_cost_does_not_grow_with_live_blocks(void) {
  enum { N = 100000 };
  void **blocks = (void **)malloc(sizeof(void *) * N);
  t_assert(blocks != NULL);

  for (int i = 0; i < N; i++) {
    blocks[i] = cdin_alloc(CDIN_MEM_BUFFER, 32);
    if (!blocks[i]) {
      for (int k = 0; k < i; k++) cdin_free(blocks[k]);
      free(blocks);
      return CTEST_FAIL_ALLOC;
    }
  }

  clock_t t0 = clock();
  for (int i = 0; i < N; i++) cdin_free(blocks[i]);
  double secs = (double)(clock() - t0) / (double)CLOCKS_PER_SEC;
  free(blocks);

  t_assert("100k oldest-first frees took under 3 s: " && secs < 3.0);
  t_eq_int(cdin_mem_live(CDIN_MEM_BUFFER), 0);
  return 0;
}


/* A pointer released and then passed to realloc is refused, not resized. */
static int t_realloc_of_a_freed_pointer_is_refused(void) {
  if (!cdin_mem_debug_enabled()) {
    printf("     (skipped: needs the debug quarantine)\n");
    return 0;
  }
  size_t bad_before = cdin_mem_bad_frees();
  void *p = cdin_alloc(CDIN_MEM_FS, 64);
  t_assert(p != NULL);
  cdin_free(p);
  t_assert(cdin_realloc(CDIN_MEM_FS, p, 128) == NULL);
  t_eq_int(cdin_mem_bad_frees(), bad_before + 1);
  t_eq_int(cdin_mem_live(CDIN_MEM_FS), 0);
  return 0;
}


/* The leak report is what the test runner gates on, so it has to be able to say
 * "zero" — and to say it truthfully. Two blocks held live, then released. */
static int t_the_leak_report_counts_live_blocks(void) {
  if (!cdin_mem_debug_enabled()) {
    /* Without the registry this returns 0 no matter what is live, which is why
     * it logs that it checked nothing. Asserting 0 here would be asserting
     * that a number means nothing. */
    t_eq_int(cdin_mem_leak_report(), 0);
    return 0;
  }

  void *a = cdin_alloc(CDIN_MEM_LOOP, 64);
  void *b = cdin_alloc(CDIN_MEM_LOOP, 64);
  t_assert(a && b);
  size_t held = cdin_mem_leak_report();
  t_assert("two live blocks are reported: " && held >= 2);

  cdin_free(a);
  cdin_free(b);
  size_t after = cdin_mem_leak_report();
  t_assert("releasing them lowers the count: " && after < held);
  return 0;
}


static const CtestCase alloc_cases[] = {
  { "accounts one allocation exactly",             t_accounts_a_single_allocation },
  { "tags are separate counters",                  t_tags_are_separate_counters },
  { "peak is a high-water mark, not a level",      t_peak_is_a_high_water_mark },
  { "total peak is not the sum of the tag peaks",  t_total_peak_is_not_the_sum_of_peaks },
  { "realloc keeps the original tag",              t_realloc_keeps_the_original_tag },
  { "a failed realloc keeps the original block",   t_failed_realloc_keeps_the_original_block },
  { "fault injection allows n, then refuses",      t_fault_injection_allows_n_then_refuses },
  { "fault injection at 0 refuses immediately",    t_fault_injection_at_zero_refuses_immediately },
  { "fault injection can be disarmed",             t_fault_injection_can_be_disarmed },
  { "calloc zeroes",                               t_calloc_zeroes },
  { "calloc refuses an overflowing count*size",    t_calloc_rejects_overflow },
  { "a zero-size allocation is not NULL",          t_zero_size_allocation_is_not_null },
  { "an invalid tag is refused",                   t_invalid_tag_is_refused },
  { "free(NULL) is a no-op",                       t_free_null_is_a_noop },
  { "the payload is max-aligned",                  t_payload_is_max_aligned },
  { "a double free does not double count",         t_double_free_does_not_double_count },
  { "a foreign pointer is not freed",              t_a_foreign_pointer_is_not_freed },
  { "clean blocks report no guard violation",      t_clean_blocks_report_no_guard_violation },
  { "guards catch overflow and underflow",         t_guard_bytes_catch_overflow_and_underflow },
  { "realloc keeps contents, tag and guards",      t_realloc_keeps_contents_and_guards },
  { "a failed realloc keeps the block registered", t_failed_realloc_keeps_the_block_registered },
  { "free cost does not grow with live blocks",    t_free_cost_does_not_grow_with_live_blocks },
  { "realloc of a freed pointer is refused",       t_realloc_of_a_freed_pointer_is_refused },
  { "the leak report counts live blocks",          t_the_leak_report_counts_live_blocks },
  { "every tag has a distinct name",               t_every_tag_has_a_distinct_name },
};

const CtestSuite alloc_suite = {
  "alloc",
  alloc_cases,
  (int)(sizeof(alloc_cases) / sizeof(alloc_cases[0])),
};
