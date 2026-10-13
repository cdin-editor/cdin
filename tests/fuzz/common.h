/* Fuzz-harness scaffolding: the driver contract every parser harness uses.
 *
 * Phase 0 lays this down before the harnesses themselves. The reason is that a
 * fuzz target is easy to write in a way that never fails — one that validates
 * its own input, or asserts something the function already guarantees — and
 * then reports zero crashes for a week. The rules below are what make a run
 * mean something, and every harness here follows them.
 *
 *   1. Take bytes the fuzzer chose. Do not normalise, trim or validate them
 *      before the call. The parser under test is the thing that has to cope.
 *   2. Call the real entry point, on the real types. A harness that calls a
 *      helper is testing the helper.
 *   3. Assert the invariants that must hold for ANY input: no crash, no
 *      out-of-bounds access, and every returned index inside the buffer it came
 *      from. A parser that returns a length longer than its input is a bug even
 *      when it does not crash.
 *   4. Report a violated invariant with FUZZ_FAIL(), never with a return value.
 *      libFuzzer ignores the return value of the target (anything but 0/-1 is
 *      reserved), so `return 1` after a message let the process exit 0 and the
 *      violation went unrecorded. FUZZ_FAIL() prints nothing itself: print the
 *      reason to stderr first, then call it. Do not use assert(): it vanishes
 *      under NDEBUG. And an invariant must hold for every input the harness
 *      can build, including NUL-truncated ones, or it is a false positive.
 *   5. Seed with the corpus in tests/fuzz/corpus/<name>/. It is checked in, so
 *      a crash found once is reproducible on every machine.
 *
 * Building one target:
 *
 *   clang -fsanitize=fuzzer,address,undefined -I src \
 *         tests/fuzz/fuzz_utf8.c src/text/utf8.c -o fuzz_utf8
 *   ./fuzz_utf8 -max_total_time=60 tests/fuzz/corpus/utf8
 *
 * Under MSVC/Windows or with a compiler that has no -fsanitize=fuzzer, the same
 * file builds as an AFL-style driver by defining AFL_DRIVER; see each harness.
 */

#ifndef CDIN_FUZZ_COMMON_H
#define CDIN_FUZZ_COMMON_H

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Refuse an input so large it would make the harness, not the parser, the
 * thing under test. 1 MiB is well past anything the parser will see in a
 * corpus and well below where the harness's own buffers matter. */
/* A violated invariant must crash, or the fuzzer cannot see it. */
#define FUZZ_FAIL() abort()

#define FUZZ_MAX_INPUT (1u << 20)

static inline size_t fuzz_clamp(size_t n) {
  return n > FUZZ_MAX_INPUT ? FUZZ_MAX_INPUT : n;
}

/* Zero-length input is not a no-op for a parser: it is the empty document, the
 * empty string, the empty file. Every harness here is called with it. */
#define FUZZ_ACCEPT_EMPTY 1

#endif /* CDIN_FUZZ_COMMON_H */
