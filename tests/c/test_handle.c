/* Handle convention and error convention, driven through a real lua_State.
 *
 * Why a separate binary with Lua linked: the main test runner deliberately links
 * no Lua so that a module can be tested in isolation, and the thing under test
 * here is the binding itself — the metatable, __gc, close(), the error table. A
 * stubbed host would be testing the stub.
 *
 * Why driven through Lua chunks rather than by calling the C functions from C:
 * __gc, __close and __tostring are metamethods. Calling cdin_handle_new directly
 * proves the allocation works and proves nothing about whether the destructor
 * runs when the userdata becomes unreachable, which is the property the whole
 * convention exists for.
 *
 * Ordering matters and is the reason the type-table case is last: it exhausts the
 * fixed type table for the whole process, so anything registering a type after it
 * would fail for a reason that has nothing to do with the test.
 *
 * The runner prints the handle count at the end, so a handle leaked by any case
 * shows up as a number that did not return to zero rather than as a mysterious
 * failure somewhere else.
 */

#include <stdio.h>
#include <string.h>

#include <lauxlib.h>
#include <lua.h>

#include "../../src/lua/error.h"
#include "../../src/lua/handle.h"
#include "ctest.h"
#include "lua_harness.h"

void stub_handle_lua_init(lua_State *L);
void stub_handle_lua_reset(void);

/* ── construction and recognition ──────────────────────────────────────── */

static int t_new_makes_a_recognisable_handle(void) {
  int before = cdin_handle_count(lh_state());
  if (!lh_eval("h = H.make('thing')")) return CTEST_FAIL_ASSERT;

  lh_bool("H.is_handle(h)", 1);
  lh_int("H.handle_count()", before + 1);
  lh_contains("getmetatable(h).__type", "thing");
  lh_contains("getmetatable(h).__name", "cdin.handle/thing");
  lh_bool("H.use(h)", 1);

  if (!lh_eval("h:close()")) return CTEST_FAIL_ASSERT;
  lh_int("H.handle_count()", before);
  return 0;
}

static int t_non_handles_are_rejected_without_raising(void) {
  /* cdin_handle_is must be safe on anything: a binding calls it on an argument
   * it has not type-checked yet. */
  lh_bool("H.is_handle(42)", 0);
  lh_bool("H.is_handle('a string')", 0);
  lh_bool("H.is_handle({})", 0);
  lh_bool("H.is_handle(nil)", 0);
  lh_bool("H.is_handle(true)", 0);
  lh_bool("H.is_handle(print)", 0);     /* a function is not a handle */
  return 0;
}

static int t_a_foreign_userdata_is_not_a_handle(void) {
  /* The case that separates "is a userdata" from "is one of ours". Checking only
   * for a metatable and stopping there is the bug this catches: any library's
   * userdata would pass, and then a payload would be read at the wrong offset. */
  if (!lh_eval("foreign = io.tmpfile()")) return CTEST_FAIL_ASSERT;
  lh_bool("H.is_handle(foreign)", 0);

  if (!lh_eval("ok = pcall(function() return H.use(foreign) end)"))
    return CTEST_FAIL_ASSERT;
  lh_bool("ok", 0);
  if (!lh_eval("foreign:close()")) return CTEST_FAIL_ASSERT;
  return 0;
}

/* ── type safety ───────────────────────────────────────────────────────── */

static int t_a_wrong_type_is_refused_by_name(void) {
  if (!lh_eval("a = H.make('thing') b = H.make('other')")) return CTEST_FAIL_ASSERT;

  lh_bool("H.is_of(a, 'thing')", 1);
  lh_bool("H.is_of(a, 'other')", 0);
  lh_bool("H.is_of(b, 'other')", 1);

  /* The message must name both types. "expected a thing handle, got a other
   * handle" is a bug report someone can act on; "bad argument #1" is not. */
  char msg[256];
  if (!lh_eval_raises("H.use(a, 'other')", msg, sizeof msg)) {
    lh_fail("check() with the wrong type did not raise: %s", msg);
    return CTEST_FAIL_ASSERT;
  }
  if (!strstr(msg, "thing") || !strstr(msg, "other")) {
    lh_fail("the type error does not name both types: \"%s\"", msg);
    return CTEST_FAIL_ASSERT;
  }

  if (!lh_eval("a:close() b:close()")) return CTEST_FAIL_ASSERT;
  return 0;
}

/* ── closing ───────────────────────────────────────────────────────────── */

static int t_close_runs_the_destructor_exactly_once(void) {
  stub_handle_lua_reset();
  if (!lh_eval("c = H.make('thing')")) return CTEST_FAIL_ASSERT;
  lh_int("H.thing_calls()", 0);

  lh_bool("c:close()", 1);
  lh_int("H.thing_calls()", 1);
  lh_int("H.thing_calls_null()", 0);   /* the destructor got a real payload */

  /* Idempotent. Closing in an error path while __gc closes afterwards is the
   * normal sequence, so a second close must be a no-op rather than an error. */
  lh_bool("c:close()", 0);
  lh_int("H.thing_calls()", 1);
  lh_bool("c:close()", 0);
  lh_int("H.thing_calls()", 1);

  /* And a collection afterwards must not run it again. */
  if (!lh_eval("c = nil collectgarbage('collect') collectgarbage('collect')"))
    return CTEST_FAIL_ASSERT;
  lh_int("H.thing_calls()", 1);
  return 0;
}

