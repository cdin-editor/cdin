/* The Lua-linked test runner.
 *
 * Separate from test_main.c because that one links no Lua on purpose. This one
 * exists for the code that cannot be tested without a lua_State: the handle
 * convention and the error convention, where the metamethods and the argument
 * checking are the behaviour under test.
 *
 * It reports the handle count at the end. A handle leaked by any case shows up as
 * a number that did not return to zero, which is a far better failure message than
 * a mysterious assertion in whichever later case happened to need a free slot.
 */

#include <stdio.h>

#include "../../src/base/alloc.h"
#include "../../src/lua/handle.h"
#include "ctest.h"
#include "lua_harness.h"

extern const CtestSuite handle_suite;
extern const CtestSuite font_suite;
void stub_handle_lua_init(void *L);
void ren_stub_free_all(void);

const char *ctest_strerror(int rc) {
  switch (rc) {
    case CTEST_FAIL_ASSERT: return "assertion failed";
    case CTEST_FAIL_RANGE:  return "value out of range";
    case CTEST_FAIL_ALLOC:  return "allocation failed";
    default:                return "failed";
  }
}

/* One case body, run against whichever suite is passed in. */
static int run_suite(const CtestSuite *suite) {
  int failed = 0;
  printf("-- %s --\n", suite->name);
  for (int i = 0; i < suite->count; i++) {
    int before = lh_failed();
    int rc = suite->cases[i].fn();
    if (rc == 0 && lh_failed() == before) {
      printf("   ok    %s\n", suite->cases[i].name);
    } else {
      printf("   FAIL  %s (%s)\n", suite->cases[i].name, ctest_strerror(rc));
      if (lh_failed() > before) printf("          %s\n", lh_error());
      failed++;
    }
  }
  printf("   %d passed, %d failed\n", suite->count - failed, failed);
  return failed;
}

int main(void) {
  /* Unbuffered stdout. A test runner that segfaults loses everything it had
   * printed if stdout is block-buffered, so the one run whose output explains the
   * crash is the one that comes back empty. This cost one confusing "exit code
   * -1073741819, no output at all" to discover. */
  setvbuf(stdout, NULL, _IONBF, 0);

  if (!lh_init()) {
    fprintf(stderr, "could not create a Lua state: %s\n", lh_error());
    return 1;
  }
  stub_handle_lua_init((void *)lh_state());

  const CtestSuite *suites[] = { &handle_suite, &font_suite };
  int failed = 0, total = 0;
  for (size_t i = 0; i < sizeof(suites) / sizeof(suites[0]); i++) {
    failed += run_suite(suites[i]);
    total  += suites[i]->count;
  }

  /* The leak gate. Every case is written to leave the count where it found it,
   * so this is a single number that says whether the convention actually closes
   * what it opens. */
  int live = cdin_handle_count(lh_state());
  printf("\n   handles still open: %d\n", live);
  if (live != 0) {
    printf("   FAIL  the handle count did not return to zero\n");
    failed++;
  }

  /* The stub's own blocks, released now that no test can still be comparing
   * against one. Before this existed the stub leaked every font the suite
   * loaded into the project's accounting for the life of the process, which is
   * harmless in a test but makes a failing run's allocator numbers harder to
   * read — and "harmless in a test" is how a real leak gets described later.
   *
   * Asserted rather than assumed: this is the one place the accounting can be
   * read end to end, so it is the place that proves the stub balances. */
  size_t gfx_live = cdin_mem_live(CDIN_MEM_GFX);
  ren_stub_free_all();
  size_t gfx_after = cdin_mem_live(CDIN_MEM_GFX);
  printf("   gfx bytes held by the stub: %zu -> %zu\n", gfx_live, gfx_after);
  if (gfx_after != 0) {
    printf("   FAIL  the stub still holds gfx bytes after freeing every font\n");
    failed++;
  }

  printf("\n");
  if (failed > 0) {
    printf("LUA-BOUNDARY TESTS FAILED (%d)\n", failed);
    lh_close();
    return 1;
  }
  printf("LUA-BOUNDARY TESTS OK (%d cases)\n", total);
  lh_close();
  return 0;
}