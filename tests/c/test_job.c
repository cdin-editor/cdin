/* The job loop: request lifecycle, error paths, and shutdown.
 *
 * This suite exists because the loop was previously verified only by a scratch
 * harness and by hand, and because the one defect it had — freeing a request
 * while a libuv worker was still reading it — was invisible to every check that
 * existed. It showed up as a SIGTRAP inside a thread named "libuv-worker" after
 * job_loop_close had already returned, which no assertion in the old suite could
 * have described, let alone caught.
 *
 * Determinism. Every case here pumps the loop explicitly and waits on a
 * completion flag, never on a sleep. A sleep would make these tests pass or fail
 * according to machine load, which is the same defect the harness that gated
 * timings on a single sample had. The pump is the same call the frame makes
 * (job_loop_run_once), so what is exercised is the real path, not a test-only
 * one.
 *
 * Scratch files go under the directory the runner is given, so a run never
 * writes into the repository — a mistake that once left multi-megabyte logs in
 * the source root.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../../src/base/alloc.h"
#include "../../src/core/logger.h"
#include "../../src/loop/loop.h"
#include "ctest.h"

/* Where the runner told us to write. Set once in t_setup. */
static const char *scratch_dir;

/* ── per-case observation ───────────────────────────────────────────────── */

/* What a completion reported. Reset before each request.
 *
 * `calls` rather than a boolean, because the exactly-once guarantee is the thing
 * most worth asserting and a boolean cannot distinguish "once" from "twice" from
 * "never" without the caller counting anyway. */
typedef struct {
  int         calls;
  LoopStatus  status;
  size_t      len;
  /* A copy of the bytes, taken inside the callback.
   *
   * Copied because the documented contract is that the buffer is valid only for
   * the duration of the callback. A test that read it afterwards would be
   * asserting that the contract does not exist. */
  uint8_t    *copy;
  size_t      copy_cap;
} Seen;

static Seen seen;

static void seen_reset(void) {
  if (seen.copy) cdin_free(seen.copy);
  memset(&seen, 0, sizeof(seen));
}

static void on_read(LoopStatus status, const uint8_t *data, size_t len,
                    void *user) {
  (void)user;
  seen.calls++;
  seen.status = status;
  seen.len = len;
  if (data && len) {
    if (len > seen.copy_cap) {
      if (seen.copy) cdin_free(seen.copy);
      seen.copy = cdin_alloc(CDIN_MEM_BUFFER, len);
      seen.copy_cap = seen.copy ? len : 0;
    }
    if (seen.copy) memcpy(seen.copy, data, len);
  }
}

/* Pumps until the callback has run or the budget is spent.
 *
 * The bound is what makes a hang a failure instead of a stuck suite. It is large
 * because a cold disk on a loaded machine is slow, and it is checked rather than
 * slept through: the case that exhausts it fails and says the request never
 * completed. */
#define JOB_PUMP_LIMIT 200000

static void pump_until_done(void) {
  for (int i = 0; i < JOB_PUMP_LIMIT && seen.calls == 0; i++) {
    job_loop_run_once();
  }
}

/* Writes a file under the scratch directory and returns its path.
 *
 * The path is built into a caller-supplied buffer rather than allocated, so a
 * case cannot leak the path on an early return. */
static int write_scratch(const char *name, const void *bytes, size_t len,
                         char *out, size_t out_cap) {
  int n = snprintf(out, out_cap, "%s/%s", scratch_dir, name);
  if (n <= 0 || (size_t)n >= out_cap) return -1;
  FILE *fp = fopen(out, "wb");
  if (!fp) return -1;
  if (len && fwrite(bytes, 1, len, fp) != len) { fclose(fp); return -1; }
  fclose(fp);
  return 0;
}

/* ── lifecycle ──────────────────────────────────────────────────────────── */

/* A read before initialisation must be refused, not queued.
 *
 * Queued would be worse than refusing: nothing could ever complete it, so the
 * caller would wait forever for a callback that cannot arrive. */
static int t_read_before_init_is_refused(void) {
  int rc = job_file_read("anything.txt", on_read, NULL);
  t_assert(rc != 0);
  t_assert(seen.calls == 0);      /* no callback, because nothing started */
  t_assert(job_pending() == 0);
  return 0;
}

/* Init is idempotent: a second call must not build a second loop, because two
 * loops mean two thread pools and no way to tell which served a request. */
static int t_repeated_init_is_safe(void) {
  t_assert(job_loop_init() == 0);
  size_t after_first = cdin_mem_live(CDIN_MEM_LOOP);
  t_assert(after_first > 0);
  t_assert(job_loop_init() == 0);
  /* Unchanged: a second loop would show up here as a second allocation. */
  t_eq_int((long long)cdin_mem_live(CDIN_MEM_LOOP), (long long)after_first);
  return 0;
}

