/* A Lua-state harness for the C tests that need one.
 *
 * The first test binary deliberately links no Lua, so that testing a module in
 * isolation does not require Lua to be present and correct. The handle and error
 * conventions are the exception: the thing under test is the binding, and a stub
 * would be testing the stub. So this file provides just enough Lua to drive them —
 * a state, an assertion helper callable from C, and an evaluation helper — and no
 * more.
 *
 * Ownership: the harness owns the lua_State for the life of the process. Every
 * suite runs against the same state, so a handle left open by one case is visible
 * to the next as a non-zero cdin_handle_count — which is why the suites assert on
 * the count and not only on their own objects.
 *
 * The assertion helpers return a failure code rather than calling exit, so a case
 * can report several failures before the runner gives up on it. That matters here
 * because a broken invariant tends to break several assertions at once, and a
 * runner that stops at the first tells you one of the symptoms.
 */

#include "lua_harness.h"

#include <stdio.h>
#include <string.h>

#include <lauxlib.h>
#include <lua.h>
#include <lualib.h>

static lua_State *L;
static int failures;
static char last_msg[512];

const char *lh_error(void) { return last_msg; }
int lh_failures(void) { return failures; }

int lh_init(void) {
  L = luaL_newstate();
  if (!L) {
    snprintf(last_msg, sizeof last_msg, "luaL_newstate failed");
    return 0;
  }
  luaL_openlibs(L);
  failures = 0;
  last_msg[0] = '\0';
  return 1;
}

void lh_close(void) {
  if (!L) return;
  /* Deliberately not lua_close yet: a handle the suites forgot to close would be
   * collected here, running its destructor for the first time, and its effects
   * would arrive after the summary. The runner reports the count instead, which is
   * the thing worth reporting — so the state is simply dropped at exit. */
  L = NULL;
}

lua_State *lh_state(void) { return L; }

/* ── assertions, callable from C ───────────────────────────────────────── */

/* Runs a Lua chunk and records whether it raised. `code` must be a complete
 * chunk. Returns 1 if it ran without raising. */
int lh_eval(const char *code) {
  if (luaL_dostring(L, code) != LUA_OK) {
    failures++;
    snprintf(last_msg, sizeof last_msg, "lua error: %s",
             lua_tostring(L, -1) ? lua_tostring(L, -1) : "(no message)");
    lua_pop(L, 1);
    return 0;
  }
  return 1;
}

/* Evaluates `code` and requires it to raise. Returns 1 if it raised, and copies
 * the message out for the caller to inspect with lh_last_error. */
int lh_eval_raises(const char *code, char *out, size_t cap) {
  if (luaL_dostring(L, code) != LUA_OK) {
    const char *msg = lua_tostring(L, -1);
    snprintf(out, cap, "%s", msg ? msg : "");
    lua_pop(L, 1);
    return 1;
  }
  snprintf(out, cap, "%s", "<no error raised>");
  return 0;
}

/* Requires a global to be a boolean equal to `want`. */
int lh_bool(const char *expr, int want) {
  char code[256];
  snprintf(code, sizeof code, "return (%s) == true", expr);
  luaL_dostring(L, code);
  int got = lua_toboolean(L, -1);
  lua_pop(L, 1);
  if (got != want) {
    failures++;
    snprintf(last_msg, sizeof last_msg,
             "%s: got %s, want %s", expr, got ? "true" : "false",
             want ? "true" : "false");
    return 0;
  }
  return 1;
}

/* Requires a global expression to equal an integer. */
int lh_int(const char *expr, long long want) {
  char code[256];
  snprintf(code, sizeof code, "return tonumber(%s)", expr);
  luaL_dostring(L, code);
  int isnum = lua_isnumber(L, -1);
  long long got = isnum ? (long long)lua_tointeger(L, -1) : 0;
  lua_pop(L, 1);
  if (!isnum || got != want) {
    failures++;
    snprintf(last_msg, sizeof last_msg, "%s: got %lld, want %lld",
             expr, got, want);
    return 0;
  }
  return 1;
}

/* Requires two expressions to be equal as numbers. */
int lh_eq(const char *a, const char *b) {
  char code[320];
  snprintf(code, sizeof code, "return (%s) == (%s)", a, b);
  luaL_dostring(L, code);
  int got = lua_toboolean(L, -1);
  lua_pop(L, 1);
  if (!got) {
    failures++;
    snprintf(last_msg, sizeof last_msg, "%s == %s  (not equal)", a, b);
    return 0;
  }
  return 1;
}

/* Requires a string expression to contain a substring. */
int lh_contains(const char *haystack_expr, const char *needle) {
  char code[320];
  snprintf(code, sizeof code, "return string.find(tostring(%s), %s, 1, true) ~= nil",
           haystack_expr, needle);
  luaL_dostring(L, code);
  int got = lua_toboolean(L, -1);
  lua_pop(L, 1);
  if (!got) {
    failures++;
    snprintf(last_msg, sizeof last_msg, "%s does not contain %s",
             haystack_expr, needle);
    return 0;
  }
  return 1;
}

void lh_fail(const char *fmt, ...) {
  va_list ap;
  va_start(ap, fmt);
  failures++;
  vsnprintf(last_msg, sizeof last_msg, fmt, ap);
  va_end(ap);
}

int lh_failed(void) { return failures; }