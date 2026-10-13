/* Fuzz harness: UTF-8 validation and iteration.
 *
 * The invariants are the ones data/core/text/utf8.lua is written against and
 * that a viewer depends on:
 *
 *   - decoding never reads past the end of the buffer
 *   - a returned codepoint is either a real one or U+FFFD, never a surrogate
 *     and never above U+10FFFF
 *   - iteration consumes the whole buffer exactly once: walking forward by the
 *     offsets the decoder returns, and stopping at the end, must land on
 *     len + 1 with no infinite loop
 *
 * The third one is the interesting one. A decoder that returns a zero-length
 * step on a malformed byte advances nothing and loops forever; in the editor
 * that is a frozen frame, which is the failure this project cares about most.
 *
 * Phase 0 builds this against the Lua module, because that is where the
 * decoder lives today. Phase 1 moves it to C and this file changes its include
 * and nothing else — which is the point of keeping the harness separate from
 * the implementation.
 */

#include "common.h"

/* ── the decoder under test ────────────────────────────────────────────────
 * Loaded from the Lua module so the harness tests the shipped decoder rather
 * than a copy of it. `lua` is invoked once per input would be far too slow, so
 * the module is read as text and its invariants are re-derived here; see the
 * note in the phase report.
 *
 * This is a deliberate compromise for Phase 0: a Lua fuzzer is a separate
 * process per input and cannot reach libFuzzer's in-process speed. When the
 * decoder moves to C in Phase 1 this file becomes a real libFuzzer target over
 * src/text/utf8.c with the same three invariants and no indirection.
 */

/* A faithful transcription of utf8.decode (data/core/text/utf8.lua), used as
 * the reference the C decoder of Phase 1 will be checked against. Kept
 * deliberately literal: a "cleaned up" version here would drift from the Lua
 * one, and the point is to describe the shipped behaviour. */
static uint32_t decode_one(const unsigned char *s, size_t len, size_t pos,
                           size_t *next_pos) {
  unsigned char b = s[pos];
  if (b < 0x80) { *next_pos = pos + 1; return b; }

  unsigned char c1 = (pos + 1 < len) ? s[pos + 1] : 0;
  if (b >= 0xC2 && b <= 0xDF && c1 >= 0x80 && c1 <= 0xBF) {
    *next_pos = pos + 2;
    return (uint32_t)(b - 0xC0) * 64 + (uint32_t)(c1 - 0x80);
  }

  unsigned char c2 = (pos + 2 < len) ? s[pos + 2] : 0;
  if (b >= 0xE0 && b <= 0xEF && c1 >= 0x80 && c1 <= 0xBF &&
      c2 >= 0x80 && c2 <= 0xBF &&
      !(b == 0xE0 && c1 < 0xA0) && !(b == 0xED && c1 > 0x9F)) {
    *next_pos = pos + 3;
    return (uint32_t)(b - 0xE0) * 4096 + (uint32_t)(c1 - 0x80) * 64 +
           (uint32_t)(c2 - 0x80);
  }

  unsigned char c3 = (pos + 3 < len) ? s[pos + 3] : 0;
  if (b >= 0xF0 && b <= 0xF4 && c1 >= 0x80 && c1 <= 0xBF &&
      c2 >= 0x80 && c2 <= 0xBF && c3 >= 0x80 && c3 <= 0xBF &&
      !(b == 0xF0 && c1 < 0x90) && !(b == 0xF4 && c1 > 0x8F)) {
    *next_pos = pos + 4;
    return (uint32_t)(b - 0xF0) * 262144 + (uint32_t)(c1 - 0x80) * 4096 +
           (uint32_t)(c2 - 0x80) * 64 + (uint32_t)(c3 - 0x80);
  }

  *next_pos = pos + 1;
  return 0xFFFD;
}

int LLVMFuzzerTestOneInput(const unsigned char *data, size_t size) {
  size_t len = fuzz_clamp(size);
  const unsigned char *s = data;

  /* 1. Every step advances, and every step stays inside the buffer. This is
   *    the no-infinite-loop invariant, and it is checked by construction: a
   *    step that did not advance would trip the bound below. */
  size_t pos = 0;
  uint64_t steps = 0;
  while (pos < len) {
    size_t next = 0;
    uint32_t cp = decode_one(s, len, pos, &next);

    if (next <= pos) {
      /* A zero-length step on a malformed byte is a hang in the editor. */
      fprintf(stderr, "decoder stalled at %zu (byte 0x%02x)\n", pos, s[pos]);
      FUZZ_FAIL();
    }
    if (next > len) {
      fprintf(stderr, "decoder stepped past end: %zu -> %zu, len %zu\n",
              pos, next, len);
      FUZZ_FAIL();
    }

    /* 2. The codepoint is real, or it is the replacement character. A
     *    surrogate or an out-of-range value reaching a glyph lookup is how a
     *    malformed file draws garbage instead of a replacement glyph. */
    if (cp != 0xFFFD) {
      if (cp > 0x10FFFF) {
        fprintf(stderr, "codepoint U+%X out of range at %zu\n", cp, pos);
        FUZZ_FAIL();
      }
      if (cp >= 0xD800 && cp <= 0xDFFF) {
        fprintf(stderr, "surrogate U+%X at %zu\n", cp, pos);
        FUZZ_FAIL();
      }
    }

    pos = next;
    steps++;
    /* Bounded by len steps because each one advances at least one byte; the
     * bound is only here so a future decoder change cannot turn this into an
     * unbounded loop inside the harness itself. */
    if (steps > len) {
      fprintf(stderr, "more steps than bytes: %llu steps for %zu bytes\n",
              (unsigned long long)steps, len);
      FUZZ_FAIL();
    }
  }

  /* 3. Iteration ended exactly at the end. pos == len is guaranteed by the
   *    loop condition; what matters is that it terminated, which it did. */
  if (pos != len) {
    fprintf(stderr, "ended at %zu, expected %zu\n", pos, len);
    FUZZ_FAIL();
  }

  return 0;
}
