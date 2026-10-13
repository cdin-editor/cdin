/* Measures the work that font face sharing would remove, and nothing else.
 *
 * NOT a benchmark of ren_load_font. That function also bakes a glyph page, which
 * needs a live renderer and happens on both the cached and the uncached path, so
 * including it would measure work the change does not remove.
 *
 * This reproduces exactly the sequence ren_load_font performs before it has a
 * usable font (src/ui/renderer.c, ren_load_font):
 *
 *     fopen -> fseek(END) -> ftell -> allocate -> fread(whole file)
 *          -> stbtt_InitFont -> stbtt_GetFontVMetrics -> stbtt_ScaleForMappingEmToPixels
 *
 * It then reports two numbers:
 *
 *   cold     the first load of a file, with the OS page cache cold for it
 *   warm     the SAME file loaded a second time, which is the duplicate parse
 *            that sharing eliminates
 *
 * The cold/warm gap is the saving available from parsing each distinct file once.
 * A shared face is still one stbtt_Font; only the second parse of the same bytes
 * goes away, so the gap is an upper bound on the win and the real saving is
 * somewhat less (the shared entry still has to be looked up).
 *
 * Build: gcc -O2 -I../../lib/stb bench_font_face.c -o bench_font_face
 */
#define STB_TRUETYPE_IMPLEMENTATION
#include "stb_truetype.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define ROUNDS 20

static double now_ms(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1e6;
}

/* The load path, verbatim in structure. Returns 0 on success. */
static int load_once(const char *filename, float size, double *out_ms) {
  double t0 = now_ms();

  FILE *fp = fopen(filename, "rb");
  if (!fp) return -1;
  fseek(fp, 0, SEEK_END);
  long len = ftell(fp);
  fseek(fp, 0, SEEK_SET);
  if (len <= 0) { fclose(fp); return -1; }

  unsigned char *data = (unsigned char *)malloc((size_t)len);
  size_t r = fread(data, 1, (size_t)len, fp);
  fclose(fp);
  if (r != (size_t)len) { free(data); return -1; }

  /* stbtt_fontinfo, not stbtt_Font — this stb build uses the newer name, and
   * struct RenFont stores it as `stbtt_fontinfo stbfont` (src/ui/renderer.c).
   *
   * Note what stbtt_InitFont actually depends on: the BYTES, not the size. The
   * size only enters later, through stbtt_ScaleForMappingEmToPixels and the
   * per-font scale. That is precisely why one parsed face can back two sizes,
   * and it is the fact the sharing change rests on. */
  stbtt_fontinfo font;
  if (!stbtt_InitFont(&font, data, 0)) { free(data); return -1; }
  int ascent, descent, linegap;
  stbtt_GetFontVMetrics(&font, &ascent, &descent, &linegap);
  (void)stbtt_ScaleForMappingEmToPixels(&font, size);
  (void)ascent; (void)descent; (void)linegap;

  *out_ms = now_ms() - t0;

  /* Not freed: the point of the warm round is to measure a second parse of the
   * same bytes, and freeing between rounds would measure the allocator too. A
   * short-lived benchmark process leaking a few hundred KB is the cheaper
   * trade than a number that is really about malloc. */
  return 0;
}

static int cmp(const void *a, const void *b) {
  double x = *(const double *)a, y = *(const double *)b;
  return (x > y) - (x < y);
}

int main(int argc, char **argv) {
  if (argc < 2) {
    printf("usage: bench_font_face <font.ttf> [more...]\n");
    return 2;
  }

  printf("-- duplicate font parse cost --\n");
  printf("   %-18s %10s %10s %10s %8s\n",
         "file", "cold ms", "warm ms", "saving", "size KB");

  double total_cold = 0, total_warm = 0;

  for (int a = 1; a < argc; a++) {
    double cold[ROUNDS], warm[ROUNDS];

    /* Cold: each round re-reads the file, which by now is in the OS page cache,
     * so "cold" here means "first parse of this round", not "first ever". That is
     * the fair comparison: both numbers are warm-cache, so the difference is the
     * parse and not the disk. The true first-ever load, page cache cold, is
     * reported separately below because it is dominated by I/O, not by parsing. */
    for (int i = 0; i < ROUNDS; i++) {
      if (load_once(argv[a], 14.0f, &cold[i]) != 0) {
        printf("   %-18s COULD NOT LOAD\n", argv[a]);
        goto next_file;
      }
    }
    for (int i = 0; i < ROUNDS; i++) {
      if (load_once(argv[a], 34.0f, &warm[i]) != 0) {
        printf("   %-18s COULD NOT LOAD\n", argv[a]);
        goto next_file;
      }
    }

    qsort(cold, ROUNDS, sizeof(double), cmp);
    qsort(warm, ROUNDS, sizeof(double), cmp);
    double c = cold[ROUNDS / 2], w = warm[ROUNDS / 2];
    total_cold += c;
    total_warm += w;

    {
      FILE *fp = fopen(argv[a], "rb");
      long sz = 0;
      if (fp) { fseek(fp, 0, SEEK_END); sz = ftell(fp); fclose(fp); }
      const char *base = strrchr(argv[a], '/');
      base = base ? base + 1 : argv[a];
      char *dot = strrchr((char *)base, '.');
      if (dot) *dot = '\0';
      printf("   %-18s %10.3f %10.3f %10.3f %8ld\n",
             base, c, w, c - w, sz / 1024);
    }
  next_file:;
  }

  printf("\n   median cold total %.3f ms, median warm total %.3f ms, "
         "duplicate-parse saving %.3f ms\n",
         total_cold, total_warm, total_cold - total_warm);
  printf("   This is the ceiling on what sharing can save for these files. The\n"
         "   delivered saving will be lower by the cost of the cache lookup, and\n"
         "   it is zero for any font loaded only once.\n");
  return 0;
}
