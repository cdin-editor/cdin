#include "path.h"
#include "ops.h"
#include "../base/alloc.h"

#include <errno.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

#ifndef _WIN32
#  include <unistd.h>
#else
#  include <windows.h>
#  include <direct.h>
#  define realpath(x, y) _fullpath(y, x, FS_PATH_MAX)
#endif


char *path_absolute_alloc(const char *path) {
#ifdef _WIN32
  char *crt_res = _fullpath(NULL, path, MAX_PATH);
  if (!crt_res) return NULL;
#else
  char *crt_res = realpath(path, NULL);
  if (!crt_res) return NULL;
#endif

  size_t len = strlen(crt_res);
  char *cdin_res = cdin_alloc(CDIN_MEM_PLATFORM, len + 1);
  if (!cdin_res) { free(crt_res); return NULL; }
  memcpy(cdin_res, crt_res, len + 1);
  free(crt_res);
  return cdin_res;
}

int path_absolute(const char *p, char *out, int out_size) {
  char *res = path_absolute_alloc(p);
  if (!res) return -1;
  size_t len = strlen(res);
  if ((int)len >= out_size) { cdin_free(res); return -1; }
  memcpy(out, res, len + 1);
  cdin_free(res);
  return 0;
}


static int is_sep(char c) {
  return c == '/' || c == '\\';
}
static int last_sep(const char *s, size_t len) {
  for (int i = (int)len - 1; i >= 0; i--) {
    if (is_sep(s[i])) return i;
  }
  return -1;
}


static int f_absolute(lua_State *L) {
  const char *p = luaL_checkstring(L, 1);
  char out[FS_PATH_MAX];
  if (path_absolute(p, out, FS_PATH_MAX) != 0)
    return 0;   
  lua_pushstring(L, out);
  return 1;
}


static int f_join(lua_State *L) {
  int n = lua_gettop(L);
  luaL_Buffer b;
  luaL_buffinit(L, &b);

  for (int i = 1; i <= n; i++) {
    size_t len;
    const char *s = luaL_checklstring(L, i, &len);

    
    if (i < n) {
      while (len > 1 && is_sep(s[len - 1])) len--;
    }

    if (i > 1 && len > 0 && !is_sep(s[0])) {
      luaL_addchar(&b, FS_SEP);
    }
    luaL_addlstring(&b, s, len);
  }

  luaL_pushresult(&b);
  return 1;
}


static int f_basename(lua_State *L) {
  size_t len;
  const char *p = luaL_checklstring(L, 1, &len);

  
  while (len > 1 && is_sep(p[len - 1])) len--;

  int sep = last_sep(p, len);
  if (sep < 0) {
    lua_pushlstring(L, p, len);
  } else {
    lua_pushlstring(L, p + sep + 1, len - (size_t)(sep + 1));
  }
  return 1;
}


static int f_dirname(lua_State *L) {
  size_t len;
  const char *p = luaL_checklstring(L, 1, &len);

  
  size_t trimmed = len;
  while (trimmed > 1 && is_sep(p[trimmed - 1])) trimmed--;

  int sep = last_sep(p, trimmed);
  if (sep < 0) {
    lua_pushliteral(L, ".");
  } else if (sep == 0) {
    
    lua_pushlstring(L, p, 1);
  } else {
    
    size_t dlen = (size_t)sep;
    while (dlen > 1 && is_sep(p[dlen - 1])) dlen--;
    lua_pushlstring(L, p, dlen);
  }
  return 1;
}


static int f_ext(lua_State *L) {
  size_t len;
  const char *p = luaL_checklstring(L, 1, &len);

  
  for (int i = (int)len - 1; i >= 0; i--) {
    if (is_sep(p[i])) break;
    if (p[i] == '.' && i > 0 && !is_sep(p[i - 1])) {
      lua_pushlstring(L, p + i, len - (size_t)i);
      return 1;
    }
  }
  lua_pushliteral(L, "");
  return 1;
}