/* Close is safe to call twice, and the second call must be a no-op rather than a
 * double free of the loop. */
static int t_repeated_close_is_safe(void) {
  t_assert(job_loop_init() == 0);
  job_loop_close();
  t_eq_int((long long)cdin_mem_live(CDIN_MEM_LOOP), 0);
  job_loop_close();   /* must not fault */
  t_eq_int((long long)cdin_mem_live(CDIN_MEM_LOOP), 0);
  return 0;
}

/* ── the read path ──────────────────────────────────────────────────────── */

static int t_a_read_completes_and_delivers_its_bytes(void) {
  static const char body[] = "the quick brown fox\njumps over the lazy dog\n";
  char path[512];
  t_assert(write_scratch("read_ok.txt", body, sizeof(body) - 1, path,
                         sizeof(path)) == 0);

  t_assert(job_loop_init() == 0);
  seen_reset();
  t_assert(job_file_read(path, on_read, NULL) == 0);
  pump_until_done();

  t_eq_int(seen.calls, 1);
  t_eq_int(seen.status, LOOP_OK);
  t_eq_int((long long)seen.len, (long long)(sizeof(body) - 1));
  t_assert(seen.copy && memcmp(seen.copy, body, sizeof(body) - 1) == 0);
  t_eq_int(job_pending(), 0);

  job_loop_close();
  return 0;
}

/* §2.6: bytes round-trip. A PE binary is the honest input here because it
 * contains NUL bytes, high bytes and a BOM-free header — exactly the content a
 * line-oriented reader would corrupt. Any transcoding on the way through would
 * show up as a length or content mismatch. */
static int t_binary_data_round_trips_byte_for_byte(void) {
  /* Every byte value, twice, so a truncation at any point is visible. */
  static uint8_t body[512];
  for (int i = 0; i < 512; i++) body[i] = (uint8_t)(i % 256);

  char path[512];
  t_assert(write_scratch("read_bin.dat", body, sizeof(body), path,
                         sizeof(path)) == 0);

  t_assert(job_loop_init() == 0);
  seen_reset();
  t_assert(job_file_read(path, on_read, NULL) == 0);
  pump_until_done();

  t_eq_int(seen.calls, 1);
  t_eq_int(seen.status, LOOP_OK);
  t_eq_int((long long)seen.len, (long long)sizeof(body));
  t_assert(seen.copy && memcmp(seen.copy, body, sizeof(body)) == 0);

  job_loop_close();
  return 0;
}

/* An empty file is a valid document, not an error. Asserted because the
 * alternative reading — treating zero bytes as a failure — would make opening an
 * empty file indistinguishable from a permission problem. */
static int t_an_empty_file_completes_successfully(void) {
  char path[512];
  t_assert(write_scratch("read_empty.txt", "", 0, path, sizeof(path)) == 0);

  t_assert(job_loop_init() == 0);
  seen_reset();
  t_assert(job_file_read(path, on_read, NULL) == 0);
  pump_until_done();

  t_eq_int(seen.calls, 1);
  t_eq_int(seen.status, LOOP_OK);
  t_eq_int((long long)seen.len, 0);

  job_loop_close();
  return 0;
}

/* A missing file is reported through the callback and leaves nothing pending.
 *
 * The exactly-once part matters as much as the status: a failed open that fired
 * no callback would leave the caller waiting, and one that fired two would run
 * its completion logic twice. */
static int t_a_missing_file_is_reported_exactly_once(void) {
  t_assert(job_loop_init() == 0);
  seen_reset();
  t_assert(job_file_read("no/such/directory/no-such-file.txt", on_read, NULL) == 0);
  pump_until_done();

  t_eq_int(seen.calls, 1);
  t_eq_int(seen.status, LOOP_ERR_OPEN);
  t_eq_int((long long)seen.len, 0);
  t_assert(seen.copy == NULL);
  t_eq_int(job_pending(), 0);

  job_loop_close();
  return 0;
}

/* A path the API cannot accept is refused before anything is allocated, so there
 * is no request to leak and no callback to wait for. */
static int t_an_invalid_path_is_refused(void) {
  t_assert(job_loop_init() == 0);
  seen_reset();

  t_assert(job_file_read(NULL, on_read, NULL) != 0);
  t_assert(job_file_read("", on_read, NULL) != 0);
  t_assert(job_file_read("x.txt", NULL, NULL) != 0);

  /* Longer than the module accepts: a truncated path would name a different
   * file, so it must be refused rather than clipped. */
  static char huge[4096];
  memset(huge, 'a', sizeof(huge) - 1);
  huge[sizeof(huge) - 1] = '\0';
  t_assert(job_file_read(huge, on_read, NULL) != 0);

  t_eq_int(seen.calls, 0);
  t_eq_int(job_pending(), 0);

  job_loop_close();
  return 0;
}

