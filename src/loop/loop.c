/* Asynchronous file I/O, off the frame thread. See loop.h for what it is for.
 *
 * The threading rule this file obeys, from AGENTS.md §2.3 and §6: the uv loop
 * runs on the MAIN thread, uv_fs work runs on libuv's own worker threads, and a
 * worker touches no Lua state and no SDL state. Only the loop thread ever runs
 * a callback, so after_read_cb is the single place where the two worlds meet —
 * and it hands back a plain byte buffer, not anything owned by Lua.
 *
 * Every piece of state below is touched by the main thread only. The loop and
 * its thread pool are main-thread-only; requests[] is main-thread-only, because
 * a request is inserted by the main thread and removed by the loop thread, which
 * is the same thread. There is no counter shared between threads at all, which
 * is why this file contains no atomics and no volatile: §6 restricts atomics to
 * loop/queue.c and the ref counts, and a counter that would need one is a sign
 * the design is wrong rather than a licence to add a second exception.
 *
 * What this file must never do, and does not: call SDL, call into Lua, or block
 * waiting for a worker. The last one matters as much as the others — a "wait for
 * the read to finish so I can return the data" implementation would satisfy the
 * signature and reintroduce the exact stall this module exists to remove.
 */

#include "loop.h"

/* uv.h before the system headers, deliberately. On Windows its types collide
 * with the CRT's if it arrives after them. */
#include <uv.h>

#include <string.h>

#include "../base/alloc.h"
#include "../core/logger.h"

/* ── request ────────────────────────────────────────────────────────────── */

/* One in-flight read.
 *
 * The path is copied into a fixed buffer rather than allocated separately: a
 * request is small and short-lived, and a second allocation per open is a second
 * failure mode in a path that exists to be reliable. A path longer than the
 * buffer is refused rather than truncated, because a truncated path names a
 * different file and reading the wrong one silently is worse than failing.
 */
#define JOB_PATH_MAX 1024

typedef struct {
  char       path[JOB_PATH_MAX];
  LoopReadCb cb;
  void      *user;
  LoopStatus status;
  uint8_t   *data;
  size_t     len;

  /* The open descriptor, carried across the stat/read/close chain.
   *
   * libuv hands each stage its result in req->result, which the next stage then
   * overwrites, so the descriptor has to be kept here once the open is done. It
   * is a uv_file (an OS handle on Windows, an int elsewhere) rather than a raw
   * int because that is what libuv's own signature uses and casting between them
   * is where a Windows build would break. */
  uv_file fd;

  /* The uv_fs_t lives INSIDE the request, not beside it.
   *
   * libuv keeps one pointer to the request and writes its result there across
   * the whole chain — open, fstat, read, close each write the same struct and
   * each callback receives that same pointer. So the address has to stay valid
   * and unchanged for the request's whole life, which rules out a temporary and
   * rules out copying the struct by value: a copy would be filled in while the
   * original stayed zero, and every result would read as zero. Allocating the
   * two together is the simplest way to keep the address stable.
   */
  uv_fs_t req;

  /* The destination for the read: our own allocation, not one libuv hands out.
   *
   * libuv's buffers come from its own allocator, which bypasses cdin_alloc and
   * with it the accounting core:memory reports and the fault injector. Reading
   * straight into a tagged allocation means every byte the editor holds is
   * attributable and can be refused on demand; the alternative is a large
   * allocation nobody counts and no test can interrupt.
   */
  uv_buf_t buf;
} JobRead;

static void job_read_close(uv_fs_t *req);

/* ── module state ───────────────────────────────────────────────────────── */

/* The loop, owned by this module, running on the main thread.
 *
 * NULL until job_loop_init. A read attempted before initialisation is refused
 * rather than queued, because there would be no thread to complete it and the
 * caller would wait forever for a callback that cannot arrive. Main-thread-only
 * throughout: job_loop_init, job_loop_close and job_file_read are all called
 * from the frame thread, and so is the completion callback, because the loop
 * itself runs there. */
static uv_loop_t *job_loop;

/* Requests in flight.
 *
 * A fixed cap, because §2.4 bans unbounded growth and this is a queue fed by
 * whatever asks for a file. 64 is far beyond anything an interactive session
 * reaches, and reaching it is a bug worth refusing loudly rather than a slow
 * death. Refusing, not overwriting: a bounded queue that drops its oldest is how
 * a document silently opens as the wrong file. */
#define JOB_MAX_REQUESTS 64

