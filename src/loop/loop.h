/* Asynchronous file I/O, off the frame thread.
 *
 * What it is for. AGENTS.md §2.7 says never block the frame, and Doc:load and
 * Doc:save in data/core/doc/init.lua block it for the whole read or write:
 * `io.open` plus a per-line loop, on the thread that also runs core.step. A 256
 * MiB file spends seconds in there, and the editor does not repaint, does not
 * respond to input, and does not honour a redraw request until the bytes are
 * all in memory. That is the concrete need this module exists to remove.
 *
 * The shape of the fix is constrained by two rules that pull against each other:
 *
 *   §2.3  the Lua state is single-threaded; workers never touch Lua.
 *   §2.7  the frame must not block.
 *
 * So the split is by data, not by phase. A worker cannot build the line table:
 * that is Lua data, and touching it from a worker is what §2.3 forbids. What it
 * CAN do is the part that is bytes and nothing else — open, read, close. The
 * bytes come back as one buffer and the frame thread splits them into lines when
 * it is ready. The expensive blocking part moves off the frame; the part that
 * must stay on the frame stays on it.
 *
 * That is why this module deals in whole files and not in line builders. It is
 * not a general filesystem abstraction and must not grow into one: it reads and
 * writes bytes, and every decision about what those bytes MEAN belongs to
 * data/core/doc, the only place that knows a BOM is data and a line ending is a
 * line ending.
 *
 * Why libuv. Decision 1 approves libuv alongside SDL3 for asynchronous
 * processing, with SDL3 keeping the window, input and rendering. This is that
 * decision's first consumer. Nothing here may call SDL: a worker touching a
 * window from another thread is exactly what Decision 1 rules out.
 *
 * Ownership. One loop per process, owned by this module, created by
 * job_loop_init and destroyed by job_loop_close. A request is owned by the caller
 * until job_file_read is called, which copies the path; the result buffer belongs
 * to the loop and is freed when the callback returns, so a callback must copy
 * anything it keeps. There is no handle and no request object: a request is a path
 * and a callback, and it completes exactly once.
 *
 * Buffers are capped. §2.4 bans unbounded growth, and a read is the easiest way to
 * ask for one. LOOP_MAX_FILE_BYTES refuses a larger file rather than allocating
 * until the process dies, and the refusal is reported through the same callback as
 * any other error, so a caller has one path rather than two.
 */

#ifndef CDIN_LOOP_H
#define CDIN_LOOP_H

#include <stddef.h>
#include <stdint.h>

/* The largest file a read will bring into memory.
 *
 * 1 GiB, because AGENTS.md says to choose the data structure by the 1 GB case and
 * this is the one place a document is read whole. Beyond it the read is refused:
 * a larger file needs a streaming path this deliberately does not implement,
 * because a half-implemented one would look like it worked. Exceeding this is an
 * error through the callback, never a truncated read — a silent short read would
 * be a corrupted document (§2.6). */
#define LOOP_MAX_FILE_BYTES ((size_t)1 << 30)

typedef enum {
  LOOP_OK = 0,
  LOOP_ERR_OPEN,       /* the file could not be opened for reading */
  LOOP_ERR_STAT,       /* its size could not be determined */
  LOOP_ERR_TOO_LARGE,  /* larger than LOOP_MAX_FILE_BYTES — refused, not truncated */
  LOOP_ERR_ALLOC,      /* the buffer could not be allocated */
  LOOP_ERR_READ,       /* the read failed, or returned fewer bytes than the size */
} LoopStatus;

/* Why a read failed, in words, for a binding to hand a caller. NULL-free by
 * construction: every status has a string. */
const char *loop_status_str(LoopStatus status);

/* Called on the loop thread when a read finishes, successfully or not.
 *
 * On success `data` is `len` readable bytes, valid only for the duration of the
 * call. On failure it is NULL and len is 0. The callback runs exactly once per
 * accepted request.
 *
 * The buffer is not NUL-terminated and may contain NUL bytes: a document is
 * bytes, and terminating it would make an embedded NUL indistinguishable from the
 * end of the data (§2.6). */