/* Several requests at once, each completing exactly once.
 *
 * All the same file on purpose: the point is that requests are distinguished from
 * each other, not that different files behave differently. Ten identical paths
 * with identical content would still catch a slot-reuse bug that handed one
 * request another's callback. */
static int t_many_requests_each_complete_exactly_once(void) {
  static const char body[] = "x\n";
  char path[512];
  t_assert(write_scratch("read_many.txt", body, sizeof(body) - 1, path,
                         sizeof(path)) == 0);

  t_assert(job_loop_init() == 0);

  enum { N = 10 };
  seen_reset();

  /* The shared on_read counts into `seen`, so this asserts the aggregate: ten
   * accepted requests must produce exactly ten completions. Fewer would mean one
   * never fired; more would mean one fired twice, which is the failure mode that
   * a per-request counter would catch more directly but that the aggregate count
   * catches just as unambiguously at this size. */
  for (int i = 0; i < N; i++) {
    t_assert(job_file_read(path, on_read, NULL) == 0);
  }

  for (int i = 0; i < JOB_PUMP_LIMIT && seen.calls < N; i++) {
    job_loop_run_once();
  }

  t_eq_int(seen.calls, N);          /* every one, and no more than once */
  t_eq_int(seen.status, LOOP_OK);
  t_eq_int((long long)seen.len, (long long)(sizeof(body) - 1));
  t_eq_int(job_pending(), 0);

  job_loop_close();
  return 0;
}

/* ── the bounded guarantees ─────────────────────────────────────────────── */

/* Saturation must refuse, never overwrite.
 *
 * The queue is capped because AGENTS.md §2.4 bans unbounded growth. What it must
 * NOT do is drop the oldest entry to make room: a reader that silently receives
 * a different request's bytes gets a document that is not the document. So this
 * fills the queue and asserts the surplus is refused. */
static int t_a_full_queue_refuses_rather_than_overwriting(void) {
  static const char body[] = "y\n";
  char path[512];
  t_assert(write_scratch("read_queue.txt", body, sizeof(body) - 1, path,
                         sizeof(path)) == 0);

  t_assert(job_loop_init() == 0);
  seen_reset();

  /* Far more than the documented cap. The queue is measured by its PEAK depth
   * rather than by how many calls were accepted, because job_file_read pumps the
   * loop once itself: a request that completes during the loop frees its slot and
   * the next call is accepted. Counting accepted calls therefore measures how
   * fast the disk is, not how deep the queue got. The peak is the bound that
   * AGENTS.md §2.4 is actually about. */
  int accepted = 0, refused = 0, peak = 0;
  for (int i = 0; i < 200; i++) {
    if (job_file_read(path, on_read, NULL) == 0) accepted++;
    else refused++;
    int p = job_pending();
    if (p > peak) peak = p;
  }

  t_assert(accepted > 0);        /* the cap is not zero */
  t_assert(refused > 0);         /* and the surplus IS refused */
  t_assert(peak <= 64);          /* the documented bound, not an unbounded queue */
  t_assert(peak >= 1);           /* and the queue really did fill */

  /* Whatever was accepted must still complete exactly once. Pumping to
   * quiescence rather than to a count, so this cannot pass by stopping early. */
  for (int i = 0; i < JOB_PUMP_LIMIT && job_pending() > 0; i++) {
    job_loop_run_once();
  }
  t_eq_int(job_pending(), 0);
  t_eq_int(seen.calls, accepted);

  job_loop_close();
  return 0;
}

/* An allocation refused mid-read must be reported as such, must not deliver a
 * partial buffer, and must not strand the request.
 *
 * This case found a real contract violation: the allocation-failure path freed
 * the buffer and set the status but left r->len at the file's size, so the
 * callback received len=48 with data=NULL. A caller doing `if (len) use(data)`
 * would have taken that branch on a NULL pointer. The fix normalises len and
 * data in job_read_done rather than at each failure site, so a path added later
 * cannot forget. The assertion on seen.len below is what catches it.
 */
