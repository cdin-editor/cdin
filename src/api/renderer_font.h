/* The font binding's Lua surface, as seen from C.
 *
 * A real header rather than the local extern that renderer_compat.c used to
 * carry, because there is now a second caller — the test suite — and a
 * declaration duplicated in two places is a declaration that will be wrong in one.
 */

#ifndef CDIN_API_RENDERER_FONT_H
#define CDIN_API_RENDERER_FONT_H

#include <lua.h>

/* Builds the `renderer.font` namespace and registers the font handle type.
 * Pushes one value: the namespace table. */
int luaopen_renderer_font(lua_State *L);

#endif /* CDIN_API_RENDERER_FONT_H */