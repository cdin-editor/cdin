#include <stdio.h>
#include <stdbool.h>
#include <assert.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

/* stb_truetype — single-header font rasterizer */
#define STB_TRUETYPE_IMPLEMENTATION
#include "../../lib/stb/stb_truetype.h"

#include "renderer.h"
#include "../base/alloc.h"
#include "../core/logger.h"

/* Glyphs are baked in blocks of 256 codepoints ("pages"), keyed by the
   codepoint's high bits (cp >> 8) — one page per 0x100 codepoint range,
   e.g. page 0x1F3 covers U+1F300..U+1F3FF (misc symbols/pictographs).
   Pages are looked up in a small open-addressing hash table sized for the
   whole Unicode range (cp up to 0x10FFFF => up to ~4352 possible pages),
   allocated lazily so this stays cheap for BMP-only text. This replaces a
   fixed 256-bucket table indexed by `(cp >> 8) % 256`, which wrapped
   around and silently collided unrelated blocks together once codepoints
   went past the BMP (e.g. an emoji at U+1FA87 landed in the same bucket
   as CJK Compatibility Ideographs at U+FA00-FAFF and could draw the
   wrong glyph instead of just being missing). */
#define GLYPHSET_TABLE_SIZE 8192  /* power of 2; open-addressed, ~65% max load */

struct RenImage {
  RenColor *pixels;
  int width, height;
};

typedef struct {
  RenImage *image;
  stbtt_bakedchar glyphs[256];
  int page;      /* cp >> 8 this set was baked for; -1 = empty slot */
  bool has_bitmap;
} GlyphSet;

#define MAX_FALLBACK_FONTS 8

struct RenFont {
  void *data;
  stbtt_fontinfo stbfont;
  GlyphSet **table;   /* GLYPHSET_TABLE_SIZE slots, lazily populated */
  float size;
  int height;
  RenFont *fallback[MAX_FALLBACK_FONTS];
  int fallback_count;
};

static SDL_Window   *window;
/* The window surface is owned by SDL and is destroyed and recreated when the
 * window is resized, restored or shown. `surface` is therefore refreshed through
 * sync_surface() on every read and never trusted across a frame boundary; the
 * last_* fields identify the surface that was painted so a replacement is seen
 * even if the allocator hands back the same address. Main thread only. */
static SDL_Surface  *surface;
static void         *last_pixels;
static int           last_w, last_h;
static bool          surface_replaced;
static struct { int left, top, right, bottom; } clip;

/* Baked-glyph bytes live for the life of the font, so the total is the only
 * honest number core:memory can report. Owned by this module, touched only by
 * load_glyphset / ren_free_font / ren_load_font, all of which run on the main
 * thread. */
static size_t glyph_bytes;
static int    glyphset_count;


/* Every allocation in this module goes through the accounting allocator, tagged
 * CDIN_MEM_FONT, so core:memory can say where the glyph cache went. Before this
 * the renderer used raw malloc and was invisible to the per-subsystem report —
 * which is why "2.1 MiB of glyphs" was a number core:memory knew but could not
 * attribute.
 *
 * check_alloc stays fatal, and is now confined to the load path — the RenFont
 * struct, the font's data block, and image creation. Those are the "tiny,
 * documented set of unrecoverable startup failures" AGENTS.md §6 permits: there
 * is no font to draw with, so there is nothing to degrade to.
 *
 * The draw path deliberately does NOT go through here. Glyph pages are baked
 * lazily by load_glyphset from get_glyphset, which runs per-frame, so an
 * allocation failure there arrives mid-frame with a command queue to unwind;
 * terminating there loses the session to one unbakeable page. load_glyphset and
 * glyphset_slot both return NULL instead, and every caller of get_glyphset
 * handles it: the width query and both draw lookups skip the codepoint, and the
 * tab-width accessors and the tab/newline fixup check before touching glyphs.
 * An OOM while drawing now costs the glyphs it could not bake and nothing else.
 *
 * What a font that cannot bake a page does is decided by those guards: it draws
 * nothing for the codepoints on that page, and the fallback chain is still tried
 * first for every codepoint, so a font with a failed page does not shadow its
 * fallbacks. A blank region is the visible cost of running out of memory, which
 * is preferable to terminating the editor.
 *
 * The allocation itself is reported before this point: cdin_alloc logs the size
 * and the subsystem it could not serve, so the log says which request failed and
 * not merely that one did. */