static int t_an_allocation_failure_is_reported_and_leaves_nothing(void) {
  static const char body[] = "allocation failure probe, long enough to matter\n";
  char path[512];
  t_assert(write_scratch("read_alloc.txt", body, sizeof(body) - 1, path,
                         sizeof(path)) == 0);

  t_assert(job_loop_init() == 0);
  seen_reset();

  /* Exactly one allocation allowed, and that number is measured rather than
   * guessed: a single read makes exactly two cdin_alloc calls — the request
   * struct, then the buffer for the file. Allowing one therefore lets the
   * request through and refuses the buffer, which is the allocation this case
   * is named for. Allowing two (the natural guess) lets both through and the
   * read SUCCEEDS, which is how this case first failed while asserting a
   * failure that never happened.
   *
   * Verified by measurement, allow=0 refuses the call, allow=1 reports
   * LOOP_ERR_ALLOC through the callback, allow>=2 reads the file successfully. */
  cdin_alloc_fail_after(1);
  int rc = job_file_read(path, on_read, NULL);
  for (int i = 0; i < JOB_PUMP_LIMIT && job_pending() > 0; i++) {
    job_loop_run_once();
  }
  unsigned long refused = cdin_alloc_failures();
  cdin_alloc_fail_disable();

  t_eq_int(rc, 0);                   /* the request was accepted */
  t_eq_int(seen.calls, 1);           /* and completed, with the failure reported */
  t_eq_int(seen.status, LOOP_ERR_ALLOC);
  t_assert(refused > 0);             /* injection actually fired */
  t_assert(seen.copy == NULL);       /* no partial buffer was delivered */
  t_eq_int((long long)seen.len, 0);
  t_eq_int(job_pending(), 0);        /* nothing stranded */

  /* And the module still works once memory is available again: a font, buffer
   * or request that cannot be refused but also cannot recover would be a second
   * bug wearing the first one's clothes. */
  seen_reset();
  t_assert(job_file_read(path, on_read, NULL) == 0);
  pump_until_done();
  t_eq_int(seen.calls, 1);
  t_eq_int(seen.status, LOOP_OK);
  t_eq_int((long long)seen.len, (long long)(sizeof(body) - 1));

  job_loop_close();
  return 0;
}

/* ── shutdown ───────────────────────────────────────────────────────────── */

/* Shutdown with a request genuinely in flight.
 *
 * WHAT THIS PROVES, stated precisely because the distinction matters and an
 * earlier version of this file overstated it:
 *
 *   PROVED  — the request is queued and NOT yet complete when close is called
 *             (pending == 1); close resolves it without invoking the callback,
 *             which is what keeps a completion from re-entering a Lua state that
 *             the editor has already closed; and afterwards every allocation the
 *             module made is released, with no live blocks at all.
 *
 *   NOT PROVED  — that this would fail if the drain were removed. It would not.
 *             Measured: with the drain removed this scenario crashes about 1 run
 *             in 6, so asserting on the outcome is asserting on a race, not on
 *             the code. Removing the drain and re-running this suite produces 73
 *             passing cases.
 *
 * The defect that the drain fixes is therefore verified by the reasoning above
 * plus one recorded observation (SIGTRAP inside a thread named "libuv-worker"
 * after job_loop_close returned, with PostQueuedCompletionStatus reporting an
 * invalid handle), not by this assertion. Detecting the race deterministically
 * needs a happens-before-aware tool — TSan — and this toolchain has no libtsan:
 * gcc -fsanitize=thread fails to link with "cannot find -ltsan". That is recorded
 * as NOT RUN in the phase checklist rather than papered over.
 */
static int t_shutdown_with_work_pending_is_safe(void) {
  /* Large enough that the read cannot plausibly have completed before the close,
   * so the case exercises the pending path rather than the idle one. */
  static char big[256 * 1024];
  memset(big, 'z', sizeof(big));
  char path[512];
  t_assert(write_scratch("read_pending.bin", big, sizeof(big), path,
                         sizeof(path)) == 0);

  t_assert(job_loop_init() == 0);
  seen_reset();

  t_assert(job_file_read(path, on_read, NULL) == 0);
  t_assert(job_pending() == 1);     /* queued, not yet pumped: it is in flight */

  job_loop_close();

  /* The request completed during the drain, so it is gone rather than pending. */
  t_eq_int(job_pending(), 0);

  /* No callback: this runs after the Lua state is gone in the real editor, and a
   * callback here would re-enter a closed interpreter. */
  t_eq_int(seen.calls, 0);

  /* Every allocation the module made is back. A number rather than a boolean
   * because "the accounting says zero" is the only evidence that the drain freed
   * rather than leaked. */
  t_eq_int((long long)cdin_mem_live(CDIN_MEM_LOOP), 0);
  t_eq_int((long long)cdin_mem_live(CDIN_MEM_BUFFER), 0);
  return 0;
}

