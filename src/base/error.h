/* The error type every fallible C function in src/ returns.
 *
 * Why not errno: errno is a single int that says a syscall failed, not which
 * operation or why, and it is not thread-local on Windows. Why not NULL plus a
 * log line: a log line is not something a caller can branch on, so every
 * caller ends up re-deriving the reason from context, and two callers derive
 * two different answers. Why not a returned struct: allocation. This returns
 * the classification in a register and leaves a single out-parameter for the
 * one piece of data that is not a classification — the path, the line number,
 * the offending token.
 *
 * The classification is deliberately small and stable. It is part of what the
 * extension contract exposes (as Lua error values in Phase 2), so adding a
 * member is a contract change and renumbering one is a break. Append only.
 *
 * CDIN_OK is 0 so that `if (err != CDIN_OK)` and `if (err)` agree. A
 * nonzero-is-error convention that is not zero-valued is the kind of thing
 * that survives review because every use site looks correct.
 *
 * Ownership: a CdinErr carries no allocation. The bytes it refers to — a
 * path, a name — belong to whoever passed them in and must outlive the err.
 * That is why there is no cdin_err_free and why the comment on every
 * `const char *` field says whose it is. A buffer-taking variant that formats
 * into a caller-supplied buffer lives in str.h, not here.
 */

#ifndef CDIN_BASE_ERROR_H
#define CDIN_BASE_ERROR_H

#include <stddef.h>

typedef enum {
  /* Not an error. Zero, so `err != CDIN_OK` and `if (err)` are the same test
   * and a caller cannot get one of them wrong by muscle memory. */
  CDIN_OK = 0,

  /* An argument was outside its documented range: a negative offset, a
   * directory separator where a filename belongs, an unrecognised enum. The
   * caller's bug, found before any work was done. Distinct from
   * CDIN_ERR_INVALID_UTF8, which is about the *data*. */
  CDIN_ERR_INVALID,

  /* The operation is real and the arguments are right, but the thing is not
   * there: no such file, no such key, no such index. Worth a different user
   * message from CDIN_ERR_INVALID, because "you asked for something that does
   * not exist" and "you asked for something impossible" are not the same
   * sentence. */
  CDIN_ERR_NOT_FOUND,

  /* The thing exists and cannot be used this way: a directory where a file
   * was expected, a read-only file being written, a buffer held by someone
   * else. Distinct from CDIN_ERR_PERM so a read-only file does not read as
   * "you lack permission". */
  CDIN_ERR_STATE,

  /* The OS refused: permission denied, sharing violation, disk full. The
   * errno-style code is in `os_code` when the platform gave one. */
  CDIN_ERR_PERM,

  /* The bytes on disk or in the input were not what the format requires:
   * malformed UTF-8, a truncated archive, an unrecognised image header.
   *
   * This exists as its own member rather than as CDIN_ERR_INVALID because the
   * contract of a text editor is that bytes round-trip (AGENTS.md §2.6): a file
   * with invalid UTF-8 must still open, and the decoder substitutes only for
   * display. A caller that sees CDIN_ERR_INVALID here may reasonably refuse the
   * file; a caller that sees CDIN_ERR_INVALID_UTF8 must not. Conflating them is
   * how a "helpful" validation step turns a Latin-1 file into an error dialog. */
  CDIN_ERR_INVALID_UTF8,

  /* A size, offset, or count would overflow, or a length exceeded the cap its
   * subsystem declares. Separate from CDIN_ERR_OOM because the remedy differs:
   * a limit means "ask for less", OOM means "free something". */
  CDIN_ERR_LIMIT,

  /* The system allocator refused. Never a substitute for CDIN_ERR_LIMIT — see
   * above. Handled at the boundary, where the caller can close a document and
   * carry on, rather than propagated into the drawing code. */
  CDIN_ERR_OOM,

  /* The operation needs a platform feature this build or this OS does not
   * have. Rare by design: most of these should be compiled out, and the ones
   * that remain should be reachable only on a platform that lacks them. */
  CDIN_ERR_UNSUPPORTED,

  /* The operation was interrupted or cancelled. Distinct from any failure so a
   * cancelled load is not reported as a broken file. */
  CDIN_ERR_CANCELLED,

  /* An invariant this module states about itself did not hold. Always a bug in
   * this runtime, never in the input. Kept distinct so a report that shows one
   * of these is unmistakably "not the user's file". */
  CDIN_ERR_INTERNAL,

  CDIN_ERR_COUNT  /* sentinel — not an error */
} CdinErr;

