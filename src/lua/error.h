/* The uniform error convention, and the contract version.
 *
 * One shape for every error crossing the C boundary, so a caller never has to
 * know which function it called to find out how the failure is spelled:
 *
 *     { code = "not_found", name = "not_found", detail = "D:/missing.txt",
 *       line = 217, os = 2 }
 *
 * `code` is the stable machine-readable string and the only field callers should
 * branch on. `name` is the same value today and exists so a human reading a dump
 * does not have to know that `code` is the identifier. `detail` is a string,
 * never nil, because a missing detail and an empty one are different facts and a
 * caller that cannot tell them apart will print "" for both.
 *
 * Why a table and not a string: an error a caller cannot branch on is a log line.
 * Phase 2 exposes these to Lua and to cdin-x, and both need to say "not found"
 * differently from "refused".
 *
 * Why not raise: raising discards everything except the message, so a caller that
 * wants to recover — close the document, fall back to the next font, offer a
 * different path — has nothing to recover with. So the C functions push a table
 * and return a count, and only the *binding* layer decides to raise, which is
 * where a decision can be made per function.
 *
 * Ownership: the table is pushed on the Lua stack and owned by Lua. `detail` is
 * borrowed from the C caller and copied into a Lua string, so the caller keeps
 * ownership of its own buffer.
 *
 * cdin.api_version: the extension contract's version, as a single integer, so a
 * plugin can refuse to load against a host it was not written for instead of
 * failing later in a way that looks like a bug in the plugin.
 */

#ifndef CDIN_LUA_ERROR_H
#define CDIN_LUA_ERROR_H

#include "lua.h"

#include "../base/error.h"

/* The extension contract version this build implements.
 *
 * A single integer, bumped when a row of docs/architecture/extension-contract.md
 * changes shape. Not a semver string: a plugin branches on it, and a string
 * invites parsing a thing that should be compared. Pre-1.0, so it starts at 1
 * and the rule is "bump on any incompatible change".
 *
 * Kept next to the error convention because both are the "what does the boundary
 * look like" declarations, and a reader who has one has usually been given the
 * other. */
#define CDIN_API_VERSION 1

/* Pushes `detail` as the standard error table and returns 1, so a binding can
 * `return cdin_error_push(L, e, "open failed");` — which is a valid Lua return
 * and reads as one.
 *
 * Never raises. See the file comment for why. */
int cdin_error_push(lua_State *L, CdinErrDetail detail, const char *detail_text);

/* cdin_error_push for a message built by a printf-style format. Kept separate
 * rather than a variadic cdin_error_pushf because the fixed-arity version is the
 * one every call site uses, and a variadic one makes every call site's format
 * string an unchecked contract. Use this one when the detail is assembled. */
int cdin_error_pushf(lua_State *L, CdinErrDetail detail, const char *fmt, ...);

/* The same table, raised as a Lua error. For a binding function whose failure has
 * no sensible continuation: the message is "code: detail" and the table is
 * attached as the error object's payload, so a pcall handler can recover the
 * code without parsing the message. */
int cdin_error_raise(lua_State *L, CdinErrDetail detail, const char *detail_text);

/* Pushes CDIN_API_VERSION. */
int cdin_api_version(lua_State *L);

#endif /* CDIN_LUA_ERROR_H */