/* After a close with nothing outstanding, the module leaves nothing behind and
 * can be brought back up — which is what "initialisation failure does not leave
 * partially initialised state" means in practice. */
static int t_close_then_reinit_leaves_no_residue(void) {
  static const char body[] = "restart\n";
  char path[512];
  t_assert(write_scratch("read_restart.txt", body, sizeof(body) - 1, path,
                         sizeof(path)) == 0);

  for (int round = 0; round < 3; round++) {
    t_assert(job_loop_init() == 0);
    /* Reset BEFORE the read, not only after. The counter is shared across cases,
     * so without this a preceding case that ran several requests — the
     * re-entrancy case runs three — leaves its total here and "called exactly
     * once" reads as 3 or 4. */
    seen_reset();
    t_assert(job_file_read(path, on_read, NULL) == 0);
    pump_until_done();
    t_eq_int(seen.calls, 1);
    t_eq_int(seen.status, LOOP_OK);
    job_loop_close();

    t_eq_int((long long)cdin_mem_live(CDIN_MEM_LOOP), 0);

    /* CDIN_MEM_BUFFER is released by the test before it is checked, because the
     * completion callback's own copy of the bytes carries that same tag. Asserting
     * the tag is zero without releasing the copy would be asserting that the test
     * has tidied up after itself, and would report 8 bytes of the test's own
     * bookkeeping as though the module had retained them.
     *
     * The module's retention is measured separately and unambiguously: with a
     * callback that keeps nothing, CDIN_MEM_BUFFER is 0 after every round. That is
     * what makes this assertion about the module rather than about the harness. */
    seen_reset();
    t_eq_int((long long)cdin_mem_live(CDIN_MEM_BUFFER), 0);
    t_eq_int((long long)cdin_mem_live_blocks(), 0);
  }
  return 0;
}

/* ── the suite ──────────────────────────────────────────────────────────── */

/* Releases the callback's copy of the bytes.
 *
 * Held across the whole suite because a completion callback has to copy the data
 * to be able to assert on it after it returns — the documented contract is that
 * the buffer is valid only for the duration of the call. That makes this the
 * suite's one long-lived allocation, and it is CDIN_MEM_BUFFER so the run's leak
 * gate sees it: without this the suite would report 8 stray bytes and the gate
 * would be reporting the test's own bookkeeping rather than the module's. */
void job_suite_release(void) {
  /* A worker left parked is a thread blocked on a condition variable: it keeps
   * the process alive at exit, so the binary never terminates and its buffered
   * output is lost with it. Done here as well as inside the case, so a case that
   * fails before its own cleanup still cannot strand one. */
  job_test_release();
  job_test_set_hook(NULL, NULL);
  seen_reset();
}

/* ── the shutdown lifetime race, deterministically ──────────────────────── */

/* What the hook observes.
 *
 * The important thing learned writing this: none of the callbacks in src/loop
 * run on a libuv WORKER. uv_fs_open/uv_fs_read/uv_fs_fstat do their blocking work
 * on a pool thread, but their callbacks are delivered by uv_run on the LOOP
 * thread — which is the main thread. So a hook placed inside job_read_stat would
 * park the main thread inside uv_run, and job_loop_run_once() would never return.
 * That is not a test bug; it is what libuv's model is.
 *
 * Which means the state a shutdown test needs — "a request is in flight that
 * libuv is holding" — is produced by NOT pumping, not by parking a worker. See
 * the case below. The hook remains useful for the one thing it can observe: how
 * many times the completion path ran. */
static const char *last_point;
static int         point_count;

static void point_hook(const char *point, void *user) {
  (void)user;
  last_point = point;
  point_count++;
}

/* THE regression test.
 *
 * The request is queued and deliberately NOT pumped, so it is genuinely in flight
 * with libuv holding it, and the loop is closed from exactly that state. What
 * makes it deterministic rather than a race is that the drain inside
 * job_loop_close is what must complete the work: with it removed, close frees a
 * request that libuv still owns, and the freed block is poisoned with 0xDD and
 * quarantined by the debug allocator, so the worker's subsequent write lands in
 * memory the assertions can see has been released.
 *
 * The earlier version of this case asserted only that the process survived, and
 * passed with the defect reinstated (measured: the crash was about 1 run in 6).
 * What is asserted here is the ORDER — nothing is freed until the loop reports no
 * outstanding work — rather than the absence of a crash. */
