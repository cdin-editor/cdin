/* The font half of the renderer stand-in, split out from stub_renderer.c.
 *
 * renderer_font.c needs a font it can load, free and chain without SDL: a
 * window, a surface and a TTF parser are all in the way, and none of them is
 * what the font suite is testing. What it is testing is the handle — its
 * lifecycle, its closed detection, and the fallback keepalives.
 *
 * This is a separate file rather than more of stub_renderer.c because the two
 * suites need different halves and link different real code:
 *
 *   cdin-tests      links the real renderer_cache.c, so rencache_free_font
 *                   already exists. Defining it again here is a link error, not
 *                   a warning.
 *   cdin-tests-lua  links no renderer at all, so it needs the deferred-free
 *                   stand-in this file provides.
 *
 * One file with both halves would make one of the two binaries fail to link, and
 * the fix for that — a macro the real cache has to cooperate with — couples a
 * test to a file it is standing in for. Splitting keeps each binary honest
 * about what it substitutes.
 *
 * Owned by the test process. All state is static and written only from the
 * single-threaded test runner.
 */

#include <stdint.h>
#include <string.h>

#include "../../src/base/alloc.h"
#include "../../src/core/logger.h"
#include "../../src/ui/renderer.h"
#include "ctest.h"

/* RenFont is opaque in renderer.h — deliberately, since nothing outside
 * src/ui/renderer.c should know its layout. So this cannot size one, and does
 * not need to: nothing here reads a font. It hands out a fixed opaque block per
 * load at a distinct address, which is the whole of what a test can observe. */
#define STUB_FONT_BYTES 64

static int fonts_loaded;
static int fonts_freed;
static int fallbacks_added;

/* Addresses rather than RenFont*, so the chain can be inspected without anything
 * outside this file having a renderer type in its hands. */
/* High-water mark of the array above, which is NOT the same as fonts_loaded:
 * fonts_loaded is a counter the tests read, and reset zeroes it while blocks are
 * still allocated. Tracking the high-water separately is what lets
 * ren_stub_free_all reach every block regardless of how often a test reset the
 * counters in between. */
static int fonts_high_water;

static RenFont *stub_fonts[64];
static RenFont *stub_chain[64];
static uintptr_t stub_chain_fallback[64];
static int      stub_chain_n;

int ren_stub_fonts_loaded(void) { return fonts_loaded; }
int ren_stub_fonts_freed(void) { return fonts_freed; }
int ren_stub_fallbacks_added(void) { return fallbacks_added; }
int ren_stub_chain_len(void) { return stub_chain_n; }

int ren_stub_chain_at(int i, uintptr_t *fallback_addr) {
  if (i < 0 || i >= stub_chain_n) return 0;
  if (fallback_addr) *fallback_addr = stub_chain_fallback[i];
  return 1;
}

/* Drops every stub block still held.
 *
 * The suite leaks these on purpose if nothing calls this: the address array is
 * what gives each load a distinct identity, so the pointers have to outlive the
 * frees that `ren_free_font` counts. Without releasing them at the end, every
 * font a test loads stays live in the project's accounting for the life of the
 * process — harmless, but it means `cdin_alloc` totals in a failing run are
 * harder to read, and "harmless in a test" is how a real leak gets described
 * later.
 *
 * Called once, after the last suite has run. It is not called from
 * ren_stub_reset, which is called between cases: mid-run the block a later case
 * compares against may still be the one an earlier case loaded. */
void ren_stub_free_all(void) {
  for (int i = 0; i < fonts_high_water; i++) {
    if (stub_fonts[i]) {
      cdin_free(stub_fonts[i]);
      stub_fonts[i] = NULL;
    }
  }
  fonts_loaded = fonts_freed = fallbacks_added = stub_chain_n = 0;
  fonts_high_water = 0;
}

void ren_stub_reset(void) {
  fonts_loaded = fonts_freed = fallbacks_added = stub_chain_n = 0;
}

/* ── what renderer_font.c calls ─────────────────────────────────────────── */

RenFont *ren_load_font(const char *filename, float size) {
  (void)filename; (void)size;
  /* Bounded by the array, not by fonts_loaded: reset() zeroes that counter
   * while blocks stay allocated, so it would hand out the same slot twice and
   * overwrite a live pointer, orphaning a block nothing can now free. */
  if (fonts_high_water >= (int)(sizeof(stub_fonts) / sizeof(stub_fonts[0])))
    return NULL;
  /* A distinct address per load, so a test cannot mistake two handles for one,
   * and through the project's allocator so it shows up in the accounting. */
  void *bytes = cdin_alloc(CDIN_MEM_GFX, STUB_FONT_BYTES);
  if (!bytes) return NULL;
  memset(bytes, 0, STUB_FONT_BYTES);
  stub_fonts[fonts_high_water++] = (RenFont *)bytes;
  fonts_loaded++;
  return stub_fonts[fonts_high_water - 1];
}

void ren_font_add_fallback(RenFont *font, RenFont *fallback) {
  if (stub_chain_n >= (int)(sizeof(stub_chain) / sizeof(stub_chain[0]))) {
    log_warn("stub: fallback chain full, ignoring");
    return;
  }
  stub_chain[stub_chain_n] = font;
  stub_chain_fallback[stub_chain_n] = (uintptr_t)fallback;
  stub_chain_n++;
  fallbacks_added++;
}

void ren_free_font(RenFont *font) { (void)font; fonts_freed++; }

/* The damage cache's deferred free, which is what the font handle's destructor
 * calls. The real one queues the font for release at end_frame; here the queue
 * is a no-op, so the counter moves at close time rather than a frame later.
 * That is a deliberate difference, and the tests state it — the thing under test
 * is that close() releases, not that the release is deferred a frame. */
void rencache_free_font(RenFont *font) { ren_free_font(font); }

/* Metrics. Fixed values, because a test that asserts on them is asserting that
 * the binding passed the right font through, not on font rendering. */
int   ren_get_font_width(RenFont *font, const char *text) {
  (void)font;
  return text ? (int)strlen(text) * 7 : 0;
}
int   ren_get_font_height(RenFont *font) { (void)font; return 16; }
float ren_get_font_size(RenFont *font) { (void)font; return 14.0f; }
int   ren_get_font_tab_width(RenFont *font) { (void)font; return 4; }
void  ren_set_font_tab_width(RenFont *font, int n) { (void)font; (void)n; }

/* The same bound the real renderer uses. The font handle anchors one fallback
 * per chain entry, so the two constants have to agree — and the binding checks
 * this at registration, which would log an error if the stub lied. */
int ren_max_fallback_fonts(void) { return 8; }
