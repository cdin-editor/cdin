/* The `renderer.font` binding: a namespace table plus a font handle.
 *
 * Converted to the handle convention (src/lua/handle.h). What that bought, and
 * what it did not:
 *
 * It bought closed detection. The userdata used to hold a `RenFont *` that __gc
 * NULLed, so any call after collection reached `ren_get_font_size(NULL)` — a
 * dereference of a null pointer, reported by the user as "the editor crashed
 * when I closed a file", with nothing in the log to explain it. Now the handle
 * remembers that it is closed and check() raises "font handle is closed".
 *
 * It did NOT fix the fallback chain. ren_font_add_fallback stores a raw
 * `RenFont *` in font->fallback[], so a fallback whose handle is collected leaves
 * the chain holding a freed pointer. That is a reference problem rather than a
 * lifetime-of-the-userdata problem, and the convention does not reach it. It
 * needs the parent handle to keep its fallbacks alive, which is a design change
 * to the payload and to the registry's reference rules — reported under OPEN
 * rather than half-built here.
 *
 * The Lua-visible surface is unchanged. `renderer.font` used to BE the metatable,
 * with __index pointing at itself, so both `renderer.font.load(p, s)` and
 * `renderer.font.set_tab_width(f, n)` worked. It is now a plain table carrying
 * `load` plus every method, and the handle's metatable carries the same methods
 * on __index — so `f:set_tab_width(n)`, `renderer.font.set_tab_width(f, n)` and
 * `renderer.font.load(p, s)` all still work, and the methods read their handle
 * from argument 1 either way.
 */

#include "api.h"
#include "renderer_font.h"
#include "../ui/renderer.h"
#include "../ui/renderer_cache.h"
#include "../core/logger.h"
#include "../base/error.h"
#include "../lua/error.h"
#include "../lua/handle.h"

/* The handle type name. Short, lowercase, and not the old "Font": it becomes the
 * metatable name ("cdin.handle/font") and part of every error message, so it is
 * written the way the rest of this file spells things. The Lua-visible metatable
 * name is not part of the extension contract, so this is not a contract change —
 * but it IS visible to code that reads getmetatable(f).__name, and that code
 * would see "cdin.handle/font" instead of nothing. */
#define FONT_TYPE "font"

/* ── the handle ────────────────────────────────────────────────────────── */

/* How many fallbacks a font can hold. Matches MAX_FALLBACK_FONTS in
 * src/ui/renderer.c, and has to: ren_font_add_fallback refuses past its own
 * bound, so a smaller number here would anchor fallbacks the chain never took
 * and a larger one would let the handle claim to anchor a chain that is already
 * full. Two constants that must agree is a thing to state rather than discover,
 * so the mismatch is checked at runtime below. */
#define FONT_MAX_FALLBACKS 8

/* The handle payload.
 *
 * `font` is the renderer object; `keepalive` holds one Lua registry reference
 * per fallback, released by the destructor.
 *
 * The keepalive list exists because ren_font_add_fallback stores a raw
 * `RenFont *` in font->fallback[]. That is a C pointer with no reference to the
 * Lua userdata behind it, so a fallback whose handle is collected leaves the
 * chain holding a freed pointer — and the next draw walks it. data/core/style.lua
 * happens to keep its fallbacks in a global table, so the shipped runtime is
 * safe; but that makes correctness depend on every caller remembering, which is
 * exactly the property that disappears in a refactor. Anchoring here means the
 * chain is safe because of how the handle works, not because of what callers do.
 *
 * A registry reference rather than storing the userdata: a Lua value cannot be
 * held in C memory without being rooted somewhere, and the registry is the place
 * designed for exactly that. LUA_NOREF is the empty slot — 5.4's name for it was
 * LUA_NOREF, and luaL_ref dropped its table argument in 5.5, so both spellings
 * here are the 5.5 ones and neither is available in 5.4. */
typedef struct {
  RenFont *font;
  int      keepalive[FONT_MAX_FALLBACKS];   /* LUA_NOREF when unused */
} FontHandle;

/* Releases the font through the damage cache, which defers the actual free to the
 * end of the frame — a font may still be in a queued draw command when Lua drops
 * it, so freeing here would be a use-after-free.
 *
 * Runs once, from close() or __gc. Drops the keepalives first, so a fallback is
 * not anchored by a handle that is going away, and NULLs the pointer so a second
 * call cannot double-free even if the convention ever changes. */
