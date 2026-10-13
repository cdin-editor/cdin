/* Renderer stand-ins for the damage-cache tests.
 *
 * renderer_cache.c records a frame's draw commands and replays them into the
 * renderer. The real renderer needs SDL, a window and a surface, none of which
 * exist in a unit test, so this provides the renderer symbols the cache calls
 * and nothing else.
 *
 * The point of the free counter: rencache_free_font defers the free to
 * end_frame, and the defect under test is that a font was dropped instead of
 * freed. Counting ren_free_font calls turns "the font was not leaked" from
 * something to reason about into an assertion.
 *
 * The font *lifecycle* — loading, fallback chains — lives in stub_font.c, which
 * only the Lua-boundary binary compiles. This binary links the real
 * renderer_cache.c, so rencache_free_font is defined for real here and defining
 * it again would be a link error.
 *
 * Owned by the test process. All state is static and written only from the
 * single-threaded test runner.
 */

#include <string.h>

#include "../../src/ui/renderer.h"
#include "ctest.h"

static int fonts_freed;
static int rects_drawn;
static int texts_drawn;

int  ren_stub_fonts_freed(void) { return fonts_freed; }
void ren_stub_reset(void) { fonts_freed = rects_drawn = texts_drawn = 0; }


/* ── the damage cache's calls into the renderer ───────────────────────── */

void ren_free_font(RenFont *font) { (void)font; fonts_freed++; }

int  ren_get_font_width(RenFont *font, const char *text) {
  (void)font;
  return text ? (int)strlen(text) * 7 : 0;
}

int  ren_get_font_height(RenFont *font) { (void)font; return 16; }
int  ren_get_font_tab_width(RenFont *font) { (void)font; return 4; }
void ren_set_font_tab_width(RenFont *font, int n) { (void)font; (void)n; }

void ren_get_size(int *x, int *y) { *x = 1920; *y = 1080; }
bool ren_take_surface_replaced(void) { return false; }
void ren_set_clip_rect(RenRect rect) { (void)rect; }
void ren_update_rects(RenRect *rects, int count) { (void)rects; (void)count; }

void ren_draw_rect(RenRect rect, RenColor color) { (void)rect; (void)color; rects_drawn++; }
int  ren_draw_text(RenFont *font, const char *text, int x, int y, RenColor color) {
  (void)font; (void)color; texts_drawn++;
  return x + (text ? (int)strlen(text) * 7 : 0);
}
