/* The bridge from Lua to the code under test, for the handle and error suites.
 *
 * Every function here is a thin forwarder: it takes Lua arguments, calls the
 * handle or error function, and returns whatever that function put on the stack.
 * There is no logic in this file on purpose — the tests are about the convention,
 * and a bridge that made decisions would be a second implementation of it.
 *
 * The forwarders exist because the code under test is C: there is no other way to
 * reach cdin_handle_check from a Lua chunk, and driving the suites from Lua is
 * what makes __gc, __close and __tostring testable at all.
 *
 * Ownership: nothing here owns anything. The handle is Lua's userdata; the
 * destructor counters are statics written only from the main thread.
 */

#include <stdio.h>
#include <string.h>

#include <lauxlib.h>
#include <lua.h>

#include "../../src/api/renderer_font.h"
#include "../../src/lua/error.h"
#include "../../src/lua/handle.h"

int ren_stub_fonts_loaded(void);
int ren_stub_fonts_freed(void);
int ren_stub_fallbacks_added(void);
void ren_stub_reset(void);

/* Destructor bookkeeping. Static because there is nowhere to hang state off a C
 * function pointer, and it is only ever touched from the main thread — Lua is
 * single-threaded here (AGENTS.md §2.3), so no lock is needed and none is used. */
static int thing_dtor_calls;
static int other_dtor_calls;
static int thing_dtor_self_null;

static void thing_dtor(lua_State *L, void *self) {
  (void)L;
  thing_dtor_calls++;
  if (self == NULL) thing_dtor_self_null++;
}

static void other_dtor(lua_State *L, void *self) {
  (void)L; (void)self;
  other_dtor_calls++;
}

/* ── forwarders ────────────────────────────────────────────────────────── */

/* make(type) -> handle. cdin_handle_new pushes the userdata, so this returns 1
 * and Lua keeps it. */
static int l_make(lua_State *L) {
  const char *type = luaL_checkstring(L, 1);
  CdinHandleDtor dtor = strcmp(type, "thing") == 0 ? thing_dtor
                     : strcmp(type, "other") == 0 ? other_dtor
                     : NULL;
  cdin_handle_new(L, 32, type, dtor);
  return 1;
}

/* use(h) -> payload, or raises. This is the check a binding does. */
static int l_use(lua_State *L) {
  const char *type = luaL_optstring(L, 2, "thing");
  cdin_handle_check(L, 1, type);
  lua_pushboolean(L, 1);
  return 1;
}

static int l_is(lua_State *L) {
  lua_pushboolean(L, cdin_handle_is(L, 1));
  return 1;
}

static int l_is_of(lua_State *L) {
  const char *type = luaL_checkstring(L, 2);
  lua_pushboolean(L, cdin_handle_is_of(L, 1, type));
  return 1;
}

static int l_close(lua_State *L) {
  lua_pushboolean(L, cdin_handle_close(L, 1));
  return 1;
}

static int l_count(lua_State *L) {
  lua_pushinteger(L, cdin_handle_count(L));
  return 1;
}

static int l_thing_calls(lua_State *L) {
  lua_pushinteger(L, thing_dtor_calls);
  return 1;
}

static int l_other_calls(lua_State *L) {
  lua_pushinteger(L, other_dtor_calls);
  return 1;
}

static int l_thing_calls_null(lua_State *L) {
  lua_pushinteger(L, thing_dtor_self_null);
  return 1;
}

static void reset_counters(void) {
  thing_dtor_calls = 0;
  other_dtor_calls = 0;
  thing_dtor_self_null = 0;
}

/* ── the error convention ──────────────────────────────────────────────── */

/* err(code, detail) -> the error table. The code arrives as a Lua number and is
 * cast to CdinErr; a code outside the enum is passed through deliberately rather
 * than clamped, so the "unknown" path is reachable from a test. */
static int l_err(lua_State *L) {
  int code = (int)luaL_checkinteger(L, 1);
  const char *detail = luaL_optstring(L, 2, NULL);
  CdinErrDetail e = { (CdinErr)code, 0, NULL, 0 };
  return cdin_error_push(L, e, detail);
}

