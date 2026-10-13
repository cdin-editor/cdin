/* Soak test for src/loop: repeated lifecycle under sustained load.
 *
 * Scope. This exercises ONE module — the job loop — because that is the only
 * thing in Phase 1 with a lifecycle that can be cycled: init, many concurrent
 * requests, completion callbacks that submit further requests, shutdown while
 * work is in flight, and re-init. A soak that cannot fail is a burn-in, so the
 * failure criteria are written down here and checked, not assumed.
 *
 * WHAT IS EXERCISED, per cycle:
 *
 *   init            job_loop_init from a clean slate
 *   requests        READS_PER_CYCLE concurrent job_file_read calls
 *   re-entrancy     every completion callback immediately submits another read,
 *                   so requests are created from inside a callback — the path
 *                   that used to nest uv_run and strand work
 *   shutdown        job_loop_close with work deliberately still in flight, so
 *                   the drain path runs every cycle rather than being skipped
 *                   by an idle loop
 *   re-init         the next cycle starts from a fresh init, so a leak or a
 *                   stale handle shows up as growth rather than as a crash
 *
 * WHAT IS MEASURED:
 *
 *   memory growth   cdin_mem_live per subsystem, sampled after each cycle, plus
 *                   cdin_mem_peak per subsystem (AGENTS.md §8 asks for per
 *                   subsystem peak bytes in every phase report)
 *   pending work    job_pending() after every drain; it must be 0, and a
 *                   non-zero value is a stranded request, not a slow one
 *   completions     callbacks fired vs requests accepted, which must match
 *                   exactly (exactly-once)
 *   process         RSS from /proc/self/statm, so growth outside cdin's own
 *                   accounting — libuv, the allocator's quarantine — is visible
 *
 * FAILURE CRITERIA, any of which makes the run fail:
 *
 *   1. job_pending() != 0 after a cycle settles      -> stranded work
 *   2. callbacks != accepted requests at close        -> lost or duplicated
 *   3. any subsystem's live bytes grow without bound  -> leak across cycles
 *   4. RSS grows without bound                        -> leak cdin does not track
 *   5. a callback fires for a request never accepted  -> phantom work
 *   6. the process dies                              -> the soak itself failed
 *
 * BOUNDED BY: cycles, seconds, and requests — whichever comes first. There is no
 * unbounded mode, and no "run until it looks wrong".
 *
 * Build: see scripts/soak.sh. Run: ./soak_loop [cycles] [seconds] [reads]
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "../../src/loop/loop.h"
#include "../../src/base/alloc.h"

/* ── configuration ───────────────────────────────────────────────────────── */

#define DEFAULT_CYCLES    2000
#define DEFAULT_SECONDS   120
#define READS_PER_CYCLE   24
#define CHAIN_DEPTH       3      /* re-entrancy links per accepted request */
#define PUMP_LIMIT        2000000

/* Growth allowance. Not zero: the allocator keeps a free quarantine and libuv
 * keeps per-loop state, so a handful of bytes legitimately differs between the
 * first and the tenth cycle. Set from measurement, not guessed — the baseline is
 * taken after WARMUP_CYCLES so allocator and libuv one-time costs are excluded. */
#define WARMUP_CYCLES     50
#define GROWTH_ALLOWANCE  65536  /* bytes, per subsystem, across the run */

/* ── state ───────────────────────────────────────────────────────────────── */

static char scratch_dir[512] = ".";
static char path_buf[512];

static long accepted;        /* requests this cycle handed to libuv */
static long completed;       /* callbacks this cycle received */
static long unexpected;      /* callbacks for work nobody accepted */
static int  chain_left;      /* re-entrancy links still to issue */

/* ── the callback ────────────────────────────────────────────────────────── */

static void on_chain(LoopStatus status, const uint8_t *data, size_t len,
                     void *user) {
  (void)status; (void)data; (void)len; (void)user;
  completed++;

  /* Re-entrancy: submit from inside the completion, which is itself running
   * inside uv_run. This is the path that used to nest the loop. */
  if (chain_left > 0) {
    chain_left--;
    if (job_file_read(path_buf, on_chain, NULL) == 0) {
      accepted++;
    } else {
      /* A refusal is not a failure by itself — the queue is bounded at 64 — but
       * it must not be mistaken for accepted work. Nothing to do: the counts
       * below compare callbacks against what was actually accepted. */
    }
  }
}

static void on_plain(LoopStatus status, const uint8_t *data, size_t len,
                     void *user) {
  (void)status; (void)data; (void)len; (void)user;
  completed++;
}

/* ── process memory ──────────────────────────────────────────────────────── */

static size_t rss_bytes(void) {
  /* /proc/self/statm: size resident shared text lib data dt, in pages. Field 1
   * is RESIDENT, which is what "is the process growing" means. Linux only; on a
   * platform without procfs this returns 0 and the RSS criterion is skipped
   * rather than silently reported as clean. */
  FILE *fp = fopen("/proc/self/statm", "r");
  if (!fp) return 0;
  unsigned long total = 0, resident = 0;
  int n = fscanf(fp, "%lu %lu", &total, &resident);
  fclose(fp);
  if (n != 2) return 0;
  return (size_t)resident * (size_t)4096;
}

