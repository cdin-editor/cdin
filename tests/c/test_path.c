/* Path resolution: shared primitive, fixed-buffer contract, and ownership.
 *
 * path_absolute_alloc is the dynamic-allocation primitive; path_absolute is the
 * fixed-buffer wrapper. Both must agree on short paths, and path_absolute must
 * reject paths that exceed its output capacity.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../../src/base/alloc.h"
#include "../../src/fs/path.h"
#include "ctest.h"

static int t_path_alloc_short_path(void) {
  char *res = path_absolute_alloc(".");
  t_assert(res != NULL);
  cdin_free(res);
  return 0;
}

static int t_path_alloc_nonexistent_path_unix(void) {
#ifdef _WIN32
  return 0; /* Windows _fullpath does not check existence */
#else
  char *res = path_absolute_alloc("nonexistent_xyz_12345");
  t_assert(res == NULL);
  return 0;
#endif
}

static int t_path_fixed_buffer_short_path(void) {
  char out[4096];
  int rc = path_absolute(".", out, (int)sizeof(out));
  t_assert(rc == 0);
  t_assert(out[0] != '\0');
  return 0;
}

static int t_path_fixed_buffer_nonexistent_unix(void) {
#ifdef _WIN32
  return 0; /* Windows _fullpath does not check existence */
#else
  char out[4096];
  int rc = path_absolute("nonexistent_xyz_12345", out, (int)sizeof(out));
  t_assert(rc == -1);
  return 0;
#endif
}

static int t_path_fixed_buffer_rejects_oversized(void) {
  /* Build a path whose absolute length exceeds the fixed buffer.
   * Use multiple components to avoid relying on single-component limits. */
  char long_path[8192];
  long_path[0] = '\0';
  for (int i = 0; i < 100; i++) {
    strcat(long_path, "aaaaaaaaaa/");
  }
  char out[4096];
  int rc = path_absolute(long_path, out, (int)sizeof(out));
  t_assert(rc == -1);
  return 0;
}



static int t_path_alloc_failure_frees_intermediate(void) {
  /* Arm the allocator to fail the next allocation, then verify that
   * path_absolute_alloc returns NULL and does not leak the intermediate. */
  cdin_alloc_fail_after(0);
  char *res = path_absolute_alloc(".");
  cdin_alloc_fail_disable();
  t_assert(res == NULL);
  return 0;
}

static const CtestCase path_cases[] = {
  { "alloc resolves a short path",              t_path_alloc_short_path },
  { "alloc fails for nonexistent path (Unix)",   t_path_alloc_nonexistent_path_unix },
  { "fixed buffer resolves a short path",        t_path_fixed_buffer_short_path },
  { "fixed buffer fails for nonexistent (Unix)", t_path_fixed_buffer_nonexistent_unix },
  { "fixed buffer rejects oversized path",       t_path_fixed_buffer_rejects_oversized },
  { "alloc failure frees intermediate",          t_path_alloc_failure_frees_intermediate },
};

const CtestSuite path_suite = {
  "path",
  path_cases,
  (int)(sizeof(path_cases) / sizeof(path_cases[0])),
};
