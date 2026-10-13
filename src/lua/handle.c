/* The handle convention. See handle.h for the rule and why it exists.
 *
 * Layout of a handle's userdata:
 *
 *     +----------------+------------------------+
 *     | HandleHeader   | payload (size bytes)   |
 *     +----------------+------------------------+
 *     ^ the pointer handed to C is here, ^ the Lua userdata starts here
 *
 * The header is a union with max_align_t so the payload keeps the platform's
 * maximum alignment without this file reasoning about it. It is 16 bytes on LP64,
 * which is worth stating because "one header per handle" is otherwise a number
 * nobody has checked: handles are not in the millions, so this is not the
 * per-line cost that matters anywhere.
 *
 * Where the destructor lives: one metatable per type, named
 * "cdin.handle/<type>", so __gc reads its own metatable to find out what it is
 * collecting. The destructor itself is kept in a fixed C-side table next to the
 * type name, because a C function pointer has no faithful representation as a
 * Lua value — pushing a light userdata built from one would be a cast the
 * standard does not bless.
 *
 * Ownership: the handle owns whatever its destructor releases. The userdata
 * itself is Lua's. Nothing here allocates.
 *
 * Threads: none of this touches shared state except the static type table, which
 * is written by cdin_handle_register at state construction and read-only after.
 * Lua is single-threaded (AGENTS.md §2.3), so there is no lock and none is needed.
 */

#include "handle.h"

#include <stdalign.h>
#include <stdint.h>
#include <string.h>

#include <lauxlib.h>

#include "../core/logger.h"

/* Key for this module's tables in the Lua registry. A light userdata, so it
 * cannot collide with a string key anyone else chose. */
static const char HANDLE_REGISTRY = 0;

/* Per-instance state. `closed` is the whole point of the convention: it is what
 * turns a use-after-close from a wild pointer into a Lua error. */
typedef union {
  struct {
    int closed;   /* 0 live, 1 closed and destructed */
    int pad;      /* keeps the union at max_align_t's size */
  } h;
  max_align_t align;
} HandleHeader;

/* ── the type table ────────────────────────────────────────────────────── */

/* One row per registered type. Fixed size: the alternative is a table keyed by
 * whatever string arrives as a type name, which is a slow leak waiting for a
 * typo. Compile-time, checked at registration, and reported rather than
 * overwritten. */
typedef struct {
  const char    *name;   /* borrowed, static: the bare type name           */
  char          mtname[sizeof(CDIN_HANDLE_MT) + 64]; /* "cdin.handle/<name>" */
  CdinHandleDtor dtor;   /* NULL for a type with nothing to release        */
} HandleType;

static HandleType types[CDIN_HANDLE_MAX_TYPES];
static int type_count;

/* Count of live handles for the state, kept in the registry rather than in a
 * static so two Lua states cannot see each other's handles. */
static int handle_count_of(lua_State *L) {
  if (!lua_rawgetp(L, LUA_REGISTRYINDEX, &HANDLE_REGISTRY)) return 0;
  if (!lua_istable(L, -1)) { lua_pop(L, 1); return 0; }
  lua_getfield(L, -1, "count");
  int n = (int)lua_tointeger(L, -1);
  lua_pop(L, 2);
  return n;
}

static void set_handle_count(lua_State *L, int n) {
  if (!lua_rawgetp(L, LUA_REGISTRYINDEX, &HANDLE_REGISTRY)) return;
  if (!lua_istable(L, -1)) { lua_pop(L, 1); return; }
  lua_pushinteger(L, n);
  lua_setfield(L, -2, "count");
  lua_pop(L, 1);
}

/* The metatable name for a type: "cdin.handle/font". Built into a caller-provided
 * buffer so registration never allocates.
 *
 * Two callers need it — registration, which stores it in the row, and
 * construction, which needs it to find the metatable again. */
static void metatable_name(char *buf, size_t cap, const char *type_name) {
  size_t prefix = sizeof(CDIN_HANDLE_MT);   /* includes the NUL */
  size_t n = strlen(type_name);
  if (prefix + n + 1 > cap) { buf[0] = '\0'; return; }
  memcpy(buf, CDIN_HANDLE_MT, prefix - 1);
  buf[prefix - 1] = '/';
  memcpy(buf + prefix, type_name, n);
  buf[prefix + n] = '\0';
}

/* Looks a type up by its METATABLE name, which is what __gc and __close have.
 *
 * By strcmp, not by pointer. The pointer comparison this used to do was an
 * optimisation that cannot work: the name a metamethod sees is Lua's interned
 * string and the name stored here is a copy inside this struct, so they are
 * never the same address. Every lookup missed, which meant every destructor
 * silently did not run and every re-registration appended a duplicate row until
 * the fixed table filled with "thing" twenty times over.
 *
 * The other caller of this — construction — does not need it at all, since
 * registration is idempotent and just calls register directly. */
