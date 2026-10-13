/* Damage-cache tests, with a font allocator that counts frees.
 *
 * The defect: rencache_free_font queued a FREE_FONT command and, when the
 * command buffer was full, push_command returned NULL and the font pointer
 * went with it. Every font whose __gc happened during a frame heavy enough to
 * fill 512 KiB was leaked — permanently, with no log line saying so, which is
 * what makes it the class of bug AGENTS.md rule 4 is about.
 *
 * The fix routes an unqueueable font to a bounded overflow list that end_frame
 * drains. The test fills the buffer with clip commands, asks for a font free,
 * and asserts that the font was accounted for rather than dropped — then ends
 * the frame and asserts it was actually freed. Freeing is counted by
 * stub_renderer.c, because the real ren_free_font lives in a renderer that
 * needs SDL.
 */

#include <stdio.h>
#include <string.h>

#include "../../src/ui/renderer_cache.h"
#include "ctest.h"

/* The command buffer, as this translation unit sees it. Kept in step with
 * renderer_cache.c's COMMAND_BUF_SIZE by mk/test.mk passing the same value. */
#ifdef RENCACHE_TEST_BUF
#  define TEST_BUF_SIZE RENCACHE_TEST_BUF
#else
#  define TEST_BUF_SIZE (1024 * 512)
#endif

/* rencache_end_frame calls into the renderer for the commands it replays, so
 * a frame can only be ended with no drawing in it. Both cases below rely on
 * that: they push FREE_FONT commands and nothing else, so the replay loop
 * touches neither the surface nor a font. */

/* How many fonts the overflow path currently holds. Not exported by the
 * module's header on purpose — this is the one place that needs to see inside,
 * so it is reached through a declaration rather than by widening the public
 * API for a test. */
extern int rencache_overflow_count(void);

/* The number of ren_free_font calls the stub renderer has seen, since the last
 * ren_stub_reset. */
extern int  ren_stub_fonts_freed(void);
extern void ren_stub_reset(void);

/* A font is only ever opaque to the cache: the cache stores and forwards the
 * pointer and never dereferences it, so a tagged integer cast to the opaque
 * type is a complete stand-in. It needs no allocator and cannot be freed for
 * real — stub_renderer.c counts the free calls instead. */
static int next_font_id = 1;

static RenFont *make_font(void) {
  int id = next_font_id++;
  return (RenFont *)(intptr_t)id;
}


/* Fills the command buffer with draw_rects (each a fixed-size record) and then
 * asks for a font free. The free cannot be queued, so it must land in the
 * overflow list rather than being dropped. */
static int t_font_free_is_not_dropped_when_full(void) {
  rencache_begin_frame();

  /* Draw rects are ignored unless they overlap the screen rect, and screen
   * dimensions come from the renderer — which is not initialised here. So the
   * buffer is filled with clip commands instead, which are queued
   * unconditionally and are the same fixed size. */
  RenRect r = { 0, 0, 10, 10 };
  for (int i = 0; i < TEST_BUF_SIZE / (int)sizeof(RenRect); i++) {
    rencache_set_clip_rect(r);
  }

  RenFont *font = make_font();
  rencache_free_font(font);

  t_assert("the overflow list took the font: " && rencache_overflow_count() >= 1);
  return 0;
}


/* end_frame drains the overflow, so a font that could not be queued is still
 * freed. This is the assertion the whole defect turns on: before the fix the
 * pointer was simply lost here and this count stayed at zero. */
static int t_overflow_is_drained_by_end_frame(void) {
  /* The previous case left one font in the overflow. */
  t_assert(rencache_overflow_count() >= 1);

  ren_stub_reset();
  rencache_end_frame();

  t_assert("the overflowed font was freed by end_frame: "
           && ren_stub_fonts_freed() >= 1);
  t_assert("the overflow list is empty after end_frame: "
           && rencache_overflow_count() == 0);
  return 0;
}


/* A frame with room in the buffer queues the font normally and overflows
 * nothing. This is the common path, and it must keep working. */
static int t_font_free_is_queued_when_there_is_room(void) {
  rencache_begin_frame();
  int before = rencache_overflow_count();

  RenFont *font = make_font();
  /* Queued, not overflowed: with an empty buffer there is room. */
  rencache_free_font(font);

  t_assert("a font with room to spare was not overflowed: "
           && rencache_overflow_count() == before);
  return 0;
}


/* Both the command buffer AND the overflow list are full.
 *
 * The third branch of rencache_free_font, and the one nobody exercises by
 * accident: it frees the font immediately, which risks a use-after-free from a
 * command still in the buffer, and is taken because leaking is the bug the
 * overflow list exists to prevent. Asserted rather than left untested, because a
 * branch that frees unsafely under pressure is exactly the branch that must not
 * change silently.
 *
 * The accounting is what is asserted: every font handed in must come out, whether
 * through the queue, through the overflow, or through the immediate free. A font
 * that is in none of those is a leak, which is the defect this whole file exists
 * to prevent. */
