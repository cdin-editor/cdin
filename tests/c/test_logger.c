/* Logger tests: the file log's size cap and its rotation.
 *
 * The defect this guards is the one Phase 0 fixes: rotation happened only at
 * startup, so a long session grew the live log past its cap without bound —
 * exactly the leak-with-a-suffix the cap exists to prevent. The test drives the
 * logger past the cap and asserts the file was rotated and kept its size.
 *
 * The logger's global state is process-wide and these cases mutate it, so each
 * one points it at its own file under the scratch directory and resets the
 * level and quiet flag afterwards. Nothing here calls the test runner's
 * stdout path: log_quiet silences the stderr callback so a case that writes
 * thousands of lines does not print thousands of lines.
 */

#include <stdio.h>
#include <string.h>

#include "../../src/core/logger.h"
#include "ctest.h"

/* Overridable so the build can point the cases at a writable scratch directory
 * without the test needing to know where that is. Defaults to the in-tree
 * build directory, which mk/test.mk creates. */
/* The scratch directory, from argv[1]. Passed in rather than compiled in
 * because a path baked into a -D has to survive two levels of quoting between
 * the makefile and the compiler, and a Windows path ("D:/...") does not: the
 * colon starts a new token. An argument has none of those problems. */
static const char *scratch_dir = "build/test-scratch";

/* Mirrors LOG_MAX_BYTES in src/core/logger.c. Kept as a literal here on
 * purpose: a test that read the constant out of the header could not catch the
 * cap being removed, which is the failure this is here for. */
#define TEST_CAP (4L * 1024L * 1024L)

/* The size of a file on disk, or -1 if it is not there.
 *
 * By opening the file rather than calling stat: the MinGW CRT's stat reports 0
 * for a file the same process has open in append mode and has been writing to
 * — the buffered size is not visible to it yet — which reads as "rotation did
 * nothing" when rotation did exactly what it should. Re-opening with its own
 * handle and seeking to the end has no such problem, and it is the same thing
 * a person checking the log by hand would do. */
static long file_size_of(const char *path) {
  FILE *fp = fopen(path, "rb");
  if (!fp) return -1;
  fseek(fp, 0, SEEK_END);
  long n = ftell(fp);
  fclose(fp);
  return n;
}

/* Opens a fresh file log at `name`, returning the FILE* so the case can check
 * the bytes on disk. Sets quiet so the stderr callback stays quiet. */
/* Points the log at a fresh file and returns that file's path.
 *
 * The logger owns the stream after log_add_fp, so the caller must not fclose
 * it: the next case closes it when it installs its own. Returns NULL if the
 * log could not be pointed at the file, which every case treats as a failure
 * rather than skipping.
 */
static const char *open_test_log(const char *name, char *out, size_t out_size) {
  snprintf(out, out_size, "%s/%s", scratch_dir, name);
  remove(out);
  {
    char prev[540];
    snprintf(prev, sizeof(prev), "%s.1", out);
    remove(prev);
  }

  FILE *fp = fopen(out, "a");
  if (!fp) {
    fprintf(stderr, "     cannot create %s\n", out);
    return NULL;
  }

  log_set_quiet(true);
  log_set_path(out);
  if (log_add_fp(fp, LOG_DEBUG) != 0) {
    fprintf(stderr, "     log_add_fp failed for %s\n", out);
    return NULL;
  }
  return out;
}


/* The cap holds: past 4 MiB the log rotates, the live file stays under the
 * cap, and the previous run is kept as <name>.1 rather than deleted. */
static int t_rotates_during_session(void) {
  char path[512];
  t_assert(open_test_log("rotate.log", path, sizeof(path)) != NULL);

  /* ~94 bytes per line at this format, so ~90k lines crosses 4 MiB with
   * margin. */
  log_set_level(LOG_DEBUG);
  for (int i = 0; i < 90000; i++) {
    log_log(LOG_INFO, __FILE__, __LINE__, "filler line %d aaaaaaaaaaaaaaaaaaaa", i);
  }

  char prev[540];
  snprintf(prev, sizeof(prev), "%s.1", path);

  long live = file_size_of(path);
  long old  = file_size_of(prev);

  t_assert("the live log exists: " && live > 0);
  /* Under the cap plus the one line that tripped it: the callback checks
   * before writing, so the live file can overshoot by at most one record. */
  t_assert("the live log stayed near the cap: " && live <= TEST_CAP + 65536);
  t_assert("rotation produced a .1 file: " && old > 0);
  /* The kept file is itself at the cap: it is the full previous run. */
  t_assert("the kept run is at the cap: " && old <= TEST_CAP + 65536);

  log_set_level(LOG_INFO);
  log_set_quiet(false);
  return 0;
}


/* A log that stays under the cap is never rotated, and no .1 appears. */
static int t_no_rotation_under_cap(void) {
  char path[512];
  t_assert(open_test_log("small.log", path, sizeof(path)) != NULL);

  for (int i = 0; i < 100; i++) {
    log_log(LOG_INFO, __FILE__, __LINE__, "small line %d", i);
  }

  char prev[540];
  snprintf(prev, sizeof(prev), "%s.1", path);

  long live = file_size_of(path);
  t_assert("the small log grew: " && live > 0);
  t_assert("a small log grew a .1 file: " && file_size_of(prev) == -1);

  log_set_level(LOG_INFO);
  log_set_quiet(false);
  return 0;
}


/* The reported size is the real size, so core:memory can show it. */
static int t_file_size_reported(void) {
  char path[512];
  t_assert(open_test_log("size.log", path, sizeof(path)) != NULL);

  for (int i = 0; i < 50; i++) {
    log_log(LOG_INFO, __FILE__, __LINE__, "reported %d", i);
  }

  long on_disk   = file_size_of(path);
  long reported = log_get_file_size();

  t_assert("the logger reports a size: " && reported > 0);
  /* The counter tracks what the callback wrote, and ftell works on a regular
   * file, so this is an exact equality rather than a range. */
  t_assert("the reported size matches the file: " && reported == on_disk);

  log_set_level(LOG_INFO);
  log_set_quiet(false);
  return 0;
}


/* A freshly opened file log reports 0, not -1: the handle exists and the file
 * is empty, which is a real measurement. -1 means there is no file log at all,
 * which is a different fact and the one core:memory prints as "(off)". */
static int t_fresh_file_log_reports_zero(void) {
  char path[512];
  t_assert(open_test_log("off.log", path, sizeof(path)) != NULL);
  t_eq_int(log_get_file_size(), 0);
  return 0;
}


static const CtestCase logger_cases[] = {
  { "rotates during a session, past the 4 MiB cap", t_rotates_during_session },
  { "does not rotate a log that stays under the cap", t_no_rotation_under_cap  },
  { "reports the live file size",                    t_file_size_reported     },
  { "a freshly opened file log reports 0, not -1",   t_fresh_file_log_reports_zero },
};

const CtestSuite logger_suite = {
  "logger",
  logger_cases,
  (int)(sizeof(logger_cases) / sizeof(logger_cases[0])),
};


/* Installs the scratch directory argv[1] carries. Called by the runner before
 * any case runs; a run with no argument keeps the default above. */
void logger_suite_set_scratch(const char *dir) {
  if (dir && *dir) scratch_dir = dir;
}