static int t_a_closed_handle_is_detectable_not_dangling(void) {
  stub_handle_lua_reset();
  if (!lh_eval("d = H.make('thing') d:close()")) return CTEST_FAIL_ASSERT;

  /* Still a handle — so tostring and the type are still available — but not a
   * live one, so is_of says no. */
  lh_bool("H.is_handle(d)", 1);
  lh_bool("H.is_of(d, 'thing')", 0);
  lh_contains("tostring(d)", "closed");

  char msg[256];
  if (!lh_eval_raises("H.use(d)", msg, sizeof msg)) {
    lh_fail("using a closed handle did not raise: %s", msg);
    return CTEST_FAIL_ASSERT;
  }
  if (!strstr(msg, "closed")) {
    lh_fail("the closed-handle error does not say it is closed: \"%s\"", msg);
  }
  if (!lh_eval("d = nil")) return CTEST_FAIL_ASSERT;
  return 0;
}

static int t_a_to_be_closed_variable_closes_at_scope_exit(void) {
  stub_handle_lua_reset();
  /* The <close> attribute, not a plain local. A plain `local x = handle` does
   * NOT run __close at scope exit — only a to-be-closed variable does — so the
   * first version of this case asserted the destructor ran and it did not,
   * because the test was exercising Lua's rule rather than the convention. */
  if (!lh_eval(
        "do\n"
        "  local scoped <close> = H.make('thing')\n"
        "end\n")) {
    return CTEST_FAIL_ASSERT;
  }
  /* Lua 5.4+ runs __close when the scope ends, normally and on error. Without it
   * the destructor waits for a collection, which is a different contract from the
   * one the header promises and one a caller closing in a loop would notice as
   * latency. */
  lh_int("H.thing_calls()", 1);

  /* And a plain local does NOT close, which is the other half of the rule and
   * worth pinning: if it ever did, a handle held in an ordinary local would be
   * destroyed while still reachable. */
  stub_handle_lua_reset();
  if (!lh_eval("do local plain = H.make('thing') end")) return CTEST_FAIL_ASSERT;
  lh_int("H.thing_calls()", 0);
  if (!lh_eval("collectgarbage('collect') collectgarbage('collect')"))
    return CTEST_FAIL_ASSERT;
  lh_int("H.thing_calls()", 1);
  return 0;
}

static int t_tostring_identifies_a_handle_and_says_whether_it_is_closed(void) {
  if (!lh_eval("e = H.make('thing')")) return CTEST_FAIL_ASSERT;

  /* Live: names the type, and says nothing about being closed. Printing
   * "(closed)" on an open handle is worse than having no __tostring at all — it
   * teaches a reader to ignore the word, so the one time it matters is the one
   * time they do not. This case exists because it shipped that way once. */
  lh_contains("tostring(e)", "thing");
  lh_bool("a live handle does not claim to be closed: "
          " && tostring(e):find('closed', 1, true) == nil", 1);

  if (!lh_eval("e:close()")) return CTEST_FAIL_ASSERT;
  lh_contains("tostring(e)", "closed");
  lh_contains("tostring(e)", "thing");
  return 0;
}

/* ── collection ────────────────────────────────────────────────────────── */

static int t_gc_runs_the_destructor(void) {
  stub_handle_lua_reset();
  /* Settle first. A handle an earlier case left unreachable is collected during
   * this case, decrements the count at a moment this case is not watching, and the
   * arithmetic below then blames this case for it. The precondition is stated
   * rather than assumed. */
  if (!lh_eval("collectgarbage('collect') collectgarbage('collect')"))
    return CTEST_FAIL_ASSERT;
  int before = cdin_handle_count(lh_state());

  if (!lh_eval("tmp = H.make('thing')")) return CTEST_FAIL_ASSERT;
  lh_int("H.handle_count()", before + 1);

  if (!lh_eval("tmp = nil collectgarbage('collect') collectgarbage('collect')"))
    return CTEST_FAIL_ASSERT;
  lh_int("H.thing_calls()", 1);
  lh_int("H.handle_count()", before);
  return 0;
}

static int t_each_type_gets_its_own_destructor(void) {
  stub_handle_lua_reset();
  if (!lh_eval("x = H.make('thing') y = H.make('other')")) return CTEST_FAIL_ASSERT;

  if (!lh_eval("x:close()")) return CTEST_FAIL_ASSERT;
  lh_int("H.thing_calls()", 1);
  lh_int("H.other_calls()", 0);      /* closing a thing must not close an other */

  if (!lh_eval("y:close()")) return CTEST_FAIL_ASSERT;
  lh_int("H.other_calls()", 1);
  lh_int("H.thing_calls()", 1);
  return 0;
}