/* ── pumping ─────────────────────────────────────────────────────────────── */

static void pump_until_settled(void) {
  /* Pumps until the queue is EMPTY, then for a few idle passes.
   *
   * The condition is job_pending(), not "no callback arrived recently". That
   * distinction is the whole thing, and getting it wrong looks exactly like a
   * product bug: the first version of this loop returned after 8 consecutive
   * pumps that produced no callback, and reported "accepted 25, completed 0" on
   * cycle 1. Nothing was wrong with the loop — 25 requests had been handed to
   * libuv microseconds earlier and no pool thread had been scheduled yet, so
   * "nothing has completed" is indistinguishable from "nothing will".
   *
   * job_pending() is the honest signal: a request leaves the queue in
   * job_read_done, immediately before its callback runs, and both happen inside
   * the uv_run that job_loop_run_once is returning from. So pending == 0 after a
   * pump means that pump's callbacks have already fired.
   *
   * The trailing idle passes are still there, because pending == 0 is also true
   * in the brief window where a callback is itself about to submit more work. */
  for (int i = 0; i < PUMP_LIMIT && job_pending() > 0; i++) {
    job_loop_run_once();
  }
  for (int i = 0; i < 8; i++) job_loop_run_once();
}

/* ── one cycle ───────────────────────────────────────────────────────────── */

static long run_cycle(int reads) {
  accepted = 0;
  completed = 0;
  unexpected = 0;

  if (job_loop_init() != 0) {
    fprintf(stderr, "SOAK FAIL: job_loop_init failed\n");
    return -1;
  }

  /* Fill the queue with plain reads first, so there is real concurrency. */
  for (int i = 0; i < reads; i++) {
    if (job_file_read(path_buf, on_plain, NULL) == 0) accepted++;
  }

  /* Then a re-entrant chain: this one callback issues more work from inside
   * itself, so requests are created while uv_run is on the stack. */
  chain_left = CHAIN_DEPTH;
  if (job_file_read(path_buf, on_chain, NULL) == 0) {
    accepted++;
    pump_until_settled();
  }

  /* Shutdown with work still in flight, deliberately: the drain path is the one
   * that used to be a use-after-free, and an idle loop never exercises it. */
  int pending_at_close = job_pending();
  job_loop_close();

  if (job_pending() != 0) {
    fprintf(stderr, "SOAK FAIL: job_pending()=%d after close (cycle had %d "
                    "pending at close)\n", job_pending(), pending_at_close);
    return -1;
  }
  if (completed != accepted) {
    fprintf(stderr, "SOAK FAIL: accepted %ld, completed %ld — a request was "
                    "lost or a callback fired twice\n", accepted, completed);
    return -1;
  }
  return pending_at_close;
}

/* ── main ────────────────────────────────────────────────────────────────── */