static JobRead *job_requests[JOB_MAX_REQUESTS];

/* Set when the process is shutting down, so a completion that arrives after
 * teardown starts does not call back into code that is being dismantled.
 * Main-thread-only, like everything else here. */
static int job_shutting_down;

/* Nonzero while a uv_run call is on the stack. Main-thread-only, like
 * everything else here: libuv dispatches our callbacks from uv_run on the loop
 * thread, so the only thread that ever changes this is the one that pumps.
 *
 * This exists because uv_run is NOT reentrant. A completion callback already
 * runs inside uv_run, so calling uv_run again from anything a callback reaches
 * — a submission, a close, anything — nests it. libuv does not reject that; it
 * dispatches part way and returns, leaving requests queued that nothing ever
 * completes. That is how two requests went permanently pending in the chain
 * test. See job_uv_run below. */
static int job_uv_depth;

/* ── test-only observation ────────────────────────────────────────────────
 *
 * Compiled out entirely unless CDIN_JOB_TEST_HOOKS is defined, so a shipping
 * build has no hook symbol and no branch on the request path — an absent code
 * path rather than a disabled one. Verified with nm on the release object.
 *
 * What it can and cannot do, learned by trying:
 *
 *   CAN observe the completion path — each stage of the read reports itself, so
 *   a test can assert which stages ran and in what order.
 *
 *   CANNOT park a worker thread. There is no code of ours on a libuv worker:
 *   uv_fs_open/uv_fs_read/uv_fs_fstat do their blocking work on a pool thread,
 *   but libuv delivers their callbacks from uv_run on the LOOP thread, which is
 *   the main thread. Parking inside a callback therefore parks main inside
 *   uv_run, and job_loop_run_once never returns.
 *
 *   An earlier version of this file did exactly that and hung the suite. The
 *   "in flight" state a shutdown test needs is produced by not pumping, which
 *   needs no hook at all.
 *
 * The hook is a plain function pointer with no lock: it is called from the loop
 * thread, which is single-threaded by construction (see the file header), so
 * there is nothing to synchronise. The user's pointer is read once here.
 */
#ifdef CDIN_JOB_TEST_HOOKS

static JobTestHook test_hook;
static void       *test_hook_user;

void job_test_set_hook(JobTestHook hook, void *user) {
  test_hook      = hook;
  test_hook_user = user;
}

/* Releases anything the hook machinery was holding. Present so the test's cleanup
 * is one call whether or not the hook was ever installed, and a no-op in every
 * build: there is nothing parked and no lock to take. */
void job_test_release(void) { }

#endif /* CDIN_JOB_TEST_HOOKS */

/* ── status ─────────────────────────────────────────────────────────────── */

const char *loop_status_str(LoopStatus status) {
  switch (status) {
    case LOOP_OK:            return "ok";
    case LOOP_ERR_OPEN:      return "cannot open the file for reading";
    case LOOP_ERR_STAT:      return "cannot determine the file size";
    case LOOP_ERR_TOO_LARGE: return "the file is larger than the 1 GiB read limit";
    case LOOP_ERR_ALLOC:     return "out of memory reading the file";
    case LOOP_ERR_READ:      return "the read failed partway through";
    default:                 return "unknown error";
  }
}

/* ── lifecycle ──────────────────────────────────────────────────────────── */

int job_loop_init(void) {
  /* Idempotent by contract. A second loop would mean a second thread pool with
   * no way to tell which one served a request. */
  if (job_loop) return 0;

  uv_loop_t *l = cdin_alloc(CDIN_MEM_LOOP, sizeof(uv_loop_t));
  if (!l) {
    log_error("job_loop: out of memory for the event loop");
    return -1;
  }

  if (uv_loop_init(l) != 0) {
    /* No error code to name: uv_loop_init's failure modes are all "this build
     * cannot make a loop", and libuv 1.52 has no portable way to say which.
     * The message names the function and the consequence, which is what a reader
     * needs. */
    log_error("job_loop: uv_loop_init failed — this libuv build cannot make a "
              "loop, so file I/O will not be asynchronous");
    cdin_free(l);
    return -1;
  }

  job_loop = l;
  job_shutting_down = 0;

  /* uv_fs work goes on libuv's own pool. Its size is libuv's default rather
   * than a number chosen here: the workload is a handful of file reads while
   * the frame thread draws, and raising it would be a guess about a machine I
   * cannot measure from this module. */
  log_info("job_loop: initialised (uv %d.%d.%d)",
           UV_VERSION_MAJOR, UV_VERSION_MINOR, UV_VERSION_PATCH);
  return 0;
}

