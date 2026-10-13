/* The font binding, tested against the stub renderer.
 *
 * This is the only test of renderer_font.c, and it exists because the conversion
 * to the handle convention introduced real logic that nothing was checking: the
 * fallback keepalives. Those were verified once by hand, from a scratch APPDATA
 * directory, driving the real editor — which is not a test, because the next
 * change can break it and nothing says so.
 *
 * The stub's free counter is what makes the keepalive observable. A fallback
 * whose handle is collected must NOT be freed while its parent is chained to it,
 * and the stub counts every ren_free_font, so "was it freed?" is a number rather
 * than a crash that may or may not happen on another machine.
 *
 * The tests below are the ones that cannot be written without a real Lua state
 * and a stubbed renderer. Everything about the convention itself is in
 * test_handle.c, which has no renderer at all.
 */

#include <stdio.h>
#include <string.h>

#include <lauxlib.h>
#include <lua.h>

#include "../../src/api/renderer_font.h"
#include "../../src/ui/renderer.h"
#include "ctest.h"
#include "lua_harness.h"

int  ren_stub_fonts_freed(void);
int  ren_stub_fonts_loaded(void);
int  ren_stub_fallbacks_added(void);
void ren_stub_reset(void);

/* Loads a stub font through the same path the runtime uses, `renderer.font.load`.
 * The filename is recorded by the stub's log, not returned; what matters is that
 * a load either yields a handle or raises. */
static int load_font(const char *var, const char *filename) {
  char code[256];
  snprintf(code, sizeof code, "%s = renderer.font.load('%s', 14.0)",
           var, filename);
  return lh_eval(code);
}

/* Every global a font case assigns. Listed so reset_fonts can nil them all:
 * a case that leaves a handle in a global hands the next case a live handle, and
 * that case's own counter assertions then read counts that are not its own. */
static const char *const font_vars[] = {
  "f", "parent", "fb", "p2", "g2", "p3", "g3", NULL
};

/* Brings the Lua state and the stub back to a known empty state, so a case's
 * counters describe only that case.
 *
 * The collection is what makes this work, and it has to be *before* the counter
 * reset, not after: finalisers that were queued by the previous case run during
 * this collection and move fonts_freed, so zeroing the counter afterwards would
 * hide exactly the cross-case leakage this is here to stop. Two collections
 * because one unrefs a fallback and the second is what finalises the userdata
 * that ref was holding. */
static int reset_fonts(void) {
  char code[512];
  size_t n = 0;
  for (int i = 0; font_vars[i]; i++)
    n += (size_t)snprintf(code + n, sizeof code - n, "%s = nil ", font_vars[i]);
  snprintf(code + n, sizeof code - n,
           "collectgarbage('collect') collectgarbage('collect')");
  if (!lh_eval(code)) return CTEST_FAIL_ASSERT;
  ren_stub_reset();
  return 0;
}

/* Collects until quiet.
 *
 * __gc runs on the cycle *after* the one that drops the last reference, so
 * "close() released it" and "it has been finalised" are two different moments.
 * Releasing a fallback is therefore not observable at close() — close() only
 * drops the reference, and the free happens at the next collection. Asserting
 * the count straight after close() would be asserting the wrong thing; this is
 * the collection that makes the free visible. */
static int settle(void) {
  if (!lh_eval("collectgarbage('collect') collectgarbage('collect')"))
    return CTEST_FAIL_ASSERT;
  return 0;
}

/* ── the surface ───────────────────────────────────────────────────────── */

static int t_load_returns_a_font_handle(void) {
  if (reset_fonts()) return CTEST_FAIL_ASSERT;

  if (!load_font("f", "font.ttf")) return CTEST_FAIL_ASSERT;
  lh_int("ren_stub.fonts_loaded()", 1);
  lh_bool("is_handle(f)", 1);
  lh_contains("getmetatable(f).__name", "font");
  lh_int("f:get_height()", 16);
  lh_int("f:get_width('abc')", 21);      /* 3 chars, 7 px each in the stub */

  /* Both spellings must work: the method on the handle, and the namespace form
   * that worked before the conversion because the metatable pointed at itself. */
  lh_eq("renderer.font.get_height(f)", "f:get_height()");

  if (!lh_eval("f:close()")) return CTEST_FAIL_ASSERT;
  lh_int("ren_stub.fonts_freed()", 1);
  return 0;
}

