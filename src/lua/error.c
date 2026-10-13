/* The uniform error convention. See error.h for the shape and the reasoning. */

#include "error.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include <lauxlib.h>

/* Longest formatted detail accepted. A detail longer than this is a bug in the
 * caller rather than a message, and truncating it here is better than formatting
 * into a buffer whose size the caller chose. */
#define ERROR_DETAIL_MAX 512

static int push_error_table(lua_State *L, CdinErrDetail detail,
                            const char *detail_text) {
  lua_newtable(L);

  lua_pushstring(L, cdin_err_name(detail.code));
  lua_setfield(L, -2, "code");

  lua_pushstring(L, cdin_err_name(detail.code));
  lua_setfield(L, -2, "name");

  /* Always a string, never nil. "" means "nothing to add" and nil would mean
   * "no detail field", and a caller cannot do anything useful with the
   * difference — so the field exists either way and the value says which. */
  lua_pushstring(L, detail_text ? detail_text : "");
  lua_setfield(L, -2, "detail");

  /* detail_text wins over the CdinErrDetail's own detail: the caller had the
   * context and this is the string meant for a human. */
  lua_pushinteger(L, (lua_Integer)detail.line);
  lua_setfield(L, -2, "line");

  /* 0 rather than nil when the OS gave no code, so arithmetic on it does not
   * need a guard. */
  lua_pushinteger(L, (lua_Integer)detail.os_code);
  lua_setfield(L, -2, "os");

  return 1;
}

int cdin_error_push(lua_State *L, CdinErrDetail detail, const char *detail_text) {
  return push_error_table(L, detail, detail_text);
}

int cdin_error_pushf(lua_State *L, CdinErrDetail detail, const char *fmt, ...) {
  char buf[ERROR_DETAIL_MAX];

  va_list ap;
  va_start(ap, fmt);
  int n = vsnprintf(buf, sizeof buf, fmt, ap);
  va_end(ap);

  if (n < 0) {
    /* vsnprintf failed, which for a "%s" of a "%s" means the arguments were
     * wrong. Say so rather than pushing whatever is in the buffer. */
    buf[0] = '\0';
  } else if ((size_t)n >= sizeof buf) {
    /* Truncated. Recorded in the message itself, because a silently shortened
     * path is the kind of detail that sends someone looking in the wrong
     * directory. */
    size_t at = sizeof buf - 5;
    memcpy(buf + at, "...", 4);
  }

  return push_error_table(L, detail, buf);
}

int cdin_error_raise(lua_State *L, CdinErrDetail detail, const char *detail_text) {
  push_error_table(L, detail, detail_text);
  const char *code = cdin_err_name(detail.code);

  /* The table is left on the stack and lua_error long-jumps, so it is never
   * popped. That is deliberate: Lua keeps the error object alive for a pcall
   * handler, which is the only reason the table was built. */
  lua_pushstring(L, detail_text && detail_text[0] ? detail_text : code);
  lua_concat(L, 2);      /* "code: detail", or just "code" when there is no detail */

  /* message on top, table under it: lua_error takes the error object and uses
   * __tostring/__name when it is not a string. */
  lua_error(L);
  return 0;   /* not reached */
}

int cdin_api_version(lua_State *L) {
  lua_pushinteger(L, CDIN_API_VERSION);
  return 1;
}