static HandleType *type_find(const char *mtname) {
  if (!mtname) return NULL;
  for (int i = 0; i < type_count; i++) {
    if (strcmp(types[i].mtname, mtname) == 0) return &types[i];
  }
  return NULL;
}

/* ── metamethods ───────────────────────────────────────────────────────── */

/* The payload at `idx`, for the __gc and __close metamethods.
 *
 * lua_touserdata, deliberately, rather than luaL_checkudata(L, idx, NULL).
 * Passing NULL as the type name is the obvious way to say "any userdata" and it
 * crashes on this Lua: the call segfaults inside a strcmp even with a valid
 * userdata as the argument, which a backtrace found and lauxlib.h does not
 * mention — it declares the function but not what it does with a NULL name. The
 * type is checked separately anyway, by handle_at, which compares against the
 * metatable this module installed; the only thing needed here is the pointer. */
static HandleHeader *handle_self(lua_State *L, int idx) {
  void *ud = lua_touserdata(L, idx);
  if (!ud) luaL_argerror(L, idx, "cdin handle expected");
  return (HandleHeader *)ud;
}

/* __gc. Lua calls this when the userdata becomes unreachable.
 *
 * The payload pointer is recovered from the userdata rather than kept in an
 * upvalue, because an upvalue holding the payload would keep it alive forever —
 * the classic way a __gc silently never runs.
 *
 * Returns 0 as Lua requires of a __gc. */
static int handle_gc(lua_State *L) {
  HandleHeader *h = handle_self(L, 1);
  if (h->h.closed) return 0;      /* already closed by close(): nothing to do */

  /* The metatable is this type's, so __name identifies the row. */
  const char *name = NULL;
  if (lua_getmetatable(L, 1)) {
    lua_getfield(L, -1, "__name");
    name = lua_tostring(L, -1);
    HandleType *t = name ? type_find(name) : NULL;
    lua_pop(L, 2);
    if (t && t->dtor) t->dtor(L, (char *)h + sizeof(HandleHeader));
  }

  h->h.closed = 1;
  set_handle_count(L, handle_count_of(L) - 1);
  return 0;
}


/* __close, for use in a to-be-closed variable. Lua calls it on scope exit, in
 * reverse order of declaration, and again for the error case. Same body as
 * close() rather than the gc, because a handle can be closed explicitly while
 * still being reachable. */
static int handle_close_method(lua_State *L) {
  HandleHeader *h = handle_self(L, 1);
  if (h->h.closed) {
    lua_pushboolean(L, 0);
    return 1;
  }

  const char *name = NULL;
  HandleType *t = NULL;
  if (lua_getmetatable(L, 1)) {
    lua_getfield(L, -1, "__name");
    name = lua_tostring(L, -1);
    t = name ? type_find(name) : NULL;
    lua_pop(L, 2);
  }
  if (t && t->dtor) t->dtor(L, (char *)h + sizeof(HandleHeader));

  h->h.closed = 1;
  set_handle_count(L, handle_count_of(L) - 1);
  lua_pushboolean(L, 1);
  return 1;
}

/* __tostring, so a handle in an error message or a REPL identifies itself. The
 * absence of this is why "attempt to index a nil value" is the only thing a user
 * gets to see about a handle they got wrong.
 *
 * Says whether it is closed, rather than always saying so. A handle printed as
 * "cdin.handle/font (closed)" while it is open is worse than no __tostring at
 * all: it teaches a reader to ignore the word, so the one time it matters it is
 * the one time they do not. */
static int handle_tostring(lua_State *L) {
  HandleHeader *h = handle_self(L, 1);
  if (!lua_getmetatable(L, 1)) return 0;

  lua_getfield(L, -1, "__name");
  const char *name = lua_tostring(L, -1);
  if (!name) {
    lua_pop(L, 2);
    lua_pushliteral(L, "cdin.handle (untyped)");
    return 1;
  }

  lua_pushfstring(L, "%s%s", name, h->h.closed ? " (closed)" : "");
  lua_remove(L, -2);   /* __name */
  lua_remove(L, -2);   /* metatable */
  return 1;
}

/* A close() method on every handle, so Lua code can release one without waiting
 * for a collection. Registered on the metatable's __index table below. */
static const luaL_Reg handle_methods[] = {
  { "close", handle_close_method },
  { NULL, NULL },
};

/* ── registration ──────────────────────────────────────────────────────── */