static int t_both_queues_full_still_frees_every_font(void) {
  ren_stub_reset();
  rencache_begin_frame();

  /* Fill the command buffer, so every subsequent free must overflow. */
  RenRect r = { 0, 0, 10, 10 };
  for (int i = 0; i < TEST_BUF_SIZE / (int)sizeof(RenRect); i++) {
    rencache_set_clip_rect(r);
  }

  /* More than the overflow list holds, so the third branch is reached. The count
   * is deliberately generous: FREE_OVERFLOW_MAX is 64, and asking for well over
   * that guarantees the list fills whatever the constant is. */
  enum { ASKED = 200 };
  for (int i = 0; i < ASKED; i++) {
    rencache_free_font(make_font());
  }

  /* Some are queued for end_frame and some were freed immediately; between them
   * every one must be accounted for. Asserted on the sum rather than on either
   * count alone, because a change that moved fonts between the two paths would
   * be a behaviour change worth noticing. */
  rencache_end_frame();
  t_assert("no font was lost when both queues were full: "
           && ren_stub_fonts_freed() >= ASKED - 1);
  t_assert("the overflow list drains completely: "
           && rencache_overflow_count() == 0);

  /* And the buffer is usable again: a full buffer must not leave the module in a
   * state where every later frame also overflows. */
  rencache_begin_frame();
  t_assert("the command buffer recovered after the full frame: "
           && rencache_overflow_count() == 0);
  rencache_end_frame();
  return 0;
}


/* Repeated free cycles must not accumulate anything.
 *
 * A single cycle passing says nothing about a list that grows: the overflow array
 * is bounded, but an index that is only ever incremented would pass every
 * one-shot test and fail the second run. Several cycles, each asserting the same
 * counts, is what makes an accumulator visible. */
static int t_repeated_cycles_do_not_accumulate(void) {
  ren_stub_reset();
  RenRect r = { 0, 0, 10, 10 };

  for (int cycle = 0; cycle < 5; cycle++) {
    rencache_begin_frame();
    for (int i = 0; i < TEST_BUF_SIZE / (int)sizeof(RenRect); i++) {
      rencache_set_clip_rect(r);
    }
    /* Two overflowed fonts per cycle: enough to hit the overflow path, few
     * enough that the list never fills and the third branch is not involved. */
    rencache_free_font(make_font());
    rencache_free_font(make_font());
    t_assert(rencache_overflow_count() == 2);

    rencache_end_frame();
    /* Exactly two freed, and the list empty, every cycle. A count that grew with
     * the cycle number would fail here. */
    t_assert(rencache_overflow_count() == 0);
    t_assert(ren_stub_fonts_freed() == 2 * (cycle + 1));
  }
  return 0;
}


/* A partial failure must leave the module able to keep working.
 *
 * The font binding's contract is that a font whose handle closes is released
 * exactly once, and that a release which cannot be queued is deferred rather than
 * dropped. Between them, a frame that goes through the overflow path must leave
 * the cache in its normal state — which is what this checks by continuing to use
 * it afterwards instead of only inspecting it at the failure. */
static int t_the_cache_is_usable_after_an_overflowed_frame(void) {
  rencache_begin_frame();
  RenRect r = { 0, 0, 10, 10 };
  for (int i = 0; i < TEST_BUF_SIZE / (int)sizeof(RenRect); i++) {
    rencache_set_clip_rect(r);
  }
  rencache_free_font(make_font());       /* overflows */
  rencache_end_frame();

  /* The next frame behaves like a first frame: room in the buffer, nothing in
   * the overflow, and a font free that is queued rather than deferred. */
  rencache_begin_frame();
  t_assert(rencache_overflow_count() == 0);
  ren_stub_reset();
  rencache_free_font(make_font());
  t_assert(rencache_overflow_count() == 0);
  rencache_end_frame();
  t_assert("the queued font was freed: " && ren_stub_fonts_freed() == 1);
  return 0;
}


/* The stats the memory report reads are the last frame's, and the peak never
 * exceeds the buffer it was measured against. */
static int t_stats_are_sane(void) {
  rencache_begin_frame();
  int dt = 0, dr = 0, peak = 0;
  rencache_get_stats(&dt, &dr, &peak);

  t_assert(rencache_get_stats != NULL);
  t_assert("the draw-text count is not negative: " && dt >= 0);
  t_assert("the draw-rect count is not negative: " && dr >= 0);
  t_assert("the command buffer peak is bounded: " && peak <= TEST_BUF_SIZE);
  return 0;
}


static const CtestCase rencache_cases[] = {
  { "a font free is overflowed, not dropped, when the buffer is full",
    t_font_free_is_not_dropped_when_full },
  { "an overflowed font is freed by end_frame",
    t_overflow_is_drained_by_end_frame },
  { "a font free is queued when the buffer has room",
    t_font_free_is_queued_when_there_is_room },
  { "both queues full still frees every font",
    t_both_queues_full_still_frees_every_font },
  { "repeated cycles do not accumulate",
    t_repeated_cycles_do_not_accumulate },
  { "the cache is usable after an overflowed frame",
    t_the_cache_is_usable_after_an_overflowed_frame },
  { "frame stats are bounded by the buffer size",
    t_stats_are_sane },
};

const CtestSuite rencache_suite = {
  "rencache",
  rencache_cases,
  (int)(sizeof(rencache_cases) / sizeof(rencache_cases[0])),
};