static void *check_alloc(void *ptr, size_t size) {
  if (!ptr) {
    log_fatal("renderer: out of memory for a %zu byte font allocation", size);
    exit(EXIT_FAILURE);
  }
  return ptr;
}

static const char *utf8_to_codepoint(const char *p, unsigned *dst) {
  /* Hardened decoder: never over-reads, rejects overlong/truncated
     sequences and surrogates, returns U+FFFD on error. */
  unsigned char c = (unsigned char)*p;
  if (c < 0x80) { *dst = c; return p + 1; }
  unsigned res = 0, n = 0, lo = 0x80, hi = 0xBF;
  if ((c & 0xE0) == 0xC0)      { res = c & 0x1F; n = 1; lo = (c == 0xC0 || c == 0xC1) ? 0x100 : 0x80; }
  else if ((c & 0xF0) == 0xE0) { res = c & 0x0F; n = 2; }
  else if ((c & 0xF8) == 0xF0) { res = c & 0x07; n = 3; }
  else { *dst = 0xFFFD; return p + 1; }
  for (unsigned i = 1; i <= n; i++) {
    unsigned char cc = (unsigned char)p[i];
    if (i == 1 && n > 1) {
      if (c == 0xE0) lo = 0xA0;
      else if (c == 0xED) hi = 0x9F;
      else if (c == 0xF0) lo = 0x90;
      else if (c == 0xF4) hi = 0x8F;
    }
    if (cc < lo || cc > hi || p[i] == '\0') { *dst = 0xFFFD; return p + 1; }
    lo = 0x80; hi = 0xBF;
    res = (res << 6) | (cc & 0x3F);
  }
  if (res > 0x10FFFF || (res >= 0xD800 && res <= 0xDFFF)) res = 0xFFFD;
  *dst = res;
  return p + n + 1;
}

static void sync_surface(void) {
  SDL_Surface *s = SDL_GetWindowSurface(window);
  if (!s) {
    log_error("renderer: SDL_GetWindowSurface failed: %s", SDL_GetError());
    return;
  }
  if (s != surface || s->pixels != last_pixels || s->w != last_w || s->h != last_h) {
    if (surface) {
      log_debug("renderer: window surface replaced (%dx%d -> %dx%d)", last_w, last_h, s->w, s->h);
      surface_replaced = true;
    }
    surface     = s;
    last_pixels = s->pixels;
    last_w      = s->w;
    last_h      = s->h;
  }
}

bool ren_take_surface_replaced(void) {
  sync_surface();
  bool r = surface_replaced;
  surface_replaced = false;
  return r;
}

void ren_init(SDL_Window *win) {
  assert(win);
  window = win;
  sync_surface();
  assert(surface);
  ren_set_clip_rect((RenRect){ 0, 0, surface->w, surface->h });
}

void ren_update_rects(RenRect *rects, int count) {
  SDL_UpdateWindowSurfaceRects(window, (SDL_Rect *)rects, count);
  sync_surface();
  assert(surface);
  static bool initial_frame = true;
  if (initial_frame) {
    SDL_ShowWindow(window);
    initial_frame = false;
  }
}

void ren_set_clip_rect(RenRect rect) {
  clip.left   = rect.x;
  clip.top    = rect.y;
  clip.right  = rect.x + rect.width;
  clip.bottom = rect.y + rect.height;
}

void ren_get_size(int *x, int *y) {
  sync_surface();
  assert(surface);
  *x = surface->w;
  *y = surface->h;
}


/* The one allocation every image in this module makes. The tag is a parameter
 * rather than fixed, because ren_new_image is public and a future caller might
 * reasonably be making a surface or a layer rather than a glyph page — and an
 * image of the wrong kind showing up in `gfx` is exactly the kind of attribution
 * error that makes a per-subsystem report worth not having.
 *
 * One block: the pixels live immediately after the header, so an image is a
 * single allocation rather than two. */
static RenImage *new_image_tagged(CdinMemTag tag, int width, int height) {
  assert(width > 0 && height > 0);
  /* Checked rather than assumed. width * height * 4 overflows int at a
   * 23000x23000 image, which is 2 GiB of pixels on a machine that may not have
   * 2 GiB, and the multiplication would wrap to a small positive number and
   * allocate a buffer far too small for the loop that fills it. */
  size_t pixels = (size_t)width * (size_t)height;
  if (height != 0 && pixels / (size_t)height != (size_t)width) {
    log_error("renderer: image %dx%d overflows a size_t", width, height);
    return NULL;
  }
  size_t total = sizeof(RenImage) + pixels * sizeof(RenColor);

  RenImage *img = cdin_alloc(tag, total);
  check_alloc(img, total);
  img->pixels = (void *)(img + 1);
  img->width  = width;
  img->height = height;
  return img;
}