CdinErr cdin_handle_register(lua_State *L, const char *type_name,
                             CdinHandleDtor dtor, const luaL_Reg *methods) {
  if (!type_name || !*type_name) return CDIN_ERR_INVALID;

  char mtname[sizeof(CDIN_HANDLE_MT) + 64];
  metatable_name(mtname, sizeof mtname, type_name);
  if (mtname[0] == '\0') {
    log_error("handle: type name \"%s\" is too long for a metatable name",
              type_name);
    return CDIN_ERR_LIMIT;
  }

  /* Lookup and row-filling happen AFTER the name is known, because the row is
   * keyed by the metatable name and every path that asks "is this type
   * registered?" has one in hand. */
  HandleType *existing = type_find(mtname);
  if (!existing) {
    if (type_count >= CDIN_HANDLE_MAX_TYPES) {
      /* Reported, not grown into. A handle type is a compile-time decision; a
       * runtime that needed more than 32 of them has a design problem, and
       * silently allocating room for it would hide that. */
      log_error("handle: no room for type \"%s\" — the limit is %d",
                type_name, CDIN_HANDLE_MAX_TYPES);
      return CDIN_ERR_LIMIT;
    }
    existing = &types[type_count++];
    existing->name = type_name;
    memcpy(existing->mtname, mtname, strlen(mtname) + 1);
  }
  existing->dtor = dtor;

  /* Registering the metatable again for the same state replaces it, which is what
   * makes a state rebuild safe. */
  if (luaL_newmetatable(L, mtname)) {
    lua_pushvalue(L, -1);
    lua_setfield(L, -2, "__index");     /* methods on itself */
    lua_pushcfunction(L, handle_gc);
    lua_setfield(L, -2, "__gc");
    lua_pushcfunction(L, handle_close_method);
    lua_setfield(L, -2, "__close");
    lua_pushcfunction(L, handle_tostring);
    lua_setfield(L, -2, "__tostring");
    lua_pushstring(L, mtname);
    lua_setfield(L, -2, "__name");
    lua_pushstring(L, type_name);
    lua_setfield(L, -2, "__type");

    /* Every handle gets close() even when the type brings its own methods, so a
     * caller's method table cannot accidentally shadow the one thing that must
     * always work. */
    lua_newtable(L);
    luaL_setfuncs(L, handle_methods, 0);
    if (methods) {
      /* The type's own methods go in front, so a type may override close() if it
       * genuinely needs to — and then it has to close itself, which is a choice
       * a reader can see. */
      for (const luaL_Reg *m = methods; m->name; m++) {
        lua_pushcfunction(L, m->func);
        lua_setfield(L, -2, m->name);
      }
    }
    lua_setfield(L, -2, "__index");

    /* The pop belongs INSIDE this branch, and that is the whole comment.
     * luaL_newmetatable pushes the metatable only when it creates one; on a
     * re-registration it pushes nothing and returns 0. An unconditional pop here
     * therefore underflows Lua's stack the second time a type is registered —
     * which is every handle after the first, because cdin_handle_new registers
     * on each construction. An underflowed stack is not an error return: it
     * corrupts the stack and crashes a few calls later, in whatever Lua function
     * happens to be next. */
    lua_pop(L, 1);
  }
  return CDIN_OK;
}

void cdin_handle_init(lua_State *L) {
  /* Three stack rules in one function, each of which cost a crash:
   *
   *  - lua_rawgetp ALWAYS pushes, whether or not the key is there. Testing its
   *    return value and popping only on the "found" path leaves the nil sitting
   *    on the stack, so the first call to init leaks one slot and every later
   *    stack index in the caller is off by one. That is how a namespace table
   *    built afterwards ends up on the wrong value and the editor panics during
   *    library registration.
   *
   *  - lua_rawsetp POPS the value, so there is no pop after it.
   *
   *  - an existing entry is left alone rather than replaced: rebuilding the table
   *    would reset the live-handle count to zero while handles were still open,
   *    so the number that exists to catch leaks would go back to looking healthy.
   */
  int found = lua_rawgetp(L, LUA_REGISTRYINDEX, &HANDLE_REGISTRY) != LUA_TNIL;
  lua_pop(L, 1);

  if (found) return;

  lua_newtable(L);
  lua_pushinteger(L, 0);
  lua_setfield(L, -2, "count");
  lua_rawsetp(L, LUA_REGISTRYINDEX, &HANDLE_REGISTRY);
}

/* ── construction ──────────────────────────────────────────────────────── */