static void font_dtor(lua_State *L, void *self) {
  FontHandle *h = (FontHandle *)self;
  if (!h) return;

  for (int i = 0; i < FONT_MAX_FALLBACKS; i++) {
    if (h->keepalive[i] != LUA_NOREF) {
      luaL_unref(L, LUA_REGISTRYINDEX, h->keepalive[i]);
      h->keepalive[i] = LUA_NOREF;
    }
  }

  if (h->font) {
    log_debug("renderer.font: releasing font (size=%.1f)",
              ren_get_font_size(h->font));
    rencache_free_font(h->font);
    h->font = NULL;
  }
}

/* The font in the handle at `idx`.
 *
 * check() raises on anything that is not a live font handle, so there is no NULL
 * to test here: the function cannot return without either a font or an error
 * already on its way out. */
static FontHandle *handle_at(lua_State *L, int idx) {
  return (FontHandle *)cdin_handle_check(L, idx, FONT_TYPE);
}

static RenFont *font_at(lua_State *L, int idx) {
  return handle_at(L, idx)->font;
}

/* The one way other translation units get a font out of a handle.
 *
 * Exists so the draw path in renderer_compat.c goes through the convention
 * rather than reaching into the userdata with its own idea of what a font is.
 * When it did the latter, with the previous metatable name, the editor panicked
 * on the first frame — which is what a second implementation of a convention
 * looks like from the inside. */
RenFont *api_check_font(lua_State *L, int idx) {
  return font_at(L, idx);
}

static int f_load(lua_State *L) {
  const char *filename = luaL_checkstring(L, 1);
  float size           = (float)luaL_checknumber(L, 2);
  log_debug("renderer.font: load(\"%s\", %.1f)", filename, size);

  /* The handle exists before the font does, so a failed load leaves a handle with
   * a null font rather than a userdata with a NULL in it — and the destructor has
   * nothing to release, which is correct. */
  FontHandle *h = (FontHandle *)cdin_handle_new(L, sizeof(FontHandle),
                                                FONT_TYPE, font_dtor);
  if (!h) return 0;   /* cdin_handle_new raised */

  for (int i = 0; i < FONT_MAX_FALLBACKS; i++) h->keepalive[i] = LUA_NOREF;

  h->font = ren_load_font(filename, size);
  if (!h->font) {
    log_error("renderer.font: load(\"%s\") failed", filename);
    /* The uniform error convention, so a caller can branch on the code rather
     * than on the message. Raising is right here: there is no font to return and
     * the caller asked for one. */
    CdinErrDetail e = CDIN_ERR(CDIN_ERR_NOT_FOUND);
    cdin_error_raise(L, e, filename);
    return 0;
  }
  log_info("renderer.font: loaded \"%s\" at %.1fpx (height=%dpx)",
           filename, size, ren_get_font_height(h->font));
  return 1;
}

static int f_set_tab_width(lua_State *L) {
  RenFont *font = font_at(L, 1);
  int n         = (int)luaL_checknumber(L, 2);
  log_trace("renderer.font: set_tab_width(%d)", n);
  ren_set_font_tab_width(font, n);
  return 0;
}

static int f_get_width(lua_State *L) {
  RenFont    *font = font_at(L, 1);
  const char *text = luaL_checkstring(L, 2);
  lua_pushnumber(L, ren_get_font_width(font, text));
  return 1;
}

static int f_get_height(lua_State *L) {
  lua_pushnumber(L, ren_get_font_height(font_at(L, 1)));
  return 1;
}

