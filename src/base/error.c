/* The CdinErr classification: names, and the one-line description.
 *
 * This file allocates nothing and calls nothing that allocates. A report about
 * running out of memory is exactly the report that must not try to allocate
 * more, so cdin_err_describe writes into the caller's buffer and cdin_err_set
 * writes through the caller's pointer. The only static data is a table of string
 * literals that the linker can place in read-only memory.
 *
 * Ownership: none. Every function here is pure — the returned const char *s are
 * string literals with static storage duration, valid for the life of the
 * process, and nothing the caller may free.
 *
 * Threads: safe to call from any thread. The statics are never written after
 * initialisation, which is what "static mutable state" is banned for; this is
 * immutable-after-init data.
 */

#include "error.h"

#include <string.h>

/* One entry per classification, indexed by the enum. The count is asserted by
 * cdin_err_name's bounds check, so a member appended to CdinErr without a row
 * here reports "unknown" instead of reading the next string — which is the
 * failure a reader would spend an hour on. */
static const char *const ERR_NAMES[CDIN_ERR_COUNT] = {
  "ok",
  "invalid",
  "not_found",
  "state",
  "perm",
  "invalid_utf8",
  "limit",
  "oom",
  "unsupported",
  "cancelled",
  "internal",
};

const char *cdin_err_name(CdinErr code) {
  /* Cast through int, not compare the enum directly: a CdinErr that arrived as
   * a corrupted value or a cast from Lua must not be able to index the table
   * with a negative int that happens to pass an enum comparison. */
  int i = (int)code;
  if (i < 0 || i >= (int)CDIN_ERR_COUNT) return "unknown";
  return ERR_NAMES[i];
}

CdinErr cdin_err_set(CdinErrDetail *e, CdinErr code, const char *detail) {
  /* A NULL detail is allowed and ignored. Several call sites have no string to
   * hand over — an index out of range, a cancelled operation — and making them
   * pass "" would put a lie in the report: an empty detail reads as "the path
   * was blank" rather than "there was nothing to add". */
  if (e) {
    e->code   = code;
    e->os_code = 0;
    e->detail = detail;
    e->line   = 0;
  }
  return code;
}

/* ── cdin_err_describe ─────────────────────────────────────────────────── */

/* Copy as much of `src` as fits, never splitting a UTF-8 sequence.
 *
 * The loop is written with explicit byte inspection rather than trusting a
 * strlen on a possibly-truncated prefix: a detail is borrowed from a caller and
 * may not even be NUL-terminated in a caller's own error, so a length is passed
 * in by the internal helper and the copy cannot run off the end.
 *
 * Returns the bytes written, and sets `truncated` to 1 if more were available. */
static size_t copy_bounded_utf8(char *dst, size_t cap, const char *src,
                                size_t src_len, int *truncated) {
  size_t n = 0;
  *truncated = 0;

  for (size_t i = 0; i < src_len; i++) {
    if (n + 1 >= cap) {          /* one byte reserved for the terminator */
      *truncated = 1;
      break;
    }

    /* Length of the UTF-8 sequence starting here, or 1 if this is not a valid
     * lead byte. An invalid lead is copied as a single byte rather than
     * dropped: the detail may legitimately be raw bytes from a file, and a log
     * line that silently omits them is worse than one that shows them. */
    unsigned char c = (unsigned char)src[i];
    size_t seq = 1;
    if (c >= 0xF0)      seq = 4;
    else if (c >= 0xE0) seq = 3;
    else if (c >= 0xC0) seq = 2;

    /* A sequence that runs past the source is treated as individual bytes: the
     * source itself is truncated, and stopping at the end of it is correct. */
    if (seq > 1 && i + seq > src_len) seq = 1;

    /* Do not emit a partial sequence even if it would fit. */
    if (seq > 1 && n + seq >= cap) { *truncated = 1; break; }

    for (size_t k = 0; k < seq; k++) dst[n++] = src[i + k];
    i += seq - 1;
  }

  dst[n] = '\0';
  return n;
}

CdinErr cdin_err_describe(CdinErrDetail e, char *buf, size_t cap) {
  if (!buf || cap == 0) return CDIN_ERR_INVALID;

  const char *name = cdin_err_name(e.code);

  /* "[name]" on its own is 2 + strlen(name) + 1 bytes of terminator. Computing
   * it rather than assuming a fixed size means a classification added later
   * cannot silently overflow the buffer for a caller that sized for "internal". */
  size_t prefix_len = 1 + strlen(name) + 2;   /* '[' + name + ']' + NUL */
  if (prefix_len > cap) {
    /* Not even the name fits. Truncate inside it, at a boundary, and say so. */
    int truncated = 0;
    copy_bounded_utf8(buf, cap, name, strlen(name), &truncated);
    return CDIN_ERR_LIMIT;
  }

  memcpy(buf, "[", 1);
  memcpy(buf + 1, name, strlen(name));
  memcpy(buf + 1 + strlen(name), "]", 1);
  size_t n = prefix_len - 1;      /* bytes written, no terminator yet */
  buf[n] = '\0';

  /* CDIN_OK has nothing to add; "ok: something" is noise. */
  if (e.code == CDIN_OK) return CDIN_OK;

  /* The OS code, when the platform gave one. errno alone is rarely actionable
   * to a user, but it is what makes a report diagnosable, so it goes in the
   * line rather than only in a debugger. */
  if (e.os_code != 0) {
    char num[24];
    int len = 0;
    /* Hand-rolled rather than snprintf: this path must not depend on the C
     * library's formatting, and the value is always small. */
    if (e.os_code < 0) num[len++] = '-';
    unsigned v = (unsigned)(e.os_code < 0 ? -e.os_code : e.os_code);
    char digits[12];
    int nd = 0;
    do {
      digits[nd++] = (char)('0' + (v % 10));
      v /= 10;
    } while (v != 0 && nd < (int)sizeof(digits));
    while (nd > 0) num[len++] = digits[--nd];

    /* " os=" is 4 bytes, the digits are len, the terminator is 1. If that does
     * not fit, drop the os code rather than truncating it: half a number in a
     * log is worse than none, and the classification is already on the line. */
    if (n + 4 + (size_t)len + 1 > cap) return CDIN_ERR_LIMIT;

    memcpy(buf + n, " os=", 4);
    n += 4;
    memcpy(buf + n, num, (size_t)len);
    n += (size_t)len;
    buf[n] = '\0';
  }

  if (!e.detail || e.detail[0] == '\0') return CDIN_OK;

  /* ": " then the detail. If only the separator fits, stop cleanly rather than
   * emitting a trailing ": ". */
  if (n + 3 > cap) return CDIN_ERR_LIMIT;
  memcpy(buf + n, ": ", 2);
  n += 2;

  int truncated = 0;
  copy_bounded_utf8(buf + n, cap - n, e.detail, strlen(e.detail), &truncated);
  n += strlen(buf + n);

  if (truncated) return CDIN_ERR_LIMIT;
  return CDIN_OK;
}