void *cdin_handle_new(lua_State *L, size_t size, const char *type_name,
                      CdinHandleDtor dtor) {
  if (!type_name || !*type_name) {
    luaL_error(L, "cdin_handle_new: type_name is required");
    return NULL;
  }

  /* Idempotent and cheap, and it means a caller who forgot to init gets a working
   * handle count rather than a silently never-updated one. */
  cdin_handle_init(L);

  /* Registration is idempotent, so construction just calls it. The earlier
   `if (!found || dtor != NULL)` guard existed to avoid re-registering, and with a
   lookup that never matched it re-registered anyway — which is how twenty copies
   of "thing" ended up in a table meant to hold thirty-two distinct types. */
  {
    CdinErr err = cdin_handle_register(L, type_name, dtor, NULL);
    if (err != CDIN_OK) {
      /* Raising here is right: the caller is a binding function that cannot
       * meaningfully continue without the object, and the type table being full
       * is a runtime configuration fault that should stop the boot rather than
       * produce a handle with no destructor. */
      luaL_error(L, "cdin_handle_new: cannot register handle type \"%s\"", type_name);
      return NULL;
    }
  }

    /* Payload after a header, and the total is checked rather than assumed: a
   * handle that wraps a buffer sized from a file could otherwise wrap. */
  size_t total = sizeof(HandleHeader) + size;
  if (total < size) {
    luaL_error(L, "cdin_handle_new: %zu byte handle overflows a size_t", size);
    return NULL;
  }

  void *ud = lua_newuserdatauv(L, total, 0);
  if (!ud) {
    /* lua_newuserdatauv raises on failure itself; this is belt and braces for a
     * build where it might not. */
    luaL_error(L, "cdin_handle_new: out of memory for a %zu byte handle", size);
    return NULL;
  }

  HandleHeader *h = (HandleHeader *)ud;
  h->h.closed = 0;
  h->h.pad = 0;
  memset((char *)ud + sizeof(HandleHeader), 0, size);

    char mtname[128];
  metatable_name(mtname, sizeof mtname, type_name);
  luaL_getmetatable(L, mtname);
    lua_setmetatable(L, -2);
  
  set_handle_count(L, handle_count_of(L) + 1);
  return (char *)ud + sizeof(HandleHeader);
}

/* ── inspection ────────────────────────────────────────────────────────── */

/* The handle at `idx`, or NULL with nothing raised. Returns NULL for a
 * non-userdata, a userdata without one of our metatables, or a closed one —
 * which is why every caller that returns an error to Lua must use
 * cdin_handle_check and not this. */
static HandleHeader *handle_at(lua_State *L, int idx, const char **type_out) {
  if (type_out) *type_out = NULL;
  if (!lua_isuserdata(L, idx)) return NULL;
  if (!lua_getmetatable(L, idx)) return NULL;

  lua_getfield(L, -1, "__name");
  const char *name = lua_tostring(L, -1);
  if (!name || strncmp(name, CDIN_HANDLE_MT, sizeof(CDIN_HANDLE_MT) - 1) != 0) {
    lua_pop(L, 2);
    return NULL;
  }
  lua_pop(L, 1);        /* __name */
  if (type_out) *type_out = name;
  lua_pop(L, 1);        /* metatable */
  return (HandleHeader *)lua_touserdata(L, idx);
}

int cdin_handle_is(lua_State *L, int idx) {
  return handle_at(L, idx, NULL) != NULL ? 1 : 0;
}

int cdin_handle_is_of(lua_State *L, int idx, const char *type_name) {
  const char *name = NULL;
  HandleHeader *h = handle_at(L, idx, &name);
  if (!h || h->h.closed) return 0;
  if (!type_name) return 1;
  return name && strcmp(name + sizeof(CDIN_HANDLE_MT), type_name) == 0;
}

void *cdin_handle_check(lua_State *L, int idx, const char *type_name) {
  const char *name = NULL;
  HandleHeader *h = handle_at(L, idx, &name);

  if (!h) {
    luaL_error(L, "expected a cdin handle%s%s, got %s",
               type_name ? " of type " : "",
               type_name ? type_name : "",
               luaL_typename(L, idx));
    return NULL;
  }
  if (h->h.closed) {
    luaL_error(L, "%s handle is closed",
               name ? name + sizeof(CDIN_HANDLE_MT) : "cdin handle");
    return NULL;
  }
  if (type_name) {
    const char *actual = name + sizeof(CDIN_HANDLE_MT);
    if (strcmp(actual, type_name) != 0) {
      /* Naming both types. "expected a font, got a surface" is a bug report
       * someone can act on; "bad argument" is not. */
      luaL_error(L, "expected a %s handle, got a %s", type_name, actual);
      return NULL;
    }
  }
  return (char *)h + sizeof(HandleHeader);
}

int cdin_handle_close(lua_State *L, int idx) {
  HandleHeader *h = handle_at(L, idx, NULL);
  if (!h || h->h.closed) return 0;

  if (lua_getmetatable(L, idx)) {
    lua_getfield(L, -1, "__name");
    const char *name = lua_tostring(L, -1);
    HandleType *t = name ? type_find(name) : NULL;
    lua_pop(L, 2);
    if (t && t->dtor) t->dtor(L, (char *)h + sizeof(HandleHeader));
  }

  h->h.closed = 1;
  set_handle_count(L, handle_count_of(L) - 1);
  return 1;
}

int cdin_handle_count(lua_State *L) {
  return handle_count_of(L);
}