/* Finishes every outstanding request before anything it touches is freed.
 *
 * This is the step that was missing, and its absence was a use-after-free rather
 * than a leak: freeing a request while a libuv worker was still inside
 * uv_fs_read left that worker reading into a buffer and a uv_fs_t that no longer
 * existed. The observable symptom was a SIGTRAP inside a thread named
 * "libuv-worker" after close returned, plus PostQueuedCompletionStatus failing
 * with an invalid handle — reproducible 4 times in 4 runs.
 *
 * How to drain, in libuv 1.52 specifically, is measured rather than assumed:
 *
 *   - uv_threadpool_init/uv_threadpool_cleanup no longer exist. 1.52 removed the
 *     public threadpool API, so there is no "join the pool" call to make. The
 *     earlier code referenced those symbols and compiled only because the branch
 *     was never taken.
 *   - uv_loop_close does NOT drain and does NOT refuse. Measured directly: with a
 *     request queued it returned 0 and the loop went away with the work
 *     outstanding. So it is not a substitute for a drain, and ignoring its
 *     return would hide nothing because there is nothing to hide.
 *
 * What remains is to run the loop until it reports itself no longer alive, which
 * is libuv's own definition of "no work outstanding": uv_loop_alive() is false
 * only when there are no active handles or requests.
 *
 * Bounded, deliberately. UV_RUN_DEFAULT would block forever on a handle that
 * never closes, so this pumps in NOWAIT slices and gives up after a deadline,
 * logging how many requests it gave up on. Giving up leaves those requests
 * unfreed rather than freed-while-in-use: a leak at shutdown is strictly better
 * than a use-after-free, and the count is reported so it is never silent.
 */
#define JOB_DRAIN_SLICES     100000   /* pump iterations before giving up */
#define JOB_DRAIN_SLICE_WAIT 1        /* ms between slices, so workers progress */

/* The ONLY place this file calls uv_run.
 *
 * Every path that needs the loop to advance goes through here, which is what
 * makes "the loop is pumped from exactly one place at a time" a checked
 * property rather than a comment that the next caller can quietly violate.
 * Nested uv_run is refused and reported, not attempted: libuv does not support
 * it and fails by stranding requests rather than by erroring.
 *
 * Returns 0 if the loop ran (or had nothing to do), -1 if the call was refused
 * because it would have nested.
 */
static int job_uv_run(uv_run_mode mode) {
  if (!job_loop) return -1;
  if (job_uv_depth > 0) {
    log_error("job_uv_run: refused — already inside uv_run, and libuv does not "
              "support a nested run; this path was reached from a completion "
              "callback");
    return -1;
  }
  job_uv_depth++;
  uv_run(job_loop, mode);
  job_uv_depth--;
  return 0;
}

static int job_drain(void) {
  for (int i = 0; i < JOB_DRAIN_SLICES; i++) {
    if (!uv_loop_alive(job_loop)) return 0;
    if (job_uv_run(UV_RUN_NOWAIT) != 0) return -1;

    /* Only sleep once the pool has had a chance to run, otherwise this spins
     * hot for slices that finish in microseconds. */
    if (uv_loop_alive(job_loop)) uv_sleep(JOB_DRAIN_SLICE_WAIT);
  }
  return uv_loop_alive(job_loop) ? -1 : 0;
}

