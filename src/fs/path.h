#ifndef FS_PATH_H
#define FS_PATH_H

#include <lua.h>
#include <lauxlib.h>
#include <lualib.h>

char *path_absolute_alloc(const char *path);
int path_absolute(const char *p, char *out, int out_size);
int luaopen_path(lua_State *L);

#endif 