RenImage *ren_new_image(int width, int height) {
  return new_image_tagged(CDIN_MEM_GFX, width, height);
}

void ren_free_image(RenImage *image) {
  cdin_free(image);
}


/* The largest page the bake is allowed to grow to.
 *
 * stbtt_BakeFontBitmap returns a negative value when the glyphs do not fit, and
 * the original loop doubled width and height until they did — with no bound. A
 * font that cannot fit at any practical size (a corrupt size field, or memory
 * already exhausted) doubled forever, allocating and freeing a larger image each
 * time. AGENTS.md §2.4 is about growth that is unbounded rather than growth that
 * is large, and this was both.
 *
 * 2048x2048 covers a page of glyphs at any size the editor offers. Past it the
 * page is abandoned rather than grown, which is the same trade the NULL path
 * makes: a missing page is visible, an unbounded loop is not. */
#define GLYPHSET_MAX_DIM 2048

static GlyphSet *load_glyphset(RenFont *font, int page) {
  /* Not check_alloc. This runs from get_glyphset on the draw path, so an OOM
   * here arrives mid-frame; ending the process for one unbakeable glyph page
   * loses the session, whereas returning NULL costs the glyphs on that page and
   * nothing else. Every caller of get_glyphset handles NULL — the width query
   * and both draw lookups skip the codepoint, and the tab-width accessors and
   * the tab/newline fixup check before touching glyphs. */
  GlyphSet *set = cdin_calloc(CDIN_MEM_FONT, 1, sizeof(GlyphSet));
  if (!set) {
    log_warn("renderer: out of memory for a glyph set (page %d)", page);
    return NULL;
  }
  set->page = page;
  int width = 128, height = 128;

retry:
  /* CDIN_MEM_FONT, not the gfx tag ren_new_image would use: a baked glyph page
   * is the glyph cache, which is what the master prompt budgets under font and
   * what a reader expects to see named `font` in core:memory. */
  set->image = new_image_tagged(CDIN_MEM_FONT, width, height);
  if (!set->image) {
    /* The image is the whole body of the page, so there is nothing to salvage.
     * cdin_alloc has already logged the size and tag it could not serve. */
    log_warn("renderer: out of memory baking glyph page %d (%dx%d)",
             page, width, height);
    cdin_free(set);
    return NULL;
  }
  float s = stbtt_ScaleForMappingEmToPixels(&font->stbfont, 1)
           / stbtt_ScaleForPixelHeight(&font->stbfont, 1);
  int res = stbtt_BakeFontBitmap(
    font->data, 0, font->size * s,
    (void *)set->image->pixels,
    width, height, page * 256, 256, set->glyphs);

  if (res < 0) {
    if (width >= GLYPHSET_MAX_DIM) {
      log_warn("renderer: glyph page %d will not fit in %dx%d, giving up on "
               "it", page, width, height);
      ren_free_image(set->image);
      cdin_free(set);
      return NULL;
    }
    width  *= 2;
    height *= 2;
    ren_free_image(set->image);
    goto retry;
  }

  int ascent, descent, linegap;
  stbtt_GetFontVMetrics(&font->stbfont, &ascent, &descent, &linegap);
  float scale = stbtt_ScaleForMappingEmToPixels(&font->stbfont, font->size);
  int scaled_ascent = (int)(ascent * scale + 0.5f);

  for (int i = 0; i < 256; i++) {
    set->glyphs[i].yoff     += scaled_ascent;
    set->glyphs[i].xadvance  = floorf(set->glyphs[i].xadvance);
    /* A codepoint this font truly has no outline for bakes to a zero-area
       glyph (unless it's whitespace, which is legitimately zero-area).
       Recording that here lets callers fall back to another font instead
       of silently drawing nothing. */
    stbtt_bakedchar *g = &set->glyphs[i];
    bool empty_box = (g->x1 <= g->x0 || g->y1 <= g->y0);
    int cp = page * 256 + i;
    bool expected_blank = (cp == ' ' || cp == '\t' || cp == '\n' || cp == '\r');
    if (!empty_box || expected_blank) set->has_bitmap = true;
  }

  for (int i = width * height - 1; i >= 0; i--) {
    uint8_t a = *((uint8_t *)set->image->pixels + i);
    set->image->pixels[i] = (RenColor){ .r=255, .g=255, .b=255, .a=a };
  }

  glyph_bytes += sizeof(GlyphSet) + (size_t)width * height * sizeof(RenColor);
  glyphset_count++;

  return set;
}