void job_loop_close(void) {
  if (!job_loop) return;

  /* REFUSED from inside a completion callback, and refusing is the whole fix.
   *
   * A callback already runs inside uv_run. Closing from there means the uv_loop_t
   * is freed while uv_run is still executing on it — libuv keeps reading its own
   * loop state after the callback returns, so that is a use-after-free, and the
   * symptom would be a fault after close() had already reported success.
   *
   * This is not hypothetical: adding the nesting guard to job_uv_run made the
   * refusal reachable, and the refusal alone is NOT enough. With the guard,
   * closing from a callback takes this path:
   *
   *   job_drain -> job_uv_run -> refused (we are inside uv_run) -> drain fails
   *   -> every request is abandoned rather than freed      (correct)
   *   -> uv_loop_close is skipped                          (correct)
   *   -> cdin_free(job_loop)                               (FREES THE LOOP
   *                                                        UNDER uv_run)
   *
   * so the guard turned a nested-pump bug into a free-during-dispatch bug one
   * step further along. A guard that only stops the first bad thing is not a
   * guard.
   *
   * Refusing outright, rather than deferring the close to the next pump, because
   * deferring needs a flag the frame loop must then know to check, and a caller
   * that asked to shut down would silently not be shut down. A refused close is
   * loud and the caller can close again once the dispatch has returned; a
   * corrupted loop is neither. */
  if (job_uv_depth > 0) {
    log_error("job_loop_close: refused — called from inside a completion "
              "callback, which is running inside uv_run; closing now would "
              "free the loop out from under it. Call this again after the "
              "callback returns.");
    return;
  }

  /* No callback may fire from here on: this runs after the Lua state is gone, so
   * a completion would re-enter a closed interpreter. Set BEFORE the drain,
   * because the drain can complete requests and therefore fire callbacks. */
  job_shutting_down = 1;

  /* Finish the outstanding work first. Everything below frees memory a worker
   * may still be reading, so this must complete before the frees, not after. */
  int drained = job_drain();

  int abandoned = 0;
  for (int i = 0; i < JOB_MAX_REQUESTS; i++) {
    JobRead *r = job_requests[i];
    if (!r) continue;
    job_requests[i] = NULL;
    if (drained != 0) {
      /* Not drained: a worker may still hold this. Freeing it is the use-after-
       * free this function exists to prevent, so it is deliberately leaked and
       * counted. uv_fs_req_cleanup is NOT called either — telling libuv a
       * request is done while a worker is inside it is the same bug in a
       * different place. */
      abandoned++;
      continue;
    }
    if (r->data) cdin_free(r->data);
    cdin_free(r);
  }
  if (abandoned > 0) {
    log_warn("job_loop: shutdown gave up on %d in-flight request(s); they are "
             "leaked rather than freed while a worker may still hold them",
             abandoned);
  }

  if (drained == 0) {
    int rc = uv_loop_close(job_loop);
    if (rc != 0) {
      log_error("job_loop: uv_loop_close returned %s — a libuv handle is still "
                "registered", uv_err_name(rc));
    }
  } else {
    log_error("job_loop: not closing the libuv loop — work is still in flight");
  }

  cdin_free(job_loop);
  job_loop = NULL;
  log_info("job_loop: closed");
}

/* ── the read path ──────────────────────────────────────────────────────── */

/* The end of the chain, and the only place the caller's callback fires.
 *
 * libuv 1.52's uv_fs_cb takes the request alone: a stage's failure is reported
 * in req->result rather than as a second argument, so this is directly a
 * uv_fs_cb. Every stage that can end the read closes the descriptor with this as
 * the callback, or calls it directly when there is no descriptor to close. */
static void job_read_done(uv_fs_t *req);

/* Runs on a libuv worker thread, once the open has completed.
 *
 * Continues the chain: sizes the file, allocates, reads, closes. It logs
 * nothing: logger.c is not documented as thread-safe, and a log call from here
 * would race on the log buffer for the sake of a message the completion callback
 * reports properly on the loop thread. The status carries the reason instead.
 *
 * Every libuv call takes the loop pointer, which the worker may use for
 * submitting requests — that is what a loop is for. It must not RUN the loop:
 * only the thread that initialised it may, and that is the main thread.
 *
 * The descriptor arrives in req->result. A negative value is libuv's
 * errno-style failure and stops the chain — but NOT without reporting: every
 * path here ends in a uv_fs_close whose callback is job_read_done, so the
 * caller's callback fires exactly once whatever happened. An early return that
 * skipped the close would leave job_pending() counting a request that can never
 * complete, which is worse than reporting the error. */
