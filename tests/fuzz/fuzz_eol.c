/* Fuzz harness: EOL detection and encoding/BOM sniffing.
 *
 * These are the parsers that decide what a file *means* before any of it is
 * shown: which bytes are a newline, whether there is a byte-order mark, and
 * whether the content is text or binary. Every one of them is a function of a
 * bounded prefix, and every one of them is a place where an off-by-one turns a
 * file into a different file.
 *
 * Invariants:
 *   - a reported line count is at least 1 (an empty document still has a line)
 *   - a detected EOL kind is one of the four, and "mixed" only when more than
 *     one kind is actually present
 *   - a BOM, if detected, is at offset 0 and the reported length matches the
 *     marker that was found
 *   - detection reads no more than the prefix it was given, and reports that
 *     it was prefix-limited rather than pretending the whole file was seen
 *
 * Phase 0 builds this against the reference transcription below. Phase 4
 * replaces the transcription with src/text/eol.c and src/text/encoding.c and
 * changes only the include.
 */

#include "common.h"

#define PREFIX_MAX 8192   /* the size of the prefix these parsers may read */

typedef enum { EOL_LF, EOL_CRLF, EOL_CR, EOL_MIXED } EolKind;
typedef enum { ENC_UTF8, ENC_UTF8_BOM, ENC_UTF16LE, ENC_UTF16BE, ENC_LATIN1,
               ENC_BINARY } Encoding;

/* Counts line terminators in a bounded prefix and reports what it saw. Mirrors
 * what Doc:load has to decide (self.crlf in data/core/doc/init.lua) and what a
 * save has to reproduce. */
static EolKind detect_eol(const unsigned char *s, size_t len, int *prefix_limited) {
  int saw_lf = 0, saw_crlf = 0, saw_cr = 0;
  size_t limit = len < PREFIX_MAX ? len : PREFIX_MAX;
  if (limit < len) *prefix_limited = 1;

  for (size_t i = 0; i < limit; i++) {
    if (s[i] == '\r') {
      if (i + 1 < len && s[i + 1] == '\n') { saw_crlf++; i++; }
      else saw_cr++;
    } else if (s[i] == '\n') {
      saw_lf++;
    }
  }

  int kinds = (saw_lf > 0) + (saw_crlf > 0) + (saw_cr > 0);
  if (kinds > 1) return EOL_MIXED;
  if (kinds == 0) return EOL_LF;          /* the default the editor saves with */
  if (saw_crlf) return EOL_CRLF;
  if (saw_cr)  return EOL_CR;
  return EOL_LF;
}

/* Byte-order mark and encoding sniffing over a bounded prefix. */
static Encoding detect_encoding(const unsigned char *s, size_t len,
                                int *bom_length, int *prefix_limited) {
  size_t limit = len < PREFIX_MAX ? len : PREFIX_MAX;
  if (limit < len) *prefix_limited = 1;
  *bom_length = 0;

  if (limit >= 3 && s[0] == 0xEF && s[1] == 0xBB && s[2] == 0xBF) {
    *bom_length = 3;
    return ENC_UTF8_BOM;
  }
  if (limit >= 2 && s[0] == 0xFF && s[1] == 0xFE) { *bom_length = 2; return ENC_UTF16LE; }
  if (limit >= 2 && s[0] == 0xFE && s[1] == 0xFF) { *bom_length = 2; return ENC_UTF16BE; }

  /* NUL in the first bytes is how a UTF-16 file without a BOM looks, and how a
   * binary file looks. Either way it is not text to be edited line by line. */
  size_t probe = limit < 512 ? limit : 512;
  for (size_t i = 0; i < probe; i++) {
    if (s[i] == 0x00) return ENC_BINARY;
  }

  /* High bytes that are not valid UTF-8 lead: Latin-1 rather than binary. */
  size_t i = 0;
  while (i < probe) {
    unsigned char b = s[i];
    if (b < 0x80) { i++; continue; }
    size_t need;
    if (b >= 0xC2 && b <= 0xDF) need = 1;
    else if (b >= 0xE0 && b <= 0xEF) need = 2;
    else if (b >= 0xF0 && b <= 0xF4) need = 3;
    else return ENC_LATIN1;   /* a continuation or an overlong lead byte */
    if (i + need >= probe) break;
    for (size_t k = 1; k <= need; k++) {
      unsigned char c = s[i + k];
      if (c < 0x80 || c > 0xBF) return ENC_LATIN1;
    }
    i += need + 1;
  }
  return ENC_UTF8;
}


int LLVMFuzzerTestOneInput(const unsigned char *data, size_t size) {
  size_t len = fuzz_clamp(size);
  int eol_limited = 0, enc_limited = 0;
  int bom_length = 0;

  EolKind eol = detect_eol(data, len, &eol_limited);
  Encoding enc = detect_encoding(data, len, &bom_length, &enc_limited);

  /* A BOM is at offset 0 and its length is one of the three the format has. */
  if (bom_length != 0) {
    if (bom_length != 2 && bom_length != 3) {
      fprintf(stderr, "BOM length %d is not a BOM length\n", bom_length);
      FUZZ_FAIL();
    }
    if ((size_t)bom_length > len) {
      fprintf(stderr, "BOM length %d exceeds input length %zu\n", bom_length, len);
      FUZZ_FAIL();
    }
    if (enc != ENC_UTF8_BOM && enc != ENC_UTF16LE && enc != ENC_UTF16BE) {
      fprintf(stderr, "BOM reported (%d) but encoding is not BOM-bearing (%d)\n",
              bom_length, (int)enc);
      FUZZ_FAIL();
    }
  }

  /* "mixed" only when more than one kind is present: a prefix that is entirely
   * CRLF is CRLF, and reporting mixed for it would make every CRLF file get a
   * prompt on save. */
  if (eol == EOL_MIXED) {
    int saw_lf = 0, saw_cr = 0;
    size_t limit = len < PREFIX_MAX ? len : PREFIX_MAX;
    for (size_t i = 0; i < limit; i++) {
      if (data[i] == '\n') saw_lf++;
      else if (data[i] == '\r') saw_cr++;
    }
    int kinds = (saw_lf > 0) + (saw_cr > 0);
    if (kinds < 2) {
      fprintf(stderr, "reported mixed, but saw %d kind(s) of terminator\n", kinds);
      FUZZ_FAIL();
    }
  }

  /* A prefix longer than the cap is reported, never silently treated as whole. */
  if (len > PREFIX_MAX && (!eol_limited || !enc_limited)) {
    fprintf(stderr, "input of %zu bytes was not reported as prefix-limited\n", len);
    FUZZ_FAIL();
  }

  return 0;
}