/* Where a page's glyphset lives, or NULL when the table could not be allocated.
 *
 * NULL rather than check_alloc: this is reached from get_glyphset on the draw
 * path, and the same reasoning as load_glyphset applies — a font that cannot
 * get a lookup table draws nothing rather than ending the session. */
static GlyphSet **glyphset_slot(RenFont *font, int page) {
  if (!font->table) {
    font->table = cdin_calloc(CDIN_MEM_FONT,
                              GLYPHSET_TABLE_SIZE, sizeof(GlyphSet *));
    if (!font->table) {
      log_warn("renderer: out of memory for the glyph table (%d entries)",
               GLYPHSET_TABLE_SIZE);
      return NULL;
    }
  }
  unsigned h = ((unsigned)page * 2654435761u) & (GLYPHSET_TABLE_SIZE - 1);
  for (int probes = 0; probes < GLYPHSET_TABLE_SIZE; probes++) {
    GlyphSet **slot = &font->table[h];
    if (*slot == NULL || (*slot)->page == page) return slot;
    h = (h + 1) & (GLYPHSET_TABLE_SIZE - 1);
  }
  /* Every probe held a different page, so the table is full and this page has
   * nowhere to live.
   *
   * The old answer was a pointer to one shared static GlyphSet, handed out
   * complete with an empty scratch->page. get_glyphset then filled it with a
   * freshly baked page, and the next codepoint in the same call overwrote it —
   * so two glyphs from different pages aliased one set, and the second draw read
   * the first page's glyphs. A silent wrong-glyph bug, reachable by having more
   * distinct pages than the table has cells.
   *
   * NULL is correct and the caller already handles it: the page is simply not
   * drawn. Missing glyphs are visible; wrong glyphs are not. */
  log_warn("renderer: glyph table full (%d pages) — page %d will not be drawn",
           GLYPHSET_TABLE_SIZE, page);
  return NULL;
}

static GlyphSet *get_glyphset(RenFont *font, int codepoint) {
  if (codepoint < 0 || codepoint > 0x10FFFF) codepoint = 0xFFFD;
  int page = codepoint >> 8;
  GlyphSet **slot = glyphset_slot(font, page);
  if (!slot) return NULL;
  if (!*slot) *slot = load_glyphset(font, page);
  return *slot;
}

static bool font_has_glyph(RenFont *font, int codepoint) {
  GlyphSet *set = get_glyphset(font, codepoint);
  return set && set->has_bitmap;
}

static RenFont *resolve_font_for(RenFont *font, int codepoint) {
  if (font_has_glyph(font, codepoint)) return font;
  for (int i = 0; i < font->fallback_count; i++) {
    if (font_has_glyph(font->fallback[i], codepoint)) return font->fallback[i];
  }
  return font;
}

int ren_max_fallback_fonts(void) { return MAX_FALLBACK_FONTS; }

void ren_font_add_fallback(RenFont *font, RenFont *fallback) {
  if (!font || !fallback || font == fallback) return;
  if (font->fallback_count >= MAX_FALLBACK_FONTS) {
    log_warn("renderer: fallback chain full (%d), ignoring additional fallback font",
             MAX_FALLBACK_FONTS);
    return;
  }
  font->fallback[font->fallback_count++] = fallback;
}