static int f_add_fallback(lua_State *L) {
  FontHandle *self = handle_at(L, 1);
  RenFont    *fallback = font_at(L, 2);
  log_debug("renderer.font: add_fallback(size=%.1f) -> chain",
            ren_get_font_size(fallback));

  /* Find the slot BEFORE chaining, and refuse if there is none. Anchoring a
   * fallback the chain then declines would keep a font alive for nothing, and
   * worse would let this handle's count and the chain's count disagree, so the
   * next add would anchor something that is not really chained. */
  int slot = -1;
  for (int i = 0; i < FONT_MAX_FALLBACKS; i++) {
    if (self->keepalive[i] == LUA_NOREF) { slot = i; break; }
  }
  if (slot < 0) {
    /* The renderer refuses past MAX_FALLBACK_FONTS too, and logs its own
     * warning; this one is here so the reason is "this handle is full" rather
     * than a silent no-op, and so the two bounds cannot drift apart unnoticed. */
    log_warn("renderer.font: fallback chain full (%d), ignoring additional "
             "fallback font", FONT_MAX_FALLBACKS);
    lua_pushvalue(L, 2);
    return 1;
  }

  ren_font_add_fallback(self->font, fallback);

  /* Take the anchor, then return the anchored value.
   *
   * luaL_ref pops the value it references, so the fallback is no longer at index
   * 2 afterwards and `lua_pushvalue(L, 2)` would read past the top of the stack
   * and return whatever happened to be there — nil on this machine. Reading the
   * value back out of the registry by its own reference sidesteps the index
   * arithmetic entirely, and returns the very object the chain now points at,
   * which is the stronger of the two guarantees.
   *
   * The return value is not cosmetic: the call sites chain, and `f:add_fallback(g)`
   * evaluating to `g` is the documented shape. A test asserts it. */
  self->keepalive[slot] = luaL_ref(L, LUA_REGISTRYINDEX);
  lua_rawgeti(L, LUA_REGISTRYINDEX, self->keepalive[slot]);
  return 1;
}

/* The instance methods. `load` is deliberately absent: it is a constructor, and
 * having it on __index meant `font:load(...)` was reachable and meaningless. It
 * stays on the namespace table below, which is where it was already used from. */
static const luaL_Reg font_methods[] = {
  { "set_tab_width", f_set_tab_width },
  { "get_width",     f_get_width     },
  { "get_height",    f_get_height    },
  { "add_fallback",  f_add_fallback  },
  { NULL, NULL }
};

static int f_max_fallbacks(lua_State *L) {
  /* So the two bounds can be compared rather than trusted. luaopen_renderer_font
   * checks at registration too; this is the same fact available at runtime, for
   * a test or for anything that wants to size a chain. */
  lua_pushinteger(L, FONT_MAX_FALLBACKS);
  return 1;
}

/* Both surfaces, deliberately the same list. The namespace keeps the
 * `renderer.font.method(f, ...)` spelling working, and the handle gets them via
 * __index for `f:method(...)`. Registering two lists and letting them drift is
 * how a method ends up present on one and missing from the other. */
static const luaL_Reg font_namespace[] = {
  { "load",           f_load           },
  { "set_tab_width",  f_set_tab_width  },
  { "get_width",      f_get_width      },
  { "get_height",     f_get_height     },
  { "add_fallback",   f_add_fallback   },
  { "max_fallbacks",  f_max_fallbacks  },
  { NULL, NULL }
};

int luaopen_renderer_font(lua_State *L) {
  log_trace("api: registering Font handle (%s)", FONT_TYPE);

  cdin_handle_init(L);

  /* The two bounds have to agree: this handle anchors one fallback per chain
   * entry, and the renderer caps the chain. Checked once at registration rather
   * than trusted, because the two are in different files and a mismatch would
   * only show up as a chain that refuses an add the handle believed it made. */
  if (ren_max_fallback_fonts() != FONT_MAX_FALLBACKS) {
    log_error("renderer.font: fallback cap mismatch — the handle allows %d, "
              "the renderer allows %d; fallbacks may be anchored for fonts the "
              "chain never took", FONT_MAX_FALLBACKS, ren_max_fallback_fonts());
  }

  /* The handle type, with its metatable. Registered first: a metatable that
   * references the methods before they exist would give an empty __index. */
  cdin_handle_register(L, FONT_TYPE, font_dtor, font_methods);

  /* The namespace. Previously this function returned the metatable with __index
   * pointing at itself, which made `renderer.font.load` work by accident of the
   * constructor sharing the instance table. Now it is an ordinary table and the
   * methods are simply on it. */
  luaL_newlib(L, font_namespace);
  lua_pushvalue(L, -1);
  lua_setfield(L, -2, "__index");   /* renderer.font.load(x) still resolves */
  return 1;
}