static int f_stem(lua_State *L) {
  size_t len;
  const char *p = luaL_checklstring(L, 1, &len);

  
  int base_start = 0;
  for (int i = (int)len - 1; i >= 0; i--) {
    if (is_sep(p[i])) { base_start = i + 1; break; }
  }

  
  int dot = -1;
  for (int i = (int)len - 1; i > base_start; i--) {
    if (p[i] == '.') { dot = i; break; }
  }

  if (dot < 0) {
    lua_pushlstring(L, p + base_start, len - (size_t)base_start);
  } else {
    lua_pushlstring(L, p + base_start, (size_t)(dot - base_start));
  }
  return 1;
}


static int f_split(lua_State *L) {
  f_dirname(L);   
  lua_pushvalue(L, 1);
  f_basename(L);  
  
  lua_remove(L, lua_gettop(L) - 2);  
  return 2;
}


static int f_normalize(lua_State *L) {
  size_t len;
  const char *p = luaL_checklstring(L, 1, &len);

  
  char out[FS_PATH_MAX];
  
  int comp_start[FS_PATH_MAX / 2];
  int depth = 0;
  size_t opos = 0;
  int leading_seps = 0;

  
  size_t i = 0;
  while (i < len && is_sep(p[i])) { i++; leading_seps++; }

  
  int abs = (leading_seps > 0);

  if (abs) {
    out[opos++] = FS_SEP;
#ifdef _WIN32
    if (leading_seps >= 2) out[opos++] = FS_SEP;
#endif
  }

  while (i <= len) {
    
    size_t j = i;
    while (j < len && !is_sep(p[j])) j++;

    size_t comp_len = j - i;

    if (comp_len == 0 || (comp_len == 1 && p[i] == '.')) {
      
    } else if (comp_len == 2 && p[i] == '.' && p[i + 1] == '.') {
      
      if (depth > 0) {
        opos = (size_t)comp_start[--depth];
        
        if (opos > 1 && is_sep(out[opos - 1])) opos--;
      }
      
    } else {
      
      if (opos > 0 && !is_sep(out[opos - 1])) {
        if (opos < FS_PATH_MAX - 1) out[opos++] = FS_SEP;
      }
      comp_start[depth++] = (int)opos;
      if (opos + comp_len < (size_t)(FS_PATH_MAX - 1)) {
        memcpy(out + opos, p + i, comp_len);
        opos += comp_len;
      }
    }

    i = j + 1;
  }

  if (opos == 0) {
    out[opos++] = abs ? FS_SEP : '.';
  }
  out[opos] = '\0';

  lua_pushstring(L, out);
  return 1;
}


static int f_is_absolute(lua_State *L) {
  size_t len;
  const char *p = luaL_checklstring(L, 1, &len);
  int result = 0;
#ifdef _WIN32
  
  if (len >= 3 && p[1] == ':' && is_sep(p[2])) result = 1;
  else if (len >= 2 && is_sep(p[0]) && is_sep(p[1])) result = 1;
  else if (len >= 1 && is_sep(p[0])) result = 1;
#else
  result = (len >= 1 && p[0] == '/');
#endif
  lua_pushboolean(L, result);
  return 1;
}


static const luaL_Reg lib[] = {
  { "absolute",    f_absolute    },
  { "join",        f_join        },
  { "basename",    f_basename    },
  { "dirname",     f_dirname     },
  { "ext",         f_ext         },
  { "stem",        f_stem        },
  { "split",       f_split       },
  { "normalize",   f_normalize   },
  { "is_absolute", f_is_absolute },
  { NULL, NULL }
};

int luaopen_path(lua_State *L) {
  luaL_newlib(L, lib);
  
  lua_pushlstring(L, (char[]){FS_SEP, '\0'}, 1);
  lua_setfield(L, -2, "sep");
  return 1;
}