/* The single detail field. Which string it is depends on the classification,
 * and it is always borrowed, never owned:
 *
 *   CDIN_ERR_NOT_FOUND      the path or key that was not there
 *   CDIN_ERR_INVALID        the argument, rendered
 *   CDIN_ERR_PERM           the path whose syscall failed
 *   CDIN_ERR_INVALID_UTF8   the offset of the first bad byte, as text
 *   CDIN_ERR_LIMIT          "wanted N, cap is M", rendered
 *   CDIN_ERR_UNSUPPORTED    what was asked for
 *   others                  NULL
 *
 * One field, not a union: a union would be smaller and would make every
 * reader check which member is live. CdinErr is four words and appears once per
 * fallible call, not once per byte, so the size does not matter and the clarity
 * does. */
typedef struct {
  CdinErr    code;
  /* The platform's own error number when there was one (errno, GetLastError),
   * else 0. Kept because "why" is often only available at the syscall, three
   * frames below the code that has to report it. */
  int        os_code;
  /* Borrowed, per the table above. NULL when there is nothing to add. */
  const char *detail;
  /* 1-based line number where the error was first given meaning, or 0. Set by
   * the module that classifies, never by a caller: a caller passing its own
   * line number produces a trace that points at the reporter rather than the
   * defect. */
  int        line;
} CdinErrDetail;

#define CDIN_ERR_INIT { CDIN_OK, 0, NULL, 0 }

/* Shorthand for the common shape: classification, platform code, borrowed
 * detail, no line. Used at the point of classification, where there is no more
 * specific line to name than the one the macro is written on. */
#define CDIN_ERR(c) ((CdinErrDetail){ (c), 0, NULL, __LINE__ })

/* Classification and detail together, for the case where the detail is a
 * borrowed string the caller already holds — a path, a key. */
#define CDIN_ERR_AT(c, d) ((CdinErrDetail){ (c), 0, (d), __LINE__ })

/* Classification, platform code, and detail. The OS code is only known where
 * the syscall happened, so this is the form used there. */
#define CDIN_ERR_OS(c, o, d) ((CdinErrDetail){ (c), (o), (d), __LINE__ })

/* True when `e` carries no error. A function of the detail rather than a
 * comparison so that a future member cannot quietly change what "no error"
 * means at the call sites. */
static inline int cdin_err_ok(CdinErrDetail e) { return e.code == CDIN_OK; }

/* Fills `e` and returns its classification, so a call site reads as
 *   return cdin_err_set(e, CDIN_ERR_PERM, "open failed");
 * and still returns the classification the caller needs. `e` may be NULL for a
 * caller that does not want the detail — the classification is not lost, which
 * is the difference between this and a void function that only logs. */
CdinErr cdin_err_set(CdinErrDetail *e, CdinErr code, const char *detail);

/* The stable machine-readable name: "not_found", "invalid_utf8", "oom". Used in
 * reports and in the Lua binding's error values, so it is part of the surface
 * and does not change to match the enum's spelling. "unknown" for a value that
 * is not one of ours rather than an out-of-bounds read. */
const char *cdin_err_name(CdinErr code);

/* A one-line human sentence into a caller-supplied buffer:
 *
 *     cdin_err_describe(e, buf, sizeof buf);   ->  "[not_found]: D:/missing.txt"
 *
 * Writes at most `cap` bytes and always NUL-terminates when cap > 0, so it is
 * safe on a 16-byte stack buffer with a 200-character detail. Returns CDIN_OK
 * when the whole sentence fit, and CDIN_ERR_LIMIT when it had to be cut — which
 * is also what a cap of zero returns. Truncation is reported rather than hidden
 * because a log line that silently loses the detail is how "not_found" ends up
 * on screen with no reason attached.
 *
 * The cut happens at a UTF-8 sequence boundary, never inside one, so the line
 * never contains a broken codepoint.
 *
 * Takes a buffer rather than returning a pointer because the sentence contains
 * the caller's detail. Returning a static string would force the caller to
 * format it, which is the work this is here to do; allocating would put an
 * allocation on the reporting path, which is exactly where a report about
 * running out of memory must not try to allocate more. */
CdinErr cdin_err_describe(CdinErrDetail e, char *buf, size_t cap);

/* An empty detail, for a caller that has nothing to say. */
#define CDIN_NOERR CDIN_ERR_INIT

#endif /* CDIN_BASE_ERROR_H */