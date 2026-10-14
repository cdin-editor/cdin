/* The C unit-test runner.
 *
 * The runtime has no C tests at all today, which is why Phase 0 spends part of
 * itself on the harness: every later phase lands with tests, and they all have
 * to run somewhere. This is that somewhere.
 *
 * Deliberately tiny. No discovery, no fixtures, no registration framework — a
 * test is a function returning 0 or a negative errno-style code, and a suite
 * is an array of them. `make test` builds this, runs it, and reports.
 *
 * Owned by nobody; every static is written before main and read-only after.
 */

#include <stdio.h>
#include <string.h>

#include "../../src/base/alloc.h"
#include "ctest.h"

static int run_suite(const CtestSuite *suite) {
  int passed = 0, failed = 0;

  printf("-- %s --\n", suite->name);
  for (int i = 0; i < suite->count; i++) {
    int rc = suite->cases[i].fn();
    if (rc == 0) {
      printf("   ok    %s\n", suite->cases[i].name);
      passed++;
    } else {
      printf("   FAIL  %s (%s)\n", suite->cases[i].name, ctest_strerror(rc));
      failed++;
    }
  }
  printf("   %d passed, %d failed\n", passed, failed);
  return failed;
}


const char *ctest_strerror(int rc) {
  switch (rc) {
    case CTEST_FAIL_ASSERT:  return "assertion failed";
    case CTEST_FAIL_RANGE:   return "value out of range";
    case CTEST_FAIL_ALLOC:   return "allocation failed";
    default:                 return "failed";
  }
}


int main(int argc, char **argv) {
  const CtestSuite *suites[] = {
    &logger_suite, &rencache_suite, &alloc_suite, &arena_suite, &error_suite,
    &job_suite, &path_suite
  };
  int failed = 0, total = 0;

  /* Bytes live before any suite runs, so the leak gate at the end compares
   * against this rather than against zero. Suites are not required to leave
   * nothing behind — a module with a legitimate singleton is not a leak — but
   * the run must not grow the heap, and that is a single number to check. */
  size_t live_at_entry = cdin_mem_total_live();

  /* The scratch directory, passed rather than compiled in: a path in a -D has
   * to survive the makefile and the shell, and a Windows path ("D:/…") does
   * not. See logger_suite_set_scratch. */
  if (argc > 1) {
    logger_suite_set_scratch(argv[1]);
    job_suite_set_scratch(argv[1]);
  }

  for (size_t i = 0; i < sizeof(suites) / sizeof(suites[0]); i++) {
    failed += run_suite(suites[i]);
    total  += suites[i]->count;
  }

  /* Suites that hold an allocation across their cases release it here, so the
   * gate below measures the MODULES rather than the tests' own bookkeeping. The
   * job suite copies each completion's bytes so it can assert on them after the
   * callback returns, which is one live allocation for the whole run. */
  job_suite_release();

  /* The leak gate. This build is compiled with -DDEBUG so the allocator's
   * live-block registry is present, which is what makes this number mean
   * something; without it the report would return 0 and the check would pass
   * for the wrong reason. */
  printf("\n-- leaks --\n");
  size_t leaked_blocks = cdin_mem_leak_report();
  size_t leaked_bytes  = cdin_mem_total_live() - live_at_entry;
  if (leaked_blocks > 0 || leaked_bytes > 0) {
    printf("   FAIL  %zu block(s), %zu byte(s) still live after the suites\n",
           leaked_blocks, leaked_bytes);
    failed++;
    total++;
  } else {
    printf("   ok    no blocks leaked (%zu bytes live, same as at entry)\n",
           cdin_mem_total_live());
  }

  /* Printed unconditionally: the per-subsystem peak is the number Phase 1's
   * report is built on, and a reader should not have to run a second
   * command to see what this run cost. */
  printf("\n-- memory --\n");
  for (int i = 0; i < (int)CDIN_MEM_COUNT; i++) {
    CdinMemTag tag = (CdinMemTag)i;
    printf("   %-10s live %10zu  peak %10zu  blocks %6zu\n",
           cdin_mem_tag_name(tag), cdin_mem_live(tag), cdin_mem_peak(tag),
           cdin_mem_alloc_count(tag));
  }
  printf("   %-10s live %10zu  peak %10zu\n", "TOTAL",
         cdin_mem_total_live(), cdin_mem_total_peak());

  printf("\n");
  if (failed > 0) {
    printf("C TESTS FAILED (%d of %d)\n", failed, total);
    return 1;
  }
  printf("C TESTS OK (%d cases)\n", total);
  return 0;
}