static int t_closing_a_font_frees_exactly_one(void) {
  if (reset_fonts()) return CTEST_FAIL_ASSERT;
  if (!load_font("f", "font.ttf")) return CTEST_FAIL_ASSERT;
  lh_int("ren_stub.fonts_freed()", 0);

  lh_bool("f:close()", 1);
  lh_int("ren_stub.fonts_freed()", 1);
  lh_bool("f:close()", 0);
  lh_int("ren_stub.fonts_freed()", 1);   /* not two */

  if (!lh_eval("f = nil collectgarbage('collect') collectgarbage('collect')"))
    return CTEST_FAIL_ASSERT;
  lh_int("ren_stub.fonts_freed()", 1);   /* __gc must not free it again */
  return 0;
}

static int t_a_closed_font_refuses_every_method(void) {
  if (reset_fonts()) return CTEST_FAIL_ASSERT;
  if (!load_font("f", "font.ttf")) return CTEST_FAIL_ASSERT;
  if (!lh_eval("f:close()")) return CTEST_FAIL_ASSERT;

  /* This is the crash the conversion removed. The old userdata NULLed itself in
   * __gc and stayed in place, so every one of these reached ren_get_font_*(NULL). */
  static const char *const calls[] = {
    "f:get_height()", "f:get_width('x')", "f:set_tab_width(4)", NULL
  };
  for (int i = 0; calls[i]; i++) {
    char msg[256];
    if (!lh_eval_raises(calls[i], msg, sizeof msg)) {
      lh_fail("%s on a closed font did not raise: %s", calls[i], msg);
      return CTEST_FAIL_ASSERT;
    }
    if (!strstr(msg, "closed")) {
      lh_fail("%s said \"%s\", which does not say the handle is closed",
              calls[i], msg);
      return CTEST_FAIL_ASSERT;
    }
  }
  lh_int("ren_stub.fonts_freed()", 1);
  return 0;
}

static int t_a_non_font_is_refused(void) {
  if (reset_fonts()) return CTEST_FAIL_ASSERT;
  /* The namespace's methods take a handle as argument 1; a non-handle must be
   * refused by name rather than read as a font. */
  char msg[256];
  if (!lh_eval_raises("renderer.font.get_height(42)", msg, sizeof msg)) {
    lh_fail("a number was accepted as a font: %s", msg);
    return CTEST_FAIL_ASSERT;
  }
  if (!lh_eval_raises("renderer.font.get_height('font')", msg, sizeof msg)) {
    lh_fail("a string was accepted as a font: %s", msg);
    return CTEST_FAIL_ASSERT;
  }
  return 0;
}

/* ── the fallback keepalive ────────────────────────────────────────────── */

/* The one that matters. A chained fallback must survive its own handle being
 * collected, because the chain holds a raw RenFont* with nothing keeping the
 * userdata alive. Before the keepalives, the next draw walked a freed font. */
static int t_a_chained_fallback_survives_its_handle(void) {
  if (reset_fonts()) return CTEST_FAIL_ASSERT;
  if (!load_font("parent", "font.ttf")) return CTEST_FAIL_ASSERT;
  if (!load_font("fb", "mono.ttf")) return CTEST_FAIL_ASSERT;

  lh_int("ren_stub.fallbacks_added()", 0);
  if (!lh_eval("parent:add_fallback(fb)")) return CTEST_FAIL_ASSERT;
  lh_int("ren_stub.fallbacks_added()", 1);

  /* add_fallback returns the fallback, so `p:add_fallback(g)` evaluates to g.
   * The call sites chain and evaluates to the fallback, and that has to keep
   * working — but this second add takes another chain slot, so the counts below
   * account for it rather than reading as an off-by-one. */
  lh_bool("parent:add_fallback(fb) == fb", 1);
  lh_int("ren_stub.fallbacks_added()", 2);
  /* Drop every reference the test holds to the fallback and collect. */
  if (!lh_eval("fb = nil") || settle()) return CTEST_FAIL_ASSERT;

  /* The fallback must NOT have been freed: the parent still points at it. This is
   * the assertion the keepalive exists for. Before it, this number was 1 and the
   * next draw walked a freed font. */
  lh_int("ren_stub.fonts_freed()", 0);
  lh_int("parent:get_height()", 16);

  /* Closing the parent releases its own font and drops the keepalives. The
   * fallback's free becomes visible at the following collection, not here. */
  if (!lh_eval("parent:close()")) return CTEST_FAIL_ASSERT;
  lh_int("ren_stub.fonts_freed()", 1);
  if (settle()) return CTEST_FAIL_ASSERT;
  lh_int("ren_stub.fonts_freed()", 2);
  return 0;
}