RenFont *ren_load_font(const char *filename, float size) {
  RenFont *font = check_alloc(cdin_calloc(CDIN_MEM_FONT, 1, sizeof(RenFont)),
                              sizeof(RenFont));
  font->size = size;

  FILE *fp = fopen(filename, "rb");
  if (!fp) { cdin_free(font); return NULL; }

  fseek(fp, 0, SEEK_END);
  long len = ftell(fp);
  fseek(fp, 0, SEEK_SET);

  /* A negative or absent length cannot be read into a buffer sized from it.
   * check_alloc would exit on the wrap; refusing here keeps a truncated or
   * non-seekable font file from being reported as an out-of-memory. */
  if (len <= 0) { fclose(fp); cdin_free(font); return NULL; }
  size_t buf_size = (size_t)len;

  font->data = check_alloc(cdin_alloc(CDIN_MEM_FONT, buf_size), buf_size);
  size_t r = fread(font->data, 1, buf_size, fp);
  fclose(fp);
  if (r != buf_size) { cdin_free(font->data); cdin_free(font); return NULL; }

  if (!stbtt_InitFont(&font->stbfont, font->data, 0)) {
    cdin_free(font->data); cdin_free(font); return NULL;
  }

  int ascent, descent, linegap;
  stbtt_GetFontVMetrics(&font->stbfont, &ascent, &descent, &linegap);
  float scale = stbtt_ScaleForMappingEmToPixels(&font->stbfont, size);
  font->height = (int)((ascent - descent + linegap) * scale + 0.5f);

  /* Make tab/newline invisible.
   *
   * The glyphset is NULL when page 0 could not be baked. That is survivable —
   * the font is loaded and usable, it just has no metrics for tab and newline
   * yet — so it is skipped rather than treated as a load failure. Returning NULL
   * here instead would make the whole font unavailable over a cosmetic fixup,
   * and the caller has no way to tell that apart from a bad file. The tab width
   * will be whatever the font reports until the page bakes later. */
  GlyphSet *set = get_glyphset(font, '\n');
  if (set) {
    stbtt_bakedchar *g = set->glyphs;
    g['\t'].x1 = g['\t'].x0;
    g['\n'].x1 = g['\n'].x0;
  } else {
    log_warn("renderer: no glyphs baked for \"%s\" — tab and newline will "
             "measure wrong until memory is available", filename);
  }

  return font;
}

void ren_free_font(RenFont *font) {
  if (font->table) {
    for (int i = 0; i < GLYPHSET_TABLE_SIZE; i++) {
      GlyphSet *set = font->table[i];
      if (set) {
        size_t px = (size_t)set->image->width * (size_t)set->image->height
                    * sizeof(RenColor);
        glyph_bytes -= sizeof(GlyphSet) + px;
        glyphset_count--;
        ren_free_image(set->image);
        cdin_free(set);
      }
    }
    cdin_free(font->table);
  }
  cdin_free(font->data);
  cdin_free(font);
}

/* Glyph cache accounting for core:memory. Read-only for the caller; the
 * counters are maintained by the two paths above. */
size_t ren_glyph_bytes(void) {
  return glyph_bytes;
}

int ren_glyphset_count(void) {
  return glyphset_count;
}

void ren_set_font_tab_width(RenFont *font, int n) {
  /* No glyphset means page 0 was never baked, so there is nothing to store the
   * width in. Silently dropping the call would leave the caller believing the
   * tab width changed, so it is logged — once per failure is not worth tracking
   * here, and the log is already the only signal the caller can act on. */
  GlyphSet *set = get_glyphset(font, '\t');
  if (!set) {
    log_warn("renderer: set_tab_width(%d) ignored — no glyphs baked for this "
             "font", n);
    return;
  }
  set->glyphs['\t'].xadvance = (float)n;
}

int ren_get_font_tab_width(RenFont *font) {
  GlyphSet *set = get_glyphset(font, '\t');
  /* 0 rather than a guess: a caller laying out a line needs a number, and
   * without metrics the honest one is "this font has no tab width yet". The
   * status bar rendering it as a zero-width tab is a visible, recoverable
   * artefact; returning a plausible constant would be a silent lie about
   * measurements the caller then uses to position everything else. */
  return set ? (int)set->glyphs['\t'].xadvance : 0;
}

int ren_get_font_width(RenFont *font, const char *text) {
  if (!font || !text) return 0;
  int x = 0;
  unsigned cp;
  /* Cap measured length so a multi-MB line cannot stall a frame. */
  int bytes = 0;
  for (const char *p = text; *p && bytes < 65536; ) {
    p = utf8_to_codepoint(p, &cp);
    bytes = (int)(p - text);
    RenFont *use = font->fallback_count ? resolve_font_for(font, (int)cp) : font;
    GlyphSet *set = get_glyphset(use, (int)cp);
    if (!set) break;
    x += (int)set->glyphs[cp & 0xff].xadvance;
  }
  return x;
}

int ren_get_font_height(RenFont *font) {
  return font->height;
}

float ren_get_font_size(RenFont *font) {
  return font->size;
}


