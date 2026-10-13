/* The Lua harness the handle and error suites run against.
 *
 * Small on purpose: a state, some assertions callable from C, and nothing else.
 * The suites drive the code under test through Lua chunks, because that is how
 * the code is actually used — and a C test that called cdin_handle_new directly
 * would not exercise the metatable, __gc or close() paths at all, which are the
 * parts with the bugs in them.
 */

#ifndef CDIN_TESTS_LUA_HARNESS_H
#define CDIN_TESTS_LUA_HARNESS_H

#include <stdarg.h>
#include <stddef.h>

#include <lua.h>

/* The shared state. Created by lh_init, valid until lh_close. */
lua_State *lh_state(void);

int  lh_init(void);
void lh_close(void);

/* Evaluates a chunk. Returns 1 if it ran, 0 if it raised — a raise is recorded
 * as a failure, because every chunk these suites evaluate is supposed to work. */
int lh_eval(const char *code);

/* Evaluates a chunk and requires it to raise, copying the message out. Returns 1
 * if it raised. */
int lh_eval_raises(const char *code, char *out, size_t cap);

/* Assertions. Each records a failure with a message and returns 1 on success. */
int lh_bool(const char *expr, int want);
int lh_int(const char *expr, long long want);
int lh_eq(const char *a, const char *b);
int lh_contains(const char *haystack_expr, const char *needle);
void lh_fail(const char *fmt, ...);

/* Failure count so far, and the last message. */
int         lh_failed(void);
const char *lh_error(void);

#endif /* CDIN_TESTS_LUA_HARNESS_H */