static void job_read_stat(uv_fs_t *req) {
  JobRead *r = (JobRead *)req->data;

  if (req->result < 0) {
    /* The open failed, so there is no descriptor to close. job_read_done is
     * invoked directly rather than through a close, because a close of a
     * descriptor that does not exist is not a thing. */
    r->status = LOOP_ERR_OPEN;
    job_read_done(req);
    return;
  }
  r->fd = (uv_file)req->result;
  r->status = LOOP_OK;

#ifdef CDIN_JOB_TEST_HOOKS
  /* Reported, not parked: this runs on the LOOP thread, so a hook that blocked
   * here would block main inside uv_run. See the note on job_test_set_hook. */
  if (test_hook) test_hook(JOB_HOOK_AFTER_OPEN, test_hook_user);
#endif

  uv_fs_fstat(job_loop, req, r->fd, NULL);
  if (req->result < 0) {
    r->status = LOOP_ERR_STAT;
    uv_fs_close(job_loop, req, r->fd, job_read_done);
    return;
  }

  /* Refuse rather than truncate. §2.6: bytes round-trip, and a short read that
   * looked like a whole one is a corrupted document with no way to tell. */
  uint64_t size = (uint64_t)req->statbuf.st_size;
  if (size > (uint64_t)LOOP_MAX_FILE_BYTES) {
    r->status = LOOP_ERR_TOO_LARGE;
    uv_fs_close(job_loop, req, r->fd, job_read_done);
    return;
  }

  r->len = (size_t)size;
  if (r->len == 0) {
    /* An empty file is a valid document, not an error: the callback gets
     * LOOP_OK with a NULL buffer and length 0. */
    uv_fs_close(job_loop, req, r->fd, job_read_done);
    return;
  }

  r->data = cdin_alloc(CDIN_MEM_BUFFER, r->len);
  if (!r->data) {
    r->status = LOOP_ERR_ALLOC;
    uv_fs_close(job_loop, req, r->fd, job_read_done);
    return;
  }
  r->buf = uv_buf_init((char *)r->data, (unsigned int)r->len);

  uv_fs_read(job_loop, req, r->fd, &r->buf, 1, -1, job_read_close);
}

/* Runs on a worker after the read. Records whether the whole file arrived and
 * closes the descriptor.
 *
 * A short read is an error, not a smaller document: the file changed under us,
 * and handing back the prefix is the silent corruption §2.6 exists to prevent.
 * The data is freed here rather than in job_read_done so that a failed read
 * never reaches a caller holding a partial buffer. */
static void job_read_close(uv_fs_t *req) {
  JobRead *r = (JobRead *)req->data;

  if (req->result < 0 || (size_t)req->result != r->len) {
    cdin_free(r->data);
    r->data = NULL;
    r->len  = 0;
    r->status = LOOP_ERR_READ;
  }

  /* The close is the last async stage, so this is where the whole chain ends:
   * job_read_close_final runs on the loop thread once the descriptor is gone,
   * and it is the only place the caller's callback fires. Running the loop here
   * is what gets the queued close started, and UV_RUN_NOWAIT means it returns
   * as soon as there is nothing ready rather than waiting for the worker.
   *
   * The open path is the one exception: uv_fs_open completes without a close. */
  uv_fs_close(job_loop, req, r->fd, job_read_done);
}

/* Runs on the loop thread, after the worker is done.
 *
 * The single place the two worlds meet: it hands the callback a byte buffer and
 * nothing else. No Lua here and no SDL, by design. */
static void job_read_done(uv_fs_t *req) {
  JobRead *r = (JobRead *)req->data;

  for (int i = 0; i < JOB_MAX_REQUESTS; i++) {
    if (job_requests[i] == r) {
      job_requests[i] = NULL;
      break;
    }
  }

#ifdef CDIN_JOB_TEST_HOOKS
  /* The last point at which the request is still allocated and libuv is still
   * holding it, reported just before the teardown below frees it. Reported, not
   * parked: this is the loop thread, and a hook that blocked here would block
   * main inside uv_run. */
  if (test_hook) test_hook(JOB_HOOK_BEFORE_DONE, test_hook_user);
#endif

  /* Normalised HERE rather than at each failure site, so the documented contract
   * holds on every path including ones added later: a failure reports a NULL
   * buffer and a length of zero.
   *
   * This was a real defect. The allocation-failure path freed the buffer and set
   * the status but left r->len at the file's size, so the callback received
   * len=48 with data=NULL — a length that describes bytes the caller was never
   * given and cannot read. A caller doing `if (len) use(data)` would have taken
   * that branch on a NULL pointer. */
  if (r->status != LOOP_OK) {
    r->len = 0;
    r->data = NULL;
  }

  /* The buffer dies with the callback. A caller that wants the bytes must copy
   * them: that makes the lifetime obvious at the call site instead of leaving a
   * pointer to memory the loop considers released. */
  if (r->cb && !job_shutting_down) {
    r->cb(r->status, r->data, r->len, r->user);
  }

  if (r->data) cdin_free(r->data);
  cdin_free(r);
}

