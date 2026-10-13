/* The handle convention: every piece of C-owned state Lua can reach.
 *
 * One rule, applied to all of it: a handle is a userdata with a metatable that
 * has a __gc and a close() method, its type name in it, and a destructor that
 * runs exactly once. Nothing else in src/ is allowed to hand Lua a pointer.
 *
 * Why this exists rather than each module doing its own thing:
 *
 *   - Lifetime. Without one convention, "who frees this and when" is answered per
 *     module, and the answer is wrong somewhere. With it, __gc is the backstop,
 *     close() is the prompt path, and the destructor is the single place the
 *     resources are released.
 *   - Detection. A closed handle is *detectably* closed. cdin_handle_check
 *     refuses it, so a use-after-close is a Lua error naming the type, not a
 *     pointer into freed memory. That is the difference between a bug that
 *     reports itself and one that corrupts a document.
 *   - Type safety across the boundary. check() compares the type name, so
 *     passing a font where a surface belongs is an error, not a reinterpret.
 *
 * The type is void* at the Lua boundary on purpose. A caller cannot reach a
 * field, cannot compute an offset into a neighbouring allocation, and cannot
 * accidentally pass the pointer to free(). Every accessor goes through
 * cdin_handle_check, which is the only place that turns a userdata into a
 * pointer.
 *
 * Ownership: the handle owns whatever its destructor releases, and nothing else.
 * cdin_handle_new allocates the payload through cdin_alloc, so a handle shows up
 * in the per-subsystem report under the tag it was created with.
 *
 * Memory-order note: Lua is single-threaded (AGENTS.md §2.3), so __gc runs on the
 * thread that dropped the last reference and no synchronisation is needed. If a
 * handle's payload is shared with a worker, the handle is not the thing that
 * synchronises — see src/loop/queue.c when it exists.
 *
 * Errors: cdin_handle_check raises a Lua error naming what was expected and what
 * arrived. Raising from a check is the right place for it because the caller is
 * Lua and can catch it; the C side never sees it.
 */

#ifndef CDIN_LUA_HANDLE_H
#define CDIN_LUA_HANDLE_H

#include <stddef.h>

#include "lua.h"
#include "lauxlib.h"

#include "../base/error.h"

/* The metatable name every handle's metatable is prefixed with. One base name
 * rather than one metatable so that "is this a handle?" is a prefix test on the
 * metatable's __name, and so a type added later cannot forget to install a __gc.
 *
 * Public because Lua code is allowed to recognise a handle:
 * `getmetatable(h).__name:match("^cdin.handle/")` is how a caller asks "is this
 * one of yours?" without knowing the type. */
#define CDIN_HANDLE_MT "cdin.handle"

/* The destructor. Runs exactly once, either from close() or from __gc.
 *
 * `self` is the payload; `L` is the owning state, for a destructor that needs to
 * unregister something. It must not raise a Lua error — a __gc that errors is
 * reported by Lua and leaves the rest of the collection half-done, so anything
 * that can fail must have failed earlier and been reported then. */
typedef void (*CdinHandleDtor)(lua_State *L, void *self);

/* Registers a handle type: creates its metatable, with __gc, __close, __index
 * and __tostring, and remembers the destructor.
 *
 * Called once per type when a state is built. Calling it again for the same name
 * replaces the metatable, which is what makes a state rebuild safe.
 *
 * Returns CDIN_ERR_LIMIT when the type table is full. It is fixed-size on
 * purpose: types are a compile-time set, and an unbounded table keyed by a string
 * would be a place for a mistake to become a slow leak.
 *
 * `methods` may be NULL. When given it becomes the metatable's __index, so the
 * handle's own methods are reachable as `h:method()`. */
CdinErr cdin_handle_register(lua_State *L, const char *type_name,
                             CdinHandleDtor dtor, const luaL_Reg *methods);

/* Pushes a new handle payload of `size` bytes and returns it.
 *
 * The payload IS the userdata: Lua allocates it, not cdin_alloc, so it does not
 * appear in the per-subsystem accounting. Anything a handle owns beyond its own
 * fields — an image buffer, a file stream — is allocated by its module through
 * cdin_alloc with the right tag, and that is what shows up in core:memory. This
 * is stated here because "why is my handle not in the report" is otherwise a
 * reasonable question with no obvious answer.
 *
 * Registers `type_name` if it has not been registered, so a new type does not
 * have to be added in two places.
 *
 * Returns the payload, or NULL after raising. The caller has nothing useful to do
 * with a NULL: there is no handle to clean up, because the allocation that would
 * have needed cleaning up is the one that failed. */
void *cdin_handle_new(lua_State *L, size_t size, const char *type_name,
                      CdinHandleDtor dtor);

/* The value at `idx`, as a handle payload.
 *
 * Raises a Lua error and returns NULL unless the value is a handle, is not
 * closed, and — when `type_name` is given — is of that type. NULL is never
 * returned without an error having been raised, so the only correct use is
 *
 *     Thing *t = cdin_handle_check(L, 1, "thing");
 *
 * and if it is NULL the error is already on its way out. */
void *cdin_handle_check(lua_State *L, int idx, const char *type_name);

/* Whether the value at `idx` is a handle at all, closed or not. Never raises, so
 * it is safe to call on any argument. 1 yes, 0 no. */
int cdin_handle_is(lua_State *L, int idx);

/* Whether the value at `idx` is a live handle of `type_name`. Never raises. */
int cdin_handle_is_of(lua_State *L, int idx, const char *type_name);

/* Closes the handle at `idx`, running its destructor now and releasing whatever
 * the destructor owns. Idempotent: closing an already-closed handle is a no-op
 * returning 0, not an error, because a caller closing in an error path and a __gc
 * closing afterwards is the normal sequence and must not raise twice.
 *
 * Returns 1 if this call did the closing, 0 if it was already closed. The value
 * stays on the stack, now marked closed, so a stale reference is detectable
 * rather than dangling. */
int cdin_handle_close(lua_State *L, int idx);

/* How many handles this state currently holds, live and closed. Reported by
 * core:memory; a number that does not fall when things are closed is the signal
 * that something is not being closed. */
int cdin_handle_count(lua_State *L);

/* Installs the registry. Called once at state creation; calling it again is
 * harmless and rebuilds it, so a state that is built twice does not have to know. */
void cdin_handle_init(lua_State *L);

/* Maximum distinct handle types. Compile-time, because the alternative is a
 * dynamic table that grows with whatever strings arrive as type names. */
#define CDIN_HANDLE_MAX_TYPES 32

#endif /* CDIN_LUA_HANDLE_H */