static int l_errf(lua_State *L) {
  int code = (int)luaL_checkinteger(L, 1);
  const char *detail = luaL_checkstring(L, 2);
  CdinErrDetail e = { (CdinErr)code, 0, NULL, 0 };
  return cdin_error_pushf(L, e, "%s", detail);
}

static int l_api_version(lua_State *L) {
  return cdin_api_version(L);
}

static int l_register(lua_State *L) {
  const char *type = luaL_checkstring(L, 1);
  CdinErr e = cdin_handle_register(L, type, NULL, NULL);
  lua_pushinteger(L, (lua_Integer)e);
  return 1;
}

/* ── the stub renderer's counters, reachable from Lua ──────────────────── */

/* A test needs these after a collection, which happens inside a Lua chunk, so
 * reading them from C is not enough — the collection and the assertion have to be
 * in the same chunk. */
static int l_stub_loaded(lua_State *L) {
  lua_pushinteger(L, ren_stub_fonts_loaded());
  return 1;
}

static int l_stub_freed(lua_State *L) {
  lua_pushinteger(L, ren_stub_fonts_freed());
  return 1;
}

static int l_stub_fallbacks(lua_State *L) {
  lua_pushinteger(L, ren_stub_fallbacks_added());
  return 1;
}

static int l_stub_reset(lua_State *L) {
  ren_stub_reset();
  return 0;
}

static const luaL_Reg bridge[] = {
  { "make",                l_make },
  { "use",                 l_use },
  { "is_handle",           l_is },
  { "is_of",               l_is_of },
  { "close_handle",        l_close },
  { "handle_count",        l_count },
  { "thing_calls",         l_thing_calls },
  { "other_calls",         l_other_calls },
  { "thing_calls_null",    l_thing_calls_null },
  { "cdin_err",            l_err },
  { "cdin_errf",           l_errf },
  { "cdin_api_version",    l_api_version },
  { "register_type",       l_register },
  { NULL, NULL },
};

/* Registers the bridge as the global table H, and the two demo types.
 *
 * One table rather than a dozen globals: the bridge's names are generic enough
 * ("make", "use", "close") that spraying them into the global namespace would
 * shadow whatever a real module puts there, and a test suite that can do that to
 * the state it shares is a test suite that will eventually do it.
 */
void stub_handle_lua_init(lua_State *L) {
  luaL_newlib(L, bridge);
  lua_setglobal(L, "H");

  cdin_handle_init(L);
  cdin_handle_register(L, "thing", thing_dtor, NULL);
  cdin_handle_register(L, "other", other_dtor, NULL);

  /* The real font binding, against the stub renderer. Not a stub of the binding:
   * what is under test IS the binding, and a stand-in for it would test the
   * stand-in. The renderer underneath is stubbed, because the parts being tested
   * are the handle, the keepalives and the argument checking — none of which
   * need SDL.
   *
   * Wired as `renderer.font`, the same shape the editor uses, so the tests spell
   * their calls the way the runtime does. */
  lua_newtable(L);
  luaopen_renderer_font(L);       /* pushes the namespace */
  lua_setfield(L, -2, "font");
  lua_setglobal(L, "renderer");

  /* The stub renderer's counters, so a test can read them from Lua rather than
   * only from C — which is what lets a test assert after a collection. */
  lua_newtable(L);
  lua_pushcfunction(L, l_stub_loaded);
  lua_setfield(L, -2, "fonts_loaded");
  lua_pushcfunction(L, l_stub_freed);
  lua_setfield(L, -2, "fonts_freed");
  lua_pushcfunction(L, l_stub_fallbacks);
  lua_setfield(L, -2, "fallbacks_added");
  lua_pushcfunction(L, l_stub_reset);
  lua_setfield(L, -2, "reset");
  lua_setglobal(L, "ren_stub");

  reset_counters();
}

void stub_handle_lua_reset(void) { reset_counters(); }