static inline RenColor blend_pixel(RenColor dst, RenColor src) {
  int ia = 0xff - src.a;
  dst.r = (uint8_t)(((src.r * src.a) + (dst.r * ia)) >> 8);
  dst.g = (uint8_t)(((src.g * src.a) + (dst.g * ia)) >> 8);
  dst.b = (uint8_t)(((src.b * src.a) + (dst.b * ia)) >> 8);
  return dst;
}

static inline RenColor blend_pixel2(RenColor dst, RenColor src, RenColor color) {
  src.a = (uint8_t)((src.a * color.a) >> 8);
  int ia = 0xff - src.a;
  dst.r = (uint8_t)(((src.r * color.r * src.a) >> 16) + ((dst.r * ia) >> 8));
  dst.g = (uint8_t)(((src.g * color.g * src.a) >> 16) + ((dst.g * ia) >> 8));
  dst.b = (uint8_t)(((src.b * color.b * src.a) >> 16) + ((dst.b * ia) >> 8));
  return dst;
}

void ren_draw_rect(RenRect rect, RenColor color) {
  if (color.a == 0) return;

  int x1 = rect.x < clip.left   ? clip.left   : rect.x;
  int y1 = rect.y < clip.top    ? clip.top    : rect.y;
  int x2 = rect.x + rect.width;
  int y2 = rect.y + rect.height;
  x2 = x2 > clip.right  ? clip.right  : x2;
  y2 = y2 > clip.bottom ? clip.bottom : y2;
  if (x1 >= x2 || y1 >= y2) return;
  RenColor *d = (RenColor *)surface->pixels + x1 + y1 * surface->w;
  int dr = surface->w - (x2 - x1);

  if (color.a == 0xff) {
    for (int j = y1; j < y2; j++) {
      for (int i = x1; i < x2; i++) { *d++ = color; }
      d += dr;
    }
  } else {
    for (int j = y1; j < y2; j++) {
      for (int i = x1; i < x2; i++) { *d = blend_pixel(*d, color); d++; }
      d += dr;
    }
  }
}

void ren_draw_image(RenImage *image, RenRect *sub, int x, int y, RenColor color) {
  if (color.a == 0) return;
  int n;
  if ((n = clip.left - x) > 0) { sub->width  -= n; sub->x += n; x += n; }
  if ((n = clip.top  - y) > 0) { sub->height -= n; sub->y += n; y += n; }
  if ((n = x + sub->width  - clip.right)  > 0) { sub->width  -= n; }
  if ((n = y + sub->height - clip.bottom) > 0) { sub->height -= n; }
  if (sub->width <= 0 || sub->height <= 0) return;

  RenColor *s = image->pixels + sub->x + sub->y * image->width;
  RenColor *d = (RenColor *)surface->pixels + x + y * surface->w;
  int sr = image->width  - sub->width;
  int dr = surface->w    - sub->width;

  for (int j = 0; j < sub->height; j++) {
    for (int i = 0; i < sub->width; i++) {
      *d = blend_pixel2(*d, *s, color);
      d++; s++;
    }
    d += dr; s += sr;
  }
}

int ren_draw_text(RenFont *font, const char *text, int x, int y, RenColor color) {
  if (!font || !text || color.a == 0) return x;
  unsigned cp;
  int drawn = 0;
  /* Baseline offset so a fallback font (which may have different metrics/
     ascent at the same pixel size) still sits on the same text baseline
     as the primary font, instead of glyphs jumping up/down mid-line. */
  int base_ascent = ren_get_font_height(font);
  for (const char *p = text; *p && drawn < 4096; ) {
    p = utf8_to_codepoint(p, &cp);
    RenFont *use = font->fallback_count ? resolve_font_for(font, (int)cp) : font;
    GlyphSet *set = get_glyphset(use, (int)cp);
    if (!set) break;
    stbtt_bakedchar *g = &set->glyphs[cp & 0xff];
    int yoff = y;
    if (use != font) yoff += base_ascent - ren_get_font_height(use);
    /* Skip zero-size/dirty glyphs (e.g. missing coverage) safely. */
    if (g->x1 > g->x0 && g->y1 > g->y0) {
      RenRect rect = { g->x0, g->y0, g->x1 - g->x0, g->y1 - g->y0 };
      ren_draw_image(set->image, &rect, x + (int)g->xoff, yoff + (int)g->yoff, color);
    }
    x += (int)g->xadvance;
    drawn++;
  }
  return x;
}