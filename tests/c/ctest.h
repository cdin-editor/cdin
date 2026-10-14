/* A minimal C test harness: the case type, the assertion macros, and the
 * declarations of the per-module case arrays that test_main.c collects.
 *
 * A test returns 0 or CTEST_FAIL_*. Nothing throws, nothing allocates a result
 * object, and a failing assertion prints the file and line it was written on —
 * which is the only thing a runner needs to be useful.
 *
 * Every case array is `const CtestCase[]`, so the linker catches a missing or
 * mistyped entry at build time rather than at run time.
 */

#ifndef CDIN_TESTS_CTEST_H
#define CDIN_TESTS_CTEST_H

#include <stddef.h>

enum {
  CTEST_FAIL_ASSERT = 1,
  CTEST_FAIL_RANGE  = 2,
  CTEST_FAIL_ALLOC  = 3,
};

typedef struct {
  const char *name;
  int (*fn)(void);
} CtestCase;

/* A suite is a pointer and a count rather than a bare array, because an
 * `extern const CtestCase x[]` is an incomplete type and the runner cannot
 * take its sizeof. The count is written once, next to the cases, so adding a
 * test cannot be forgotten by the runner. */
typedef struct {
  const char     *name;
  const CtestCase *cases;
  int             count;
} CtestSuite;

/* Per-module suites, defined in tests/c/test_<module>.c. */
extern const CtestSuite logger_suite;
extern const CtestSuite rencache_suite;
extern const CtestSuite alloc_suite;
extern const CtestSuite arena_suite;
extern const CtestSuite error_suite;
extern const CtestSuite job_suite;
extern const CtestSuite path_suite;

/* Suites that need to know where to write scratch files. Each has its own entry
 * point rather than a field on CtestSuite, because that struct is shared and a
 * member added for one suite would have to be set by all of them. */
void logger_suite_set_scratch(const char *dir);
void job_suite_set_scratch(const char *dir);

/* Releases whatever a suite is still holding, so the run's leak gate measures
 * the modules and not the tests' own bookkeeping. */
void job_suite_release(void);

const char *ctest_strerror(int rc);

/* Writes the failure to stderr with file/line, then returns the code. The
 * caller returns it, so one line of test code is one line of output. */
#define t_assert(cond) \
  do { \
    if (!(cond)) { \
      fprintf(stderr, "     %s:%d: assertion failed: %s\n", __FILE__, __LINE__, #cond); \
      return CTEST_FAIL_ASSERT; \
    } \
  } while (0)

#define t_eq_int(got, want) \
  do { \
    long long g_ = (long long)(got), w_ = (long long)(want); \
    if (g_ != w_) { \
      fprintf(stderr, "     %s:%d: got %lld, want %lld  (%s)\n", \
              __FILE__, __LINE__, g_, w_, #got); \
      return CTEST_FAIL_ASSERT; \
    } \
  } while (0)

#define t_eq_str(got, want) \
  do { \
    const char *g_ = (got), *w_ = (want); \
    if (!g_ || !w_ || strcmp(g_, w_) != 0) { \
      fprintf(stderr, "     %s:%d: got \"%s\", want \"%s\"\n", \
              __FILE__, __LINE__, g_ ? g_ : "(null)", w_ ? w_ : "(null)"); \
      return CTEST_FAIL_ASSERT; \
    } \
  } while (0)

#define t_eq_ptr(got, want) \
  do { \
    const void *g_ = (const void *)(got); \
    const void *w_ = (const void *)(want); \
    if (g_ != w_) { \
      fprintf(stderr, "     %s:%d: got %p, want %p  (%s)\n", \
              __FILE__, __LINE__, g_, w_, #got); \
      return CTEST_FAIL_ASSERT; \
    } \
  } while (0)

#endif /* CDIN_TESTS_CTEST_H */