/* ── the type table's limit ────────────────────────────────────────────── */

static int t_the_type_table_reports_its_limit(void) {
  /* Last case on purpose: this exhausts the process-wide type table, so anything
   * registering a type afterwards would fail for an unrelated reason. */
  int got_limit = 0;
  for (int i = 0; i < CDIN_HANDLE_MAX_TYPES + 8; i++) {
    char name[64];
    snprintf(name, sizeof name, "filler_%d", i);
    CdinErr e = cdin_handle_register(lh_state(), name, NULL, NULL);
    if (e == CDIN_ERR_LIMIT) {
      got_limit = 1;
      /* And it must keep refusing, rather than half-admitting types and leaving
       * a table the caller cannot reason about. */
      char more[64];
      snprintf(more, sizeof more, "filler_again_%d", i);
      if (cdin_handle_register(lh_state(), more, NULL, NULL) != CDIN_ERR_LIMIT) {
        lh_fail("registration succeeded after the limit had been reported");
        return CTEST_FAIL_ASSERT;
      }
      break;
    }
    if (e != CDIN_OK) {
      lh_fail("registration failed with %d before reaching the limit", (int)e);
      return CTEST_FAIL_ASSERT;
    }
  }
  if (!got_limit) {
    lh_fail("the type table never reported its limit at %d types",
            CDIN_HANDLE_MAX_TYPES);
    return CTEST_FAIL_ASSERT;
  }
  return 0;
}

/* ── the error convention ──────────────────────────────────────────────── */

static int t_the_error_table_has_the_agreed_shape(void) {
  if (!lh_eval("e = H.cdin_err(1, 'a detail')")) return CTEST_FAIL_ASSERT;
  lh_contains("e.code", "invalid");
  lh_contains("e.name", "invalid");
  lh_eq("e.detail", "'a detail'");
  lh_bool("type(e.line) == 'number'", 1);
  lh_bool("type(e.os) == 'number'", 1);

  /* A code outside the enum must not read past the name table. */
  if (!lh_eval("bogus = H.cdin_err(9999, nil)")) return CTEST_FAIL_ASSERT;
  lh_eq("bogus.code", "'unknown'");
  return 0;
}

static int t_an_error_detail_is_always_a_string(void) {
  /* nil and "" are different facts, and a caller that cannot tell them apart
   * prints "" for both — so the field exists either way and says which. */
  if (!lh_eval(
        "a = H.cdin_err(2)\n"
        "b = H.cdin_err(2, '')")) {
    return CTEST_FAIL_ASSERT;
  }
  lh_bool("type(a.detail) == 'string'", 1);
  lh_bool("type(b.detail) == 'string'", 1);
  lh_bool("a.detail == ''", 1);
  return 0;
}

static int t_a_formatted_detail_is_bounded_and_says_so(void) {
  /* A very long detail must be cut, and the cut must be visible. A silently
   * shortened path is how someone ends up looking in the wrong directory. */
  if (!lh_eval("f = H.cdin_errf(3, string.rep('x', 4000))")) return CTEST_FAIL_ASSERT;
  lh_bool("#f.detail < 600", 1);
  lh_contains("f.detail", "...");
  return 0;
}

static int t_api_version_is_a_number(void) {
  lh_bool("type(H.cdin_api_version()) == 'number'", 1);
  lh_int("H.cdin_api_version()", CDIN_API_VERSION);
  lh_bool("H.cdin_api_version() >= 1", 1);
  return 0;
}

static const CtestCase handle_cases[] = {
  { "new makes a recognisable handle",        t_new_makes_a_recognisable_handle },
  { "non-handles are rejected, not raised",   t_non_handles_are_rejected_without_raising },
  { "a foreign userdata is not a handle",     t_a_foreign_userdata_is_not_a_handle },
  { "a wrong type is refused by name",        t_a_wrong_type_is_refused_by_name },
  { "close runs the destructor exactly once", t_close_runs_the_destructor_exactly_once },
  { "a closed handle is detectable",          t_a_closed_handle_is_detectable_not_dangling },
  { "to-be-closed closes at scope exit",     t_a_to_be_closed_variable_closes_at_scope_exit },
  { "tostring names the handle and its state", t_tostring_identifies_a_handle_and_says_whether_it_is_closed },
  { "gc runs the destructor",                 t_gc_runs_the_destructor },
  { "each type gets its own destructor",      t_each_type_gets_its_own_destructor },
  { "the type table reports its limit",       t_the_type_table_reports_its_limit },
  { "the error table has the agreed shape",   t_the_error_table_has_the_agreed_shape },
  { "an error detail is always a string",     t_an_error_detail_is_always_a_string },
  { "a formatted detail is bounded",          t_a_formatted_detail_is_bounded_and_says_so },
  { "api_version is a number",                t_api_version_is_a_number },
};

const CtestSuite handle_suite = {
  "handle + error",
  handle_cases,
  (int)(sizeof(handle_cases) / sizeof(handle_cases[0])),
};