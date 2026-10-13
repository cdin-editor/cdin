#ifndef API_H
#define API_H

#include <lua.h>
#include <lauxlib.h>
#include <lualib.h>

typedef struct RenFont RenFont;

/* The font handle's type name.
 *
 * This used to be "Font" and to name a metatable that only the font module
 * knew about. It is now the handle convention's type name, so the metatable is
 * "cdin.handle/font" and an error says "expected a font handle, got a surface".
 * Nothing outside this repository could have depended on the old spelling — the
 * extension contract does not name it — but code reading getmetatable(f).__name
 * would see the new value, which is a change worth stating rather than assuming
 * nobody looks.
 *
 * It lives here because two translation units need it, and a name that two files
 * can disagree about is exactly the bug that just happened: renderer_compat.c
 * kept checking the old metatable and the draw path raised on the first frame. */
#define API_TYPE_FONT "font"

/* The RenFont in the font handle at `idx`.
 *
 * Raises unless the value is a live font handle, so there is no NULL for the
 * caller to check — the error is already on its way out. Every function that
 * takes a font goes through here rather than reaching into the userdata itself, so
 * "is this a live font?" is answered in one place and cannot drift.
 *
 * This is the hot path (once per drawn string), so it is one compare of an
 * interned string plus the handle header read — no allocation, no lookup.
 */
RenFont *api_check_font(lua_State *L, int idx);

void api_load_libs(lua_State *L);

#endif