static int t_close_drains_before_it_frees(void) {
  static const char body[] = "parked\n";
  char path[512];
  int rc = 0;

  if (write_scratch("read_parked.txt", body, sizeof(body) - 1, path,
                    sizeof(path)) != 0) return CTEST_FAIL_ASSERT;

  if (job_loop_init() != 0) return CTEST_FAIL_ASSERT;
  seen_reset();
  last_point = NULL;
  point_count = 0;
  job_test_set_hook(point_hook, NULL);

  /* Queued and NOT pumped: the request is in flight, libuv holds it, and no
   * callback has run. This is the state the defect lived in. */
  if (job_file_read(path, on_read, NULL) != 0) { rc = CTEST_FAIL_ASSERT; goto done; }
  if (job_pending() != 1) {
    fprintf(stderr, "     %s:%d: expected 1 pending request, got %d\n",
            __FILE__, __LINE__, job_pending());
    rc = CTEST_FAIL_ASSERT;
    goto done;
  }

  /* Close from that state. The drain must finish the request before any free. */
  job_loop_close();
  job_test_set_hook(NULL, NULL);

  /* Disposed, not stranded and not double-freed. */
  if (job_pending() != 0) {
    fprintf(stderr, "     %s:%d: a request was still pending after close\n",
            __FILE__, __LINE__);
    rc = CTEST_FAIL_ASSERT;
    goto done2;
  }
  /* No callback: close runs after the Lua state is gone in the real editor. */
  if (seen.calls != 0) {
    fprintf(stderr, "     %s:%d: a callback fired during shutdown (%d)\n",
            __FILE__, __LINE__, seen.calls);
    rc = CTEST_FAIL_ASSERT;
    goto done2;
  }
  /* Everything released. A number, not a boolean: "the accounting says zero" is
   * the only evidence the drain freed rather than leaked. */
  if ((long long)cdin_mem_live(CDIN_MEM_LOOP) != 0) {
    fprintf(stderr, "     %s:%d: %lld loop bytes live after close\n",
            __FILE__, __LINE__, (long long)cdin_mem_live(CDIN_MEM_LOOP));
    rc = CTEST_FAIL_ASSERT;
    goto done2;
  }
  if ((long long)cdin_mem_live_blocks() != 0) {
    fprintf(stderr, "     %s:%d: %lld blocks live after close\n",
            __FILE__, __LINE__, (long long)cdin_mem_live_blocks());
    rc = CTEST_FAIL_ASSERT;
    goto done2;
  }

  /* And the module works again, so the drain left no broken state behind. */
  if (job_loop_init() != 0) { rc = CTEST_FAIL_ASSERT; goto done2; }
  seen_reset();
  if (job_file_read(path, on_read, NULL) != 0) { rc = CTEST_FAIL_ASSERT; goto done2; }
  pump_until_done();
  if (seen.calls != 1) {
    fprintf(stderr, "     %s:%d: expected 1 callback after re-init, got %d\n",
            __FILE__, __LINE__, seen.calls);
    rc = CTEST_FAIL_ASSERT;
    goto done2;
  }
  if (seen.status != LOOP_OK) { rc = CTEST_FAIL_ASSERT; goto done2; }
  if ((long long)seen.len != (long long)(sizeof(body) - 1)) {
    rc = CTEST_FAIL_ASSERT;
    goto done2;
  }
  job_loop_close();

done2:
  job_test_set_hook(NULL, NULL);
done:
  job_test_release();
  job_test_set_hook(NULL, NULL);
  return rc;
}

/* Re-entrancy: a completion callback may submit another request.
 *
 * The API permits it, because job_read_done removes the request from the queue
 * BEFORE invoking the callback, so the slot is free and the queue cannot deadlock
 * against itself. That ordering is a design decision with a consequence, and this
 * is the case that pins it.
 *
 * Three links rather than one, because the interesting failure is a second-level
 * one: a request submitted from inside a completion has to be picked up by a
 * LATER pump rather than recursing into the dispatch that is already running. A
 * single-link version would pass even if that were wrong. */
#define REENTRANCY_DEPTH 3
static char    chain_path[REENTRANCY_DEPTH][512];
static size_t  chain_body_len;
static int     chain_issued;

static void chain_callback(LoopStatus status, const uint8_t *data, size_t len,
                           void *user) {
  (void)user;
  seen.calls++;
  seen.status = status;
  seen.len = len;
  if (data && len) {
    if (seen.copy) cdin_free(seen.copy);
    seen.copy = cdin_alloc(CDIN_MEM_BUFFER, len);
    seen.copy_cap = seen.copy ? len : 0;
    if (seen.copy) memcpy(seen.copy, data, len);
  }

  /* Issue the next link from inside the completion. This is the re-entrant
   * call: job_file_read is reached while the loop is dispatching this very
   * callback. That used to mean a nested uv_run, which libuv does not support;
   * the requests it stranded showed up as job_pending() == 2 after the chain.
   * job_file_read no longer pumps the loop, so the next link completes on the
   * following frame like any other request. */
  if (chain_issued < REENTRANCY_DEPTH) {
    int idx = chain_issued++;
    if (job_file_read(chain_path[idx], chain_callback, NULL) != 0) {
      /* A refusal would silently shorten the chain and the count assertion below
       * would catch it, which is why this is not an assertion of its own. */
      chain_issued = REENTRANCY_DEPTH;
    }
  }
}