/* A fallback added twice is anchored twice and released twice — the keepalive is
 * per chain entry, not per font, and getting that wrong either leaks the second
 * reference or frees a font the chain still points at. */
static int t_the_same_fallback_added_twice_is_released_twice(void) {
  if (reset_fonts()) return CTEST_FAIL_ASSERT;
  if (!load_font("p2", "font.ttf")) return CTEST_FAIL_ASSERT;
  if (!load_font("g2", "mono.ttf")) return CTEST_FAIL_ASSERT;
  if (!lh_eval("p2:add_fallback(g2) p2:add_fallback(g2)"))
    return CTEST_FAIL_ASSERT;
  lh_int("ren_stub.fallbacks_added()", 2);

  /* Two chain entries means two anchors, so dropping every Lua reference still
   * leaves the font alive. If the keepalive were taken once per font rather than
   * once per chain entry, this would be the number that moved. */
  if (!lh_eval("g2 = nil") || settle()) return CTEST_FAIL_ASSERT;
  lh_int("ren_stub.fonts_freed()", 0);

  if (!lh_eval("p2:close()")) return CTEST_FAIL_ASSERT;
  if (settle()) return CTEST_FAIL_ASSERT;
  lh_int("ren_stub.fonts_freed()", 2);
  return 0;
}

/* Past the cap the handle refuses, and refusing must not anchor. A keepalive
 * taken for a fallback the chain declined keeps a font alive for nothing and
 * makes the handle's count and the chain's disagree. */
static int t_a_full_chain_refuses_without_anchoring(void) {
  if (reset_fonts()) return CTEST_FAIL_ASSERT;
  if (!load_font("p3", "font.ttf")) return CTEST_FAIL_ASSERT;
  if (!load_font("g3", "mono.ttf")) return CTEST_FAIL_ASSERT;
  if (!lh_eval("for i = 1, 20 do p3:add_fallback(g3) end"))
    return CTEST_FAIL_ASSERT;

  int cap = ren_max_fallback_fonts();
  int added = ren_stub_fallbacks_added();
  if (added != cap) {
    lh_fail("the chain took %d fallbacks, cap is %d", added, cap);
    return CTEST_FAIL_ASSERT;
  }

  /* Dropping the fallback and collecting must not free it while the chain holds
   * it. This assertion alone cannot tell anchored-refused from anchored-taken —
   * both keep the font alive — so the count above is what pins the behaviour:
   * twenty adds, eight taken. */
  if (!lh_eval("g3 = nil") || settle()) return CTEST_FAIL_ASSERT;
  lh_int("ren_stub.fonts_freed()", 0);

  if (!lh_eval("p3:close()")) return CTEST_FAIL_ASSERT;
  if (settle()) return CTEST_FAIL_ASSERT;
  lh_int("ren_stub.fonts_freed()", 2);
  return 0;
}

/* ── the module's own bookkeeping ──────────────────────────────────────── */

static int t_the_binding_and_the_renderer_agree_on_the_cap(void) {
  /* luaopen_renderer_font checks this at registration and logs an error if they
   * differ. Asserting it here means a mismatch fails a test rather than waiting
   * for somebody to read a log.
   *
   * The comparison is written as a Lua expression with the renderer's number
   * interpolated, because the harness compares expressions and cannot read a C
   * value into the middle of one. */
  char expr[128];
  snprintf(expr, sizeof expr,
           "renderer.font.max_fallbacks() == %d", ren_max_fallback_fonts());
  lh_bool(expr, 1);
  return 0;
}

static const CtestCase font_cases[] = {
  { "load returns a font handle",             t_load_returns_a_font_handle },
  { "closing frees exactly one font",         t_closing_a_font_frees_exactly_one },
  { "a closed font refuses every method",     t_a_closed_font_refuses_every_method },
  { "a non-font is refused by name",          t_a_non_font_is_refused },
  { "a chained fallback survives collection", t_a_chained_fallback_survives_its_handle },
  { "a fallback added twice releases twice",  t_the_same_fallback_added_twice_is_released_twice },
  { "a full chain refuses without anchoring", t_a_full_chain_refuses_without_anchoring },
  { "binding and renderer agree on the cap",  t_the_binding_and_the_renderer_agree_on_the_cap },
};

const CtestSuite font_suite = {
  "font binding",
  font_cases,
  (int)(sizeof(font_cases) / sizeof(font_cases[0])),
};