typedef void (*LoopReadCb)(LoopStatus status, const uint8_t *data, size_t len,
                           void *user);

/* Starts the loop. Idempotent: calling it twice succeeds and creates no second
 * loop, because two loops would mean two thread pools and no way to tell which
 * served a request. Returns 0 on success. */
int job_loop_init(void);

/* Stops the loop, after finishing whatever it is still doing.
 *
 * Requests still in flight are COMPLETED, not abandoned: the loop is pumped until
 * it reports itself no longer alive before anything is freed. That ordering is the
 * whole contract — freeing a request while a libuv worker is still reading it is a
 * use-after-free, and it presented as a SIGTRAP inside a worker thread after this
 * function had returned.
 *
 * Completion callbacks do NOT fire during the drain, because this is called after
 * the Lua state is gone and a callback would re-enter a closed interpreter.
 *
 * If the drain cannot finish within its own bounded deadline, the outstanding
 * requests are deliberately leaked and counted in the log rather than freed while
 * a worker may still hold them. A leak at shutdown is recoverable; a
 * use-after-free is not.
 *
 * MUST NOT be called from inside a completion callback. A callback is running
 * inside uv_run, and closing would free the loop while libuv is still reading
 * its state. The call is REFUSED and logged, the loop is left intact and
 * working, and the caller can close again once the dispatch has returned. Nothing
 * is freed on that path, so a refused close costs a log line and nothing else. */
void job_loop_close(void);

/* Reads a whole file off the frame thread.
 *
 * Returns 0 if the request was accepted, non-zero if it could not be started (no
 * loop, null arguments, a path out of range, or the queue full). The path is
 * copied before returning, so the caller may reuse its buffer.
 *
 * Zero means the callback will run exactly once, later, on the loop thread.
 * "Later" means on a subsequent job_loop_run_once, and never before this function
 * returns. It does not run the loop itself, and must not: a caller may submit
 * from inside a completion callback, and uv_run is not reentrant.
 * Non-zero means it will NOT run — the two are not interchangeable, and a caller
 * that treats a refusal as a pending request waits forever. */
int job_file_read(const char *path, LoopReadCb cb, void *user);

/* Requests accepted and not yet completed, for a caller that needs to reach
 * quiescence and for the memory report. */
int job_pending(void);

/* Dispatches whatever is ready and returns. Never sleeps.
 *
 * The frame loop calls this once per frame, and it is the only thing that makes
 * completion callbacks fire. UV_RUN_NOWAIT rather than a default run, because a
 * frame that waited for work would hang the editor whenever nothing was
 * outstanding — which is nearly always. Returns 0, or -1 if the loop is not
 * initialised. */
int job_loop_run_once(void);

/* -- test-only observation ------------------------------------------------
 *
 * Compiled out entirely unless CDIN_JOB_TEST_HOOKS is defined, so the shipping
 * build has no hook symbol at all rather than a disabled code path.
 *
 * The hook is CALLED FROM THE LOOP THREAD at each stage of a read, which is the
 * main thread. It is not a worker-thread hook and cannot be used to park one:
 * libuv does its blocking file work on a pool thread, but delivers every callback
 * from uv_run on the loop thread, so blocking inside a callback blocks main.
 * An earlier version of this tried to park a worker that way and hung the suite.
 *
 * It is here for what it can do: report which stages ran, in order.
 */
typedef void (*JobTestHook)(const char *point, void *user);

/* Named rather than numbered so a test cannot silently depend on an ordering
 * that changes. */
#define JOB_HOOK_AFTER_OPEN   "after_open"    /* fd obtained */
#define JOB_HOOK_BEFORE_DONE  "before_done"   /* work finished, request not freed */

/* Installs the hook, or clears it with NULL. One at a time. */
void job_test_set_hook(JobTestHook hook, void *user);

/* Releases anything the hook machinery holds. A no-op, and present so a test's
 * cleanup reads the same whether or not hooks are enabled. */
void job_test_release(void);

#endif /* CDIN_LOOP_H */