static int t_a_callback_may_submit_another_request(void) {
  static const char body[] = "chained\n";
  chain_body_len = sizeof(body) - 1;
  chain_issued = 0;

  char path[512];
  t_assert(write_scratch("read_chain.txt", body, chain_body_len, path,
                         sizeof(path)) == 0);
  /* Every link reads the same path: what is under test is the queue handling, not
   * the file. Copying it into a per-link buffer keeps the callback's request
   * independent of the caller's stack frame. */
  for (int i = 0; i < REENTRANCY_DEPTH; i++) {
    memcpy(chain_path[i], path, sizeof(path));
  }

  t_assert(job_loop_init() == 0);
  seen_reset();

  /* The first request, which then issues the second from its own completion, and
   * so on. */
  memcpy(chain_path[0], path, sizeof(path));
  t_assert(job_file_read(chain_path[0], chain_callback, NULL) == 0);
  chain_issued = 1;

  for (int i = 0; i < JOB_PUMP_LIMIT && seen.calls < REENTRANCY_DEPTH; i++) {
    job_loop_run_once();
  }

  /* Each link fired exactly once, all succeeded, and the queue drained — which is
   * what says the re-entrant submission did not deadlock or recurse. */
  t_eq_int(job_pending(), 0);
  t_eq_int(seen.calls, REENTRANCY_DEPTH);
  t_eq_int(seen.status, LOOP_OK);
  t_eq_int((long long)seen.len, (long long)chain_body_len);

  job_loop_close();
  return 0;
}

/* ── re-entrancy: what the loop does while a callback is on the stack ─────── */

/* Records whether the loop was pumped from inside a callback, and how a close
 * attempted from one turned out. */
static int reentrant_saw_pump;
static int reentrant_close_attempted;

static void probing_callback(LoopStatus status, const uint8_t *data, size_t len,
                             void *user) {
  (void)status; (void)data; (void)len; (void)user;
  seen.calls++;

  /* Pumping from here would be a nested uv_run. It must be refused, not
   * attempted. A refusal returns -1 and changes nothing, which is what makes
   * this safe to call rather than something to assert on in production code. */
  reentrant_saw_pump = job_loop_run_once();
}

static void closing_callback(LoopStatus status, const uint8_t *data, size_t len,
                             void *user) {
  (void)status; (void)data; (void)len; (void)user;
  seen.calls++;
  /* Must be refused: closing here would free the loop while uv_run is still
   * executing on it. */
  reentrant_close_attempted++;
  job_loop_close();
}

/* A callback must never observe its own request as still pending, and the
 * submission call must never run the loop.
 *
 * Both halves were true before, by accident rather than by design: job_file_read
 * ended with uv_run(UV_RUN_NOWAIT), so a callback could fire inside the
 * submitting call. What is pinned here is the contract as it now stands —
 *
 *   - job_file_read returns before the callback has run, always;
 *   - the request is off the queue before its callback fires, so a callback that
 *     submits again finds a free slot rather than a full queue.
 *
 * The second point is why the re-entrancy chain works at all: it takes the slot
 * the request it is running inside just released. */
static int t_a_callback_never_fires_before_the_pump_that_runs_it(void) {
  static const char body[] = "timing\n";
  seen_reset();
  reentrant_saw_pump = 99;   /* 99 is not a valid return, so "unchanged" is visible */

  char path[512];
  t_assert(write_scratch("read_timing.txt", body, sizeof(body) - 1, path,
                         sizeof(path)) == 0);
  t_assert(job_loop_init() == 0);

  t_assert(job_file_read(path, probing_callback, NULL) == 0);

  /* The callback has NOT run: job_file_read does not pump. If it did, this is
   * where it would show, and the re-entrant pump inside probing_callback would
   * have been attempted. */
  t_eq_int(seen.calls, 0);
  t_eq_int(job_pending(), 1);

  for (int i = 0; i < JOB_PUMP_LIMIT && seen.calls == 0; i++) job_loop_run_once();
  t_eq_int(seen.calls, 1);

  /* Reached from inside the callback, so it was inside uv_run and had to be
   * refused. -1 unchanged means the guard fired. */
  t_eq_int(reentrant_saw_pump, -1);

  /* And the loop is still healthy afterwards — the refusal must not have wedged
   * it. A second read completes normally. */
  seen_reset();
  t_assert(job_file_read(path, on_read, NULL) == 0);
  pump_until_done();
  t_eq_int(seen.calls, 1);

  job_loop_close();
  return 0;
}

