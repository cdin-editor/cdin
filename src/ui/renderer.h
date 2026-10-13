#ifndef RENDERER_H
#define RENDERER_H

#include <SDL3/SDL.h>
#include <stdint.h>
#include <stdbool.h>

typedef struct { uint8_t b, g, r, a; } RenColor;

typedef struct { int x, y, width, height; } RenRect;

typedef struct RenImage RenImage;
typedef struct RenFont RenFont;
void ren_init(SDL_Window *win);
void ren_update_rects(RenRect *rects, int count);
void ren_set_clip_rect(RenRect rect);
void ren_get_size(int *x, int *y);

/* True once if the window surface was replaced since the last call (resize,
 * restore, show, DPI change). A replaced surface holds none of the pixels the
 * damage cache believes are on screen, so the caller must repaint everything. */
bool ren_take_surface_replaced(void);

RenImage *ren_new_image(int width, int height);
void ren_free_image(RenImage *image);

RenFont *ren_load_font(const char *filename, float size);
void ren_free_font(RenFont *font);
void ren_set_font_tab_width(RenFont *font, int n);
int ren_get_font_tab_width(RenFont *font);
int ren_get_font_width(RenFont *font, const char *text);
int ren_get_font_height(RenFont *font);
float ren_get_font_size(RenFont *font);

void ren_font_add_fallback(RenFont *font, RenFont *fallback);

/* How many fallbacks a font's chain can hold.
 *
 * Exposed because the font handle anchors one fallback per chain entry, and its
 * own fixed array has to be the same size. Two constants in two files that must
 * agree is better checked than assumed — and the check is in
 * luaopen_renderer_font, so a mismatch is a log line at boot rather than a chain
 * that silently refuses an add. */
int ren_max_fallback_fonts(void);

/* Baked-glyph cache accounting, for core:memory. glyph_bytes is the total
 * bitmap bytes held by every live font; count is how many 256-codepoint pages
 * are resident. Both are zero before any font is loaded. */
size_t ren_glyph_bytes(void);
int    ren_glyphset_count(void);

void ren_draw_rect(RenRect rect, RenColor color);
void ren_draw_image(RenImage *image, RenRect *sub, int x, int y, RenColor color);
int  ren_draw_text(RenFont *font, const char *text, int x, int y, RenColor color);

#endif