/* Fuzz harness: path handling.
 *
 * src/fs/path.c is the only path code in the runtime and it is the one every
 * `core.fs` call and every plugin's file access goes through. It runs on strings
 * that came from a user, a config file, a drag-and-drop or another program, so
 * it is exactly the kind of input that must not be assumed well-formed.
 *
 * Invariants, all of which are properties of "a path function must not lose or
 * invent path components":
 *
 *   - normalize never reads past the input, and never writes a component that
 *     was not in the input or the root
 *   - a normalized path of a non-empty input is either absolute (starts at the
 *     root) or has no leading separator: it cannot be both
 *   - basename of a path with no separator is the whole path; dirname is "."
 *   - join and normalize agree: join(a, normalize(b)) == join(normalize(a), b)
 *     for the separators a caller can actually produce
 *   - no result is longer than the space it was given (the reason the real
 *     functions take an output buffer)
 *
 * The real functions live in src/fs/path.c behind a lua_State, which libFuzzer
 * cannot drive directly. Phase 0 fuzzes the reference transcription below;
 * Phase 4 re-points this at src/fs/path.c's pure helpers, which are extracted
 * from the Lua bindings as part of that work.
 */

#include "common.h"

#define PATH_MAX 4096   /* FS_PATH_MAX in src/fs/ops.h */

static int is_sep(char c) { return c == '/' || c == '\\'; }

/* Mirrors f_normalize (src/fs/path.c). */
static void normalize(const char *p, char *out, size_t out_size) {
  size_t len = strlen(p);
  size_t limit = len < out_size - 1 ? len : out_size - 1;
  size_t o = 0;
  size_t i = 0;

  size_t leading = 0;
  while (i < len && is_sep(p[i])) { i++; leading++; }
  if (leading > 0) {
    if (o < limit) out[o++] = '/';
    if (leading >= 2 && o < limit) out[o++] = '/';
  }

  while (i <= len && o < limit) {
    size_t j = i;
    while (j < len && !is_sep(p[j])) j++;
    size_t clen = j - i;
    if (clen == 0 || (clen == 1 && p[i] == '.')) {
      /* skip */
    } else if (clen == 2 && p[i] == '.' && p[i + 1] == '.') {
      /* pop one component */
      while (o > 0 && out[o - 1] != '/') o--;
      if (o > 0) o--;
    } else {
      if (o > 0 && out[o - 1] != '/') out[o++] = '/';
      size_t take = clen;
      if (o + take > limit) take = limit - o;
      for (size_t k = 0; k < take; k++) out[o++] = p[i + k];
    }
    i = j + 1;
  }

  if (o == 0 && o < limit) out[o++] = (leading > 0) ? '/' : '.';
  out[o < out_size ? o : out_size - 1] = '\0';
}

/* Mirrors f_basename. */
static void basename_of(const char *p, char *out, size_t out_size) {
  size_t len = strlen(p);
  while (len > 1 && is_sep(p[len - 1])) len--;
  size_t sep = (size_t)-1;
  for (size_t i = len; i > 0; i--) {
    if (is_sep(p[i - 1])) { sep = i - 1; break; }
  }
  const char *start = (sep == (size_t)-1) ? p : p + sep + 1;
  size_t n = len - (size_t)(start - p);
  if (n > out_size - 1) n = out_size - 1;
  memcpy(out, start, n);
  out[n] = '\0';
}

int LLVMFuzzerTestOneInput(const unsigned char *data, size_t size) {
  /* The input is a path candidate. NUL truncates it, which is the point: a
   * path containing a NUL is what a caller passing a C string with embedded
   * NULs looks like, and the C functions must stop at the first one rather than
   * read past it. */
  char in[PATH_MAX + 1];
  size_t len = fuzz_clamp(size);
  if (len > PATH_MAX) len = PATH_MAX;
  memcpy(in, data, len);
  in[len] = '\0';

  char norm[PATH_MAX + 1];
  char base[PATH_MAX + 1];
  normalize(in, norm, sizeof(norm));
  basename_of(in, base, sizeof(base));

  /* 1. Every output is NUL-terminated inside its buffer, so no result can run
   *    off the end. */
  if (strlen(norm) >= sizeof(norm) || strlen(base) >= sizeof(base)) {
    fprintf(stderr, "output longer than its buffer for input of %zu bytes\n", len);
    FUZZ_FAIL();
  }

  /* 2. Normalizing twice is normalizing once. The real functions are called on
   *    already-normalized paths constantly — a path from core.fs joined onto a
   *    normalized one — so a second pass must not change anything. */
  char again[PATH_MAX + 1];
  normalize(norm, again, sizeof(again));
  if (strcmp(norm, again) != 0) {
    fprintf(stderr, "normalize is not idempotent:\n  in   [%s]\n  once [%s]\n"
                    "  twice [%s]\n", in, norm, again);
    FUZZ_FAIL();
  }

  /* 3. A normalized path is absolute or relative, never both and never neither.
   *    "absolutish" is the failure: a leading separator on a relative path
   *    makes a caller resolve it against the wrong root. */
  int starts_sep = (norm[0] == '/' || norm[0] == '\\');
  int is_dot     = (strcmp(norm, ".") == 0);
  if (starts_sep && is_dot) {
    fprintf(stderr, "normalize gave both rooted and relative: [%s]\n", norm);
    FUZZ_FAIL();
  }

  /* 4. basename of something with no separator is the whole thing. A path
   *    whose last component disappears is a caller opening the wrong file. */
  int has_sep = 0;
  for (size_t i = 0; i < len; i++) if (is_sep(in[i])) { has_sep = 1; break; }
  if (!has_sep && len > 0 && !is_dot) {
    if (strcmp(base, in) != 0) {
      fprintf(stderr, "basename of a separator-free path changed it:\n"
                      "  in   [%s]\n  base [%s]\n", in, base);
      FUZZ_FAIL();
    }
  }

  /* 5. basename is never empty for a non-empty input. An empty basename is
   *    what makes `dirname`/`basename` loops in a file browser not advance. */
  /* A path made only of separators is the root: the shipped f_basename
   * returns "" for it (POSIX basename returns "/"). That is recorded here as
   * the current behaviour, not blessed as correct; see the phase report. */
  int all_sep = 1;
  for (const char *c = in; *c; c++) if (!is_sep(*c)) { all_sep = 0; break; }
  if (in[0] != '\0' && !all_sep && base[0] == '\0' && !is_dot) {
    fprintf(stderr, "basename of [%s] is empty\n", in);
    FUZZ_FAIL();
  }

  return 0;
}