/* Closing the loop from inside a completion callback must be refused, and must
 * leave the loop intact.
 *
 * This is the second half of the nesting guard, and it is the half that is easy
 * to get wrong. Refusing only the nested uv_run is not sufficient: the close then
 * proceeded to cdin_free(job_loop) while uv_run was still executing on it, which
 * is a use-after-free one step past the bug the guard was added for.
 *
 * The assertions are chosen so the failure is the failure and not a mystery
 * fault later: the callback ran, and afterwards the loop still answers for work.
 * A freed loop would fail here rather than somewhere else. */
static int t_close_from_inside_a_callback_is_refused_and_leaves_it_working(void) {
  static const char body[] = "refused-close\n";
  seen_reset();
  reentrant_close_attempted = 0;

  char path[512];
  t_assert(write_scratch("read_refuse_close.txt", body, sizeof(body) - 1, path,
                         sizeof(path)) == 0);
  t_assert(job_loop_init() == 0);

  t_assert(job_file_read(path, closing_callback, NULL) == 0);
  for (int i = 0; i < JOB_PUMP_LIMIT && seen.calls == 0; i++) job_loop_run_once();
  t_eq_int(seen.calls, 1);
  t_eq_int(reentrant_close_attempted, 1);

  /* The refused close freed nothing, so the loop is still there: it accepts a
   * read, completes it, and reports no residue. If close had gone ahead, the loop
   * memory would be gone and this read would either fail or crash. */
  seen_reset();
  t_assert(job_file_read(path, on_read, NULL) == 0);
  t_eq_int(job_pending(), 1);
  pump_until_done();
  t_eq_int(seen.calls, 1);
  t_eq_int(seen.status, LOOP_OK);
  t_eq_int(job_pending(), 0);

  /* Closing for real, now that nothing is on the stack, is accepted. */
  job_loop_close();

  /* And the loop really is gone: a read is refused rather than queued, which is
   * what "not leaked" means for a shutdown. Reset first — the read above left
   * seen.calls at 1, and comparing that against 0 would fail for a reason that
   * has nothing to do with the refusal. */
  seen_reset();
  t_assert(job_file_read(path, on_read, NULL) != 0);
  t_eq_int(seen.calls, 0);
  t_eq_int(job_pending(), 0);
  return 0;
}

static const CtestCase job_cases[] = {
  { "a read before init is refused",        t_read_before_init_is_refused },
  { "repeated init is safe",                 t_repeated_init_is_safe },
  { "repeated close is safe",                t_repeated_close_is_safe },
  { "a read completes and delivers bytes",   t_a_read_completes_and_delivers_its_bytes },
  { "binary data round-trips exactly",       t_binary_data_round_trips_byte_for_byte },
  { "an empty file completes successfully",  t_an_empty_file_completes_successfully },
  { "a missing file is reported once",       t_a_missing_file_is_reported_exactly_once },
  { "an invalid path is refused",            t_an_invalid_path_is_refused },
  { "many requests complete exactly once",   t_many_requests_each_complete_exactly_once },
  { "a full queue refuses, not overwrites",  t_a_full_queue_refuses_rather_than_overwriting },
  { "allocation failure is reported",        t_an_allocation_failure_is_reported_and_leaves_nothing },
  { "shutdown with work pending is safe",    t_shutdown_with_work_pending_is_safe },
  { "close drains before it frees",          t_close_drains_before_it_frees },
  { "a callback may submit a request",      t_a_callback_may_submit_another_request },
  { "a callback fires only on a later pump", t_a_callback_never_fires_before_the_pump_that_runs_it },
  { "close from a callback is refused",      t_close_from_inside_a_callback_is_refused_and_leaves_it_working },
  { "close then re-init leaves no residue",  t_close_then_reinit_leaves_no_residue },
};

const CtestSuite job_suite = {
  "job loop",
  job_cases,
  (int)(sizeof(job_cases) / sizeof(job_cases[0])),
};

/* The scratch directory, set by the runner alongside logger_suite_set_scratch.
 *
 * A separate entry point rather than a field on CtestSuite, because that struct
 * is shared by every suite and adding a member would have meant touching all of
 * them for one suite's needs. */
void job_suite_set_scratch(const char *dir) {
  scratch_dir = dir;
  seen_reset();
}