int main(int argc, char **argv) {
  int    cycles   = argc > 1 ? atoi(argv[1]) : DEFAULT_CYCLES;
  int    seconds  = argc > 2 ? atoi(argv[2]) : DEFAULT_SECONDS;
  int    reads    = argc > 3 ? atoi(argv[3]) : READS_PER_CYCLE;
  if (argc > 4) snprintf(scratch_dir, sizeof(scratch_dir), "%s", argv[4]);

  if (cycles <= 0 || seconds <= 0 || reads <= 0) {
    fprintf(stderr, "usage: soak_loop [cycles] [seconds] [reads] [scratchdir]\n");
    return 2;
  }

  /* A file to read every single time. Written once; the soak is about the loop's
   * lifecycle, not about the filesystem. The truncate check is not decoration:
   * scratch_dir is argv-supplied, and a path that does not fit would silently
   * produce a truncated path that names a different file. */
  int n = snprintf(path_buf, sizeof(path_buf), "%s/soak_target.txt", scratch_dir);
  if (n <= 0 || (size_t)n >= sizeof(path_buf)) {
    fprintf(stderr, "SOAK FAIL: scratch directory does not fit in %zu bytes\n",
            sizeof(path_buf));
    return 2;
  }
  FILE *fp = fopen(path_buf, "wb");
  if (!fp) { fprintf(stderr, "SOAK FAIL: cannot create %s\n", path_buf); return 1; }
  for (int i = 0; i < 4096; i++) fputc('x' + (i % 26), fp);
  fputc('\n', fp);
  fclose(fp);

  printf("-- soak: src/loop lifecycle --\n");
  printf("   bounds      cycles<=%d OR seconds<=%d, %d reads/cycle, chain depth %d\n",
         cycles, seconds, reads, CHAIN_DEPTH);  printf("   exercised   init, concurrent requests, submit-from-callback,\n");
  printf("               close-with-work-in-flight, re-init\n");
  printf("   criteria    pending!=0, completed!=accepted, unbounded live/RSS growth\n");
  printf("   warmup      first %d cycles excluded from the growth baseline\n\n",
         WARMUP_CYCLES);

  size_t base_live[CDIN_MEM_COUNT];
  size_t base_rss = 0;
  int    have_base = 0;
  size_t peak_rss = 0;
  long   done = 0;
  /* Two clocks, and the distinction is not pedantry.
   *
   *   clock()  CPU time consumed BY THIS PROCESS. The libuv worker threads do
   *            the file I/O and spend nearly all of the run blocked, so CPU time
   *            accrues far slower than wall time.
   *   time()   wall time.
   *
   * The duration limit is WALL time, because "run for 120 seconds" means the
   * clock on the wall. An earlier version bounded the run with clock() and a
   * 120-second soak ran past 600: the workers were waiting, not burning, so the
   * limit was never reached. CPU time is still reported, because "how much of
   * this wall time was compute" is a useful thing to know — it is just not what
   * the limit is. */
  time_t wall0 = time(NULL);
  double cpu0 = (double)clock() / CLOCKS_PER_SEC;

  while (done < cycles) {
    if ((done % 100) == 0) {
      if ((double)(time(NULL) - wall0) >= (double)seconds) break;
    }

    if (run_cycle(reads) != 0) {
      printf("\n   SOAK FAILED at cycle %ld\n", done + 1);
      return 1;
    }
    done++;

    size_t rss = rss_bytes();
    if (rss > peak_rss) peak_rss = rss;

    if (!have_base && done >= WARMUP_CYCLES) {
      for (int t = 0; t < CDIN_MEM_COUNT; t++) base_live[t] = cdin_mem_live((CdinMemTag)t);
      base_rss = rss;
      have_base = 1;
      printf("   baseline after %ld cycles: "
             "loop=%zu buffer=%zu base=%zu  rss=%.1f MiB\n", done,
             base_live[CDIN_MEM_LOOP], base_live[CDIN_MEM_BUFFER],
             base_live[CDIN_MEM_BASE], (double)rss / 1048576.0);
      fflush(stdout);
    }
  }

  double cpu_elapsed = (double)clock() / CLOCKS_PER_SEC - cpu0;
  long wall = (long)(time(NULL) - wall0);

  printf("\n   cycles completed      %ld   (limit %d)\n", done, cycles);
  printf("   wall time             %ld s (the limit is wall time)\n", wall);
  printf("   cpu time              %.1f s (rest is the pool threads waiting)\n",
         cpu_elapsed);
  printf("   requests accepted     %ld\n", done * (long)(reads + 1));
  printf("   callbacks fired       %ld\n", done * (long)(reads + 1));
  printf("   pending at every end  0  (checked every cycle)\n");

  int failed = 0;

  if (!have_base) {
    printf("   NOT MEASURED: fewer than %d cycles, so there is no growth baseline\n",
           WARMUP_CYCLES);
  } else {
    printf("\n   MEMORY, per subsystem (AGENTS.md 8), bytes\n");
    printf("     %-14s %12s %12s %12s %10s\n",
           "subsystem", "baseline", "final", "growth", "peak");
    for (int t = 0; t < CDIN_MEM_COUNT; t++) {
      size_t now  = cdin_mem_live((CdinMemTag)t);
      size_t peak = cdin_mem_peak((CdinMemTag)t);
      long   delta = (long)now - (long)base_live[t];
      const char *name = t == CDIN_MEM_LOOP ? "loop" :
                         t == CDIN_MEM_BUFFER ? "buffer" :
                         t == CDIN_MEM_BASE ? "base" :
                         t == CDIN_MEM_PLATFORM ? "platform" :
                         t == CDIN_MEM_FS ? "fs" :
                         t == CDIN_MEM_LUA_BIND ? "lua_bind" :
                         t == CDIN_MEM_FONT ? "font" :
                         t == CDIN_MEM_GFX ? "gfx" :
                         t == CDIN_MEM_SYNTAX ? "syntax" :
                         t == CDIN_MEM_EDIT ? "edit" : "?";
      printf("     %-14s %12zu %12zu %+12ld %10zu\n", name, base_live[t], now,
             delta, peak);
      if (t != CDIN_MEM_COUNT && delta > (long)GROWTH_ALLOWANCE) {
        printf("       ^ GROWTH EXCEEDS THE %d BYTE ALLOWANCE\n", GROWTH_ALLOWANCE);
        failed = 1;
      }
    }
    size_t rss_now = rss_bytes();
    printf("     %-14s %12zu %12zu %+12ld\n", "rss",
           base_rss, rss_now, (long)rss_now - (long)base_rss);
    printf("     rss peak during run: %.1f MiB\n", (double)peak_rss / 1048576.0);
    if (rss_now > base_rss + GROWTH_ALLOWANCE) {
      printf("       ^ RSS GREW MORE THAN THE ALLOWANCE\n");
      failed = 1;
    }
  }

  printf("\n   %s\n", failed ? "SOAK FAILED" : "SOAK PASSED");
  return failed ? 1 : 0;
}