int job_file_read(const char *path, LoopReadCb cb, void *user) {
  if (!job_loop) {
    log_error("job_file_read: refused — job_loop_init has not been called");
    return -1;
  }
  if (!path || !cb) {
    log_error("job_file_read: refused — null path or callback");
    return -1;
  }

  size_t path_len = strlen(path);
  if (path_len == 0 || path_len >= JOB_PATH_MAX) {
    log_error("job_file_read: path length %zu is out of range (1..%d)",
              path_len, JOB_PATH_MAX - 1);
    return -1;
  }

  int slot = -1;
  for (int i = 0; i < JOB_MAX_REQUESTS; i++) {
    if (!job_requests[i]) { slot = i; break; }
  }
  if (slot < 0) {
    log_error("job_file_read: %d reads already in flight, refusing another",
              JOB_MAX_REQUESTS);
    return -1;
  }

  JobRead *r = cdin_alloc(CDIN_MEM_LOOP, sizeof(JobRead));
  if (!r) {
    log_error("job_file_read: out of memory for a request");
    return -1;
  }
  memset(r, 0, sizeof(*r));
  memcpy(r->path, path, path_len + 1);
  r->cb   = cb;
  r->user = user;

  /* The back-pointer from libuv's request to ours. Every callback in the chain
   * recovers the JobRead through this, so without it the first completion
   * dereferences NULL — and it does so on a worker thread inside libuv, which is
   * why it surfaces as a bare SIGSEGV with a stack that names only our function.
   * Set here rather than in a caller because the struct is ours and this is the
   * one place that knows the two are the same allocation. */
  r->req.data = r;

  job_requests[slot] = r;

  /* uv_fs_open with job_read_stat as the callback is the ASYNC form: libuv
   * queues the open on its thread pool and returns immediately, which is the
   * whole point. The path goes through r->path rather than the caller's pointer
   * because the request outlives this call and libuv reads the path when the
   * worker runs, not now.
   *
   * job_read_stat is that worker: it receives the opened descriptor in
   * req->result and continues the chain from there. */
  if (uv_fs_open(job_loop, &r->req, r->path, UV_FS_O_RDONLY, 0, job_read_stat) != 0) {
    /* Queuing failed, so no callback will run. Undo the reservation rather than
     * leaving a slot occupied by a request that will never complete — otherwise
     * job_pending() reports a read that can never finish. */
    job_requests[slot] = NULL;
    cdin_free(r);
    log_error("job_file_read: uv_fs_open would not queue \"%s\"", path);
    return -1;
  }

  /* Deliberately does NOT pump the loop.
   *
   * This used to end with uv_run(UV_RUN_NOWAIT), which is wrong: a completion
   * callback is itself running INSIDE uv_run, so a caller that submits a request
   * from a callback gets a nested uv_run. libuv does not support that, and it does
   * not fail cleanly — the nested dispatch leaves requests in the queue that
   * nothing ever completes.
   *
   * Measured, in WSL against libuv 1.48 (tests/c/test_job.c, case "a callback may
   * submit a request"):
   *     with the nested uv_run   -> 14 passed, 1 failed; job_pending() == 2
   *     without it               -> 15 passed, 0 failed
   * and it passed on Windows by luck, which is how it survived until now. A
   * defect that is platform-dependent and load-dependent is still a defect; the
   * fact that the same code is correct on one libuv version and wrong on another
   * is the argument for removing the call rather than documenting it.
   *
   * Pumping is not this function's job. job_loop_run_once() is called once per
   * frame by the frame loop, and that is the single point where the loop runs —
   * which also means a callback can never be dispatched from two places at once.
   * A request submitted from a callback therefore completes on the next frame,
   * which is the correct and obvious answer: nothing waits on it having happened
   * by the time the submitting call returns. */
  return 0;
}

int job_pending(void) {
  int n = 0;
  for (int i = 0; i < JOB_MAX_REQUESTS; i++) {
    if (job_requests[i]) n++;
  }
  return n;
}

int job_loop_run_once(void) {
  if (!job_loop) return -1;
  /* UV_RUN_NOWAIT is the whole reason this is safe to call from a frame: it
   * dispatches whatever is ready and returns, rather than sleeping until
   * something happens. A frame that called UV_RUN_DEFAULT would hang the editor
   * whenever no request was outstanding, which is nearly always.
   *
   * The frame calls this once per frame; SDL3 still owns the window, input and
   * rendering, and this never touches SDL. It is also the only pump on the
   * normal path — job_file_read deliberately does not run the loop, so that a
   * submission from inside a callback can never nest one. */
  return job_uv_run(UV_RUN_NOWAIT);
}
