#include <SDL3/SDL.h>
#include <stdbool.h>
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <sys/stat.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include "api.h"
#include "../base/alloc.h"
#include "../lua/error.h"
#include "../loop/loop.h"
#include "../ui/renderer_cache.h"
#include "../core/window.h"
#include "../core/logger.h"
#include "../search/find.h"
#include "../fs/path.h"

/* The damage cache's command buffer, reported so a caller can see how close
 * the frame came to the ceiling rather than only that it was hit. Mirrors
 * COMMAND_BUF_SIZE in renderer_cache.c; the two cannot drift because
 * rencache_get_stats returns the peak from the same buffer that bounds it. */
#define COMMAND_BUF_SIZE (1024 * 512)

#ifndef _WIN32
  #include <unistd.h>
#else
  #include <windows.h>
  #include <direct.h>
  #define realpath(x, y) _fullpath(y, x, MAX_PATH)
#endif

extern SDL_Window *window;


static const char *button_name(int button) {
  switch (button) {
    case 1:  return "left";
    case 2:  return "middle";
    case 3:  return "right";
    default: return "?";
  }
}

static char *key_name(char *dst, int sym) {
  const char *name = SDL_GetKeyName(sym);
  strncpy(dst, name, 15);
  dst[15] = '\0';
  for (char *p = dst; *p; p++) {
    *p = (char)tolower((unsigned char)*p);
  }
  return dst;
}


static int f_poll_event(lua_State *L) {
  char buf[16];
  SDL_Event e;

top:
  if (!SDL_PollEvent(&e)) {
    return 0;
  }

  switch (e.type) {
    /* ── quit ── */
    case SDL_EVENT_QUIT:
      lua_pushstring(L, "quit");
      return 1;

    /* ── window events (SDL3: separate event types) ── */
    case SDL_EVENT_WINDOW_RESIZED:
      lua_pushstring(L, "resized");
      lua_pushnumber(L, e.window.data1);
      lua_pushnumber(L, e.window.data2);
      return 3;

    case SDL_EVENT_WINDOW_EXPOSED:
    case SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED:
    case SDL_EVENT_WINDOW_MAXIMIZED:
    case SDL_EVENT_WINDOW_RESTORED:
    case SDL_EVENT_WINDOW_SHOWN:
    case SDL_EVENT_WINDOW_DISPLAY_SCALE_CHANGED:
      rencache_invalidate();
      lua_pushstring(L, "exposed");
      return 1;

    case SDL_EVENT_WINDOW_FOCUS_GAINED:
      SDL_FlushEvents(SDL_EVENT_TEXT_INPUT, SDL_EVENT_TEXT_INPUT);
      goto top;

    case SDL_EVENT_DROP_FILE: {
      float mx, my;
      SDL_GetGlobalMouseState(&mx, &my);
      int wx, wy;
      SDL_GetWindowPosition(window, &wx, &wy);
      lua_pushstring(L, "filedropped");
      lua_pushstring(L, e.drop.data);
      lua_pushnumber(L, mx - (float)wx);
      lua_pushnumber(L, my - (float)wy);
      return 4;
    }

    /* ── keyboard ── */
    case SDL_EVENT_KEY_DOWN:
      lua_pushstring(L, "keypressed");
      lua_pushstring(L, key_name(buf, e.key.key));
      return 2;

    case SDL_EVENT_KEY_UP:
      lua_pushstring(L, "keyreleased");
      lua_pushstring(L, key_name(buf, e.key.key));
      return 2;

    case SDL_EVENT_TEXT_INPUT:
      lua_pushstring(L, "textinput");
      lua_pushstring(L, e.text.text);
      return 2;

    /* ── mouse ── */
    case SDL_EVENT_MOUSE_BUTTON_DOWN:
      if (e.button.button == 1) SDL_CaptureMouse(true);
      lua_pushstring(L, "mousepressed");
      lua_pushstring(L, button_name(e.button.button));
      lua_pushnumber(L, e.button.x);
      lua_pushnumber(L, e.button.y);
      lua_pushnumber(L, e.button.clicks);
      return 5;

    case SDL_EVENT_MOUSE_BUTTON_UP:
      if (e.button.button == 1) SDL_CaptureMouse(false);
      lua_pushstring(L, "mousereleased");
      lua_pushstring(L, button_name(e.button.button));
      lua_pushnumber(L, e.button.x);
      lua_pushnumber(L, e.button.y);
      return 4;

    case SDL_EVENT_MOUSE_MOTION:
      lua_pushstring(L, "mousemoved");
      lua_pushnumber(L, e.motion.x);
      lua_pushnumber(L, e.motion.y);
      lua_pushnumber(L, e.motion.xrel);
      lua_pushnumber(L, e.motion.yrel);
      return 5;

    case SDL_EVENT_MOUSE_WHEEL:
      lua_pushstring(L, "mousewheel");
      lua_pushnumber(L, e.wheel.y);
      return 2;

    default:
      goto top;
  }

  return 0;
}


static int f_wait_event(lua_State *L) {
  double n = luaL_checknumber(L, 1);
  lua_pushboolean(L, SDL_WaitEventTimeout(NULL, (Sint32)(n * 1000)));
  return 1;
}


/* ── cursor ── */
static SDL_Cursor *cursor_cache[8];

static const char *cursor_opts[] = {
  "arrow", "ibeam", "sizeh", "sizev", "hand", NULL
};

static const SDL_SystemCursor cursor_enums[] = {
  SDL_SYSTEM_CURSOR_DEFAULT,
  SDL_SYSTEM_CURSOR_TEXT,
  SDL_SYSTEM_CURSOR_EW_RESIZE,
  SDL_SYSTEM_CURSOR_NS_RESIZE,
  SDL_SYSTEM_CURSOR_POINTER,
};

static int f_set_cursor(lua_State *L) {
  int opt = luaL_checkoption(L, 1, "arrow", cursor_opts);
  SDL_SystemCursor id = cursor_enums[opt];
  if (!cursor_cache[opt]) {
    log_debug("system: creating and caching cursor \"%s\"", cursor_opts[opt]);
    cursor_cache[opt] = SDL_CreateSystemCursor(id);
    if (!cursor_cache[opt]) {
      log_error("system: SDL_CreateSystemCursor(\"%s\") failed: %s", cursor_opts[opt], SDL_GetError());
    }
  }
  SDL_SetCursor(cursor_cache[opt]);
  return 0;
}


static int f_set_window_title(lua_State *L) {
  const char *title = luaL_checkstring(L, 1);
  log_trace("system: set window title to \"%s\"", title);
  SDL_SetWindowTitle(window, title);
  return 0;
}


static const char *window_opts[] = { "normal", "maximized", "fullscreen", NULL };

static int f_set_window_mode(lua_State *L) {
  int n = luaL_checkoption(L, 1, "normal", window_opts);
  log_debug("system: set window mode to \"%s\"", window_opts[n]);
  if (n == 0) {
    SDL_RestoreWindow(window);
    SDL_SetWindowFullscreen(window, false);
  } else if (n == 1) {
    SDL_MaximizeWindow(window);
  } else {
    SDL_SetWindowFullscreen(window, true);
  }
  return 0;
}


static int f_window_has_focus(lua_State *L) {
  Uint32 flags = SDL_GetWindowFlags(window);
  lua_pushboolean(L, (flags & SDL_WINDOW_INPUT_FOCUS) != 0);
  return 1;
}


static int f_window_minimize(lua_State *L) {
  (void)L;
  window_minimize(window);
  return 0;
}


static int f_window_toggle_maximize(lua_State *L) {
  (void)L;
  window_toggle_maximize(window);
  return 0;
}


static int f_window_is_maximized(lua_State *L) {
  lua_pushboolean(L, window_is_maximized(window));
  return 1;
}

static int f_set_hit_regions(lua_State *L) {
  int titlebar_height = (int)luaL_checknumber(L, 1);
  WindowRect buttons[8];
  int n = 0;

  if (!lua_isnoneornil(L, 2)) {
    luaL_checktype(L, 2, LUA_TTABLE);
    int len = (int)lua_rawlen(L, 2);
    for (int i = 1; i <= len && n < 8; i++) {
      lua_rawgeti(L, 2, i);
      if (lua_istable(L, -1)) {
        lua_rawgeti(L, -1, 1); buttons[n].x = (int)lua_tonumber(L, -1); lua_pop(L, 1);
        lua_rawgeti(L, -1, 2); buttons[n].y = (int)lua_tonumber(L, -1); lua_pop(L, 1);
        lua_rawgeti(L, -1, 3); buttons[n].w = (int)lua_tonumber(L, -1); lua_pop(L, 1);
        lua_rawgeti(L, -1, 4); buttons[n].h = (int)lua_tonumber(L, -1); lua_pop(L, 1);
        n++;
      }
      lua_pop(L, 1);
    }
  }

  window_set_hit_regions(titlebar_height, buttons, n);
  return 0;
}

static int f_show_confirm_dialog(lua_State *L) {
  const char *title = luaL_checkstring(L, 1);
  const char *msg   = luaL_checkstring(L, 2);

#ifdef _WIN32
  int id = MessageBox(0, msg, title, MB_YESNO | MB_ICONWARNING);
  lua_pushboolean(L, id == IDYES);
#else
  SDL_MessageBoxButtonData buttons[] = {
    { SDL_MESSAGEBOX_BUTTON_RETURNKEY_DEFAULT, 1, "Yes" },
    { SDL_MESSAGEBOX_BUTTON_ESCAPEKEY_DEFAULT, 0, "No"  },
  };
  SDL_MessageBoxColorScheme scheme = {
    .colors = {
      [SDL_MESSAGEBOX_COLOR_BACKGROUND]        = { 14, 14, 14 },
      [SDL_MESSAGEBOX_COLOR_TEXT]              = { 208, 208, 208 },
      [SDL_MESSAGEBOX_COLOR_BUTTON_BORDER]     = { 58, 58, 58 },
      [SDL_MESSAGEBOX_COLOR_BUTTON_BACKGROUND] = { 26, 26, 26 },
      [SDL_MESSAGEBOX_COLOR_BUTTON_SELECTED]   = { 139, 127, 199 },
    },
  };
  SDL_MessageBoxData data = {
    .title       = title,
    .message     = msg,
    .numbuttons  = 2,
    .buttons     = buttons,
    .colorScheme = &scheme,
  };
  int buttonid = 0;
  if (!SDL_ShowMessageBox(&data, &buttonid)) {
    log_error("SDL_ShowMessageBox failed: %s", SDL_GetError());
  }
  lua_pushboolean(L, buttonid == 1);
#endif
  return 1;
}


static int f_chdir(lua_State *L) {
  const char *path = luaL_checkstring(L, 1);
#ifdef _WIN32
  if (_chdir(path) != 0) {
    log_error("system.chdir(\"%s\") failed: %s", path, strerror(errno));
    luaL_error(L, "chdir() failed: %s", strerror(errno));
  }
#else
  if (chdir(path) != 0) {
    log_error("system.chdir(\"%s\") failed: %s", path, strerror(errno));
    luaL_error(L, "chdir() failed: %s", strerror(errno));
  }
#endif
  log_info("system: working directory changed to \"%s\"", path);
  return 0;
}


static int f_list_dir(lua_State *L) {
  const char *path = luaL_checkstring(L, 1);
  DIR *dir = opendir(path);
  if (!dir) {
    lua_pushnil(L);
    lua_pushstring(L, strerror(errno));
    return 2;
  }
  lua_newtable(L);
  int i = 1;
  struct dirent *entry;
  while ((entry = readdir(dir))) {
    if (strcmp(entry->d_name, ".")  == 0) continue;
    if (strcmp(entry->d_name, "..") == 0) continue;
    lua_pushstring(L, entry->d_name);
    lua_rawseti(L, -2, i++);
  }
  closedir(dir);
  return 1;
}


static int f_absolute_path(lua_State *L) {
  const char *path = luaL_checkstring(L, 1);
  char *res = path_absolute_alloc(path);
  if (!res) return 0;
  lua_pushstring(L, res);
  cdin_free(res);
  return 1;
}


static int f_get_file_info(lua_State *L) {
  const char *path = luaL_checkstring(L, 1);
  struct stat s;
  if (stat(path, &s) < 0) {
    lua_pushnil(L);
    lua_pushstring(L, strerror(errno));
    return 2;
  }
  lua_newtable(L);
  lua_pushnumber(L, (lua_Number)s.st_mtime);
  lua_setfield(L, -2, "modified");
  lua_pushnumber(L, (lua_Number)s.st_size);
  lua_setfield(L, -2, "size");
  if      (S_ISREG(s.st_mode)) lua_pushstring(L, "file");
  else if (S_ISDIR(s.st_mode)) lua_pushstring(L, "dir");
  else                          lua_pushnil(L);
  lua_setfield(L, -2, "type");
  return 1;
}


static int f_get_clipboard(lua_State *L) {
  char *text = SDL_GetClipboardText();
  if (!text) return 0;
  lua_pushstring(L, text);
  SDL_free(text);
  return 1;
}

static int f_set_clipboard(lua_State *L) {
  SDL_SetClipboardText(luaL_checkstring(L, 1));
  return 0;
}


static int f_get_time(lua_State *L) {
  double t = (double)SDL_GetPerformanceCounter()
           / (double)SDL_GetPerformanceFrequency();
  lua_pushnumber(L, t);
  return 1;
}

static int f_sleep(lua_State *L) {
  double n = luaL_checknumber(L, 1);
  SDL_Delay((Uint32)(n * 1000));
  return 0;
}


static int f_exec(lua_State *L) {
  size_t len;
  const char *cmd = luaL_checklstring(L, 1, &len);
#ifdef _WIN32
  int wlen = MultiByteToWideChar(CP_UTF8, 0, cmd, -1, NULL, 0);
  if (wlen <= 0) {
    /* Conversion reported a length of 0 or failed outright. Both mean there is no
     * command to run, and passing an empty buffer to CreateProcess would spawn
     * something with no name — while a zero-length malloc would hand back a valid
     * pointer that looks like success. */
    luaL_error(L, "exec: the command is empty or not convertible");
    return 0;
  }
  size_t wbytes = (size_t)wlen * sizeof(wchar_t);
  wchar_t *wcmd = (wchar_t *)cdin_alloc(CDIN_MEM_PLATFORM, wbytes);
  if (!wcmd) luaL_error(L, "exec: out of memory for %zu bytes", wbytes);
  MultiByteToWideChar(CP_UTF8, 0, cmd, -1, wcmd, wlen);

  STARTUPINFOW si = { 0 };
  si.cb = sizeof(si);
  PROCESS_INFORMATION pi = { 0 };
  CreateProcessW(NULL, wcmd, NULL, NULL, FALSE,
                 DETACHED_PROCESS | CREATE_NO_WINDOW,
                 NULL, NULL, &si, &pi);
  if (pi.hProcess) CloseHandle(pi.hProcess);
  if (pi.hThread)  CloseHandle(pi.hThread);
  cdin_free(wcmd);
#else
  /* VIOLATES AGENTS.md §2.8 ("never spawn through a shell; argv arrays only").
   * `system()` hands the string to /bin/sh, so quoting, globbing and `;` all
   * behave the way the shell says rather than the way the caller wrote. It is
   * pre-existing and deliberately left alone: replacing it needs an argv array,
   * which means deciding how one command string becomes a vector — quoting rules
   * included — and that is a user-visible behaviour change. Reported in the phase
   * report under OPEN rather than silently rewritten. */
  char *buf = (char *)cdin_alloc(CDIN_MEM_PLATFORM, len + 32);
  if (!buf) luaL_error(L, "exec: out of memory");
  snprintf(buf, len + 32, "%s &", cmd);
  int r = system(buf); (void)r;
  cdin_free(buf);
#endif
  return 0;
}

static int f_fuzzy_match(lua_State *L) {
  const char *str = luaL_checkstring(L, 1);
  const char *ptn = luaL_checkstring(L, 2);
  int score;
  if (!fuzzy_match_c(str, ptn, &score)) return 0;
  lua_pushnumber(L, score);
  return 1;
}
static int f_popen(lua_State *L) {
  const char *cmd = luaL_checkstring(L, 1);

#ifdef _WIN32
  int wlen = MultiByteToWideChar(CP_UTF8, 0, cmd, -1, NULL, 0);
  if (wlen <= 0) {
    lua_pushnil(L);
    return 1;
  }
  size_t wbytes = (size_t)wlen * sizeof(wchar_t);
  wchar_t *wcmd = (wchar_t *)cdin_alloc(CDIN_MEM_PLATFORM, wbytes);
  if (!wcmd) return luaL_error(L, "popen: out of memory for %zu bytes", wbytes);
  MultiByteToWideChar(CP_UTF8, 0, cmd, -1, wcmd, wlen);

  SECURITY_ATTRIBUTES sa = { sizeof(sa), NULL, TRUE };
  HANDLE hRead, hWrite;
  if (!CreatePipe(&hRead, &hWrite, &sa, 0)) {
    cdin_free(wcmd);
    lua_pushnil(L);
    return 1;
  }
  SetHandleInformation(hRead, HANDLE_FLAG_INHERIT, 0);

  SECURITY_ATTRIBUTES sa_nul = { sizeof(sa_nul), NULL, TRUE };
  HANDLE hNul = CreateFileW(L"NUL", GENERIC_WRITE, FILE_SHARE_WRITE,
                            &sa_nul, OPEN_EXISTING, 0, NULL);

  STARTUPINFOW si = { 0 };
  si.cb          = sizeof(si);
  si.dwFlags     = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
  si.wShowWindow = SW_HIDE;
  si.hStdOutput  = hWrite;
  si.hStdError   = (hNul != INVALID_HANDLE_VALUE) ? hNul : GetStdHandle(STD_ERROR_HANDLE);
  si.hStdInput   = GetStdHandle(STD_INPUT_HANDLE);

  PROCESS_INFORMATION pi = { 0 };
  BOOL ok = CreateProcessW(
    NULL, wcmd, NULL, NULL,
    TRUE,
    CREATE_NO_WINDOW,
    NULL, NULL, &si, &pi);
  cdin_free(wcmd);
  CloseHandle(hWrite);
  if (hNul != INVALID_HANDLE_VALUE) CloseHandle(hNul);

  if (!ok) {
    CloseHandle(hRead);
    lua_pushnil(L);
    return 1;
  }

  luaL_Buffer b;
  luaL_buffinit(L, &b);
  char buf[4096];
  DWORD nread;
  while (ReadFile(hRead, buf, sizeof(buf), &nread, NULL) && nread > 0)
    luaL_addlstring(&b, buf, nread);

  CloseHandle(hRead);
  WaitForSingleObject(pi.hProcess, INFINITE);
  CloseHandle(pi.hProcess);
  CloseHandle(pi.hThread);

  luaL_pushresult(&b);
  return 1;

#else
  FILE *fp = popen(cmd, "r");
  if (!fp) { lua_pushnil(L); return 1; }

  luaL_Buffer b;
  luaL_buffinit(L, &b);
  char buf[4096];
  size_t n;
  while ((n = fread(buf, 1, sizeof(buf), fp)) > 0)
    luaL_addlstring(&b, buf, n);
  pclose(fp);

  luaL_pushresult(&b);
  return 1;
#endif
}


/* C-side memory counters, for core:memory. Deliberately a table rather than
 * several functions: one call, one consistent snapshot, and adding a counter
 * later does not change the signature of anything a caller already uses.
 * glyph_bytes and glyphsets come from the renderer, command_buf_peak from
 * the damage cache, log_size from the logger. Anything unavailable is -1
 * rather than nil, so a caller can divide or subtract without a guard.
 *
 * The per-subsystem figures come from the accounting allocator (src/base) and
 * are the numbers a phase report is built on. They are all zeros on a build
 * where nothing allocates through it yet, which is a true statement rather than
 * a missing one: a subsystem that has not been converted still uses malloc and
 * is genuinely invisible to the allocator. `tags` carries the CdinMemTag values
 * themselves, so the Lua side reports the same names the C side would print and
 * no name table has to be maintained in two languages. */

/* Pushes `n` integers as one array field on the table below it, leaving the
 * stack exactly as it found it apart from nothing.
 *
 * A helper rather than four hand-written blocks, because the stack discipline
 * here is easy to get wrong in a way that does not corrupt memory — it just
 * raises "attempt to index a number value" from inside this C function, a
 * message that reads like a Lua-side bug and sends you looking in
 * data/core/memory.lua instead of here.
 *
 * The two mistakes this shape exists to prevent, both of which were made here
 * once:
 *
 *   - lua_setfield pops exactly one value, so pushing n elements and then
 *     calling it leaves n-1 of them on the stack. After four arrays that is 40
 *     strays, and the next `lua_setfield(L, -2, ...)` lands on an integer.
 *   - with n elements pushed, the table below them is at -(n+1), not -2.
 *
 * lua_rawseti pops its value, so each element leaves the stack as it is stored,
 * and when the loop ends only the table is left for the final setfield. */
static void push_int_array(lua_State *L, const lua_Integer *vals, int n,
                           const char *key) {
  lua_createtable(L, n, 0);
  for (int i = 0; i < n; i++) {
    lua_pushinteger(L, vals[i]);
    lua_rawseti(L, -2, i + 1);   /* 1-based: index 0 is not an array slot */
  }
  lua_setfield(L, -2, key);
}

/* The same for an array of borrowed C strings. The names come from the
 * allocator rather than from a table maintained in Lua, so a subsystem cannot
 * end up reported under a name the C side does not use — and one more name is
 * added by editing one list, not two. */
static void push_str_array(lua_State *L, const char *const *vals, int n,
                           const char *key) {
  lua_createtable(L, n, 0);
  for (int i = 0; i < n; i++) {
    lua_pushstring(L, vals[i] ? vals[i] : "");
    lua_rawseti(L, -2, i + 1);
  }
  lua_setfield(L, -2, key);
}

static int f_memory_stats(lua_State *L) {
  int draw_text = 0, draw_rect = 0, buf_peak = 0;
  rencache_get_stats(&draw_text, &draw_rect, &buf_peak);

  enum { TAGS = (int)CDIN_MEM_COUNT };

  /* Collected into C arrays before anything is pushed, so the stack discipline
   * above is checkable by eye: nothing is read from Lua while the stack is
   * mid-construction. */
  lua_Integer tags[TAGS], live[TAGS], peak[TAGS], blocks[TAGS];
  const char *names[TAGS];
  for (int i = 0; i < TAGS; i++) {
    CdinMemTag tag = (CdinMemTag)i;
    tags[i]   = (lua_Integer)i;
    names[i]  = cdin_mem_tag_name(tag);
    live[i]   = (lua_Integer)cdin_mem_live(tag);
    peak[i]   = (lua_Integer)cdin_mem_peak(tag);
    blocks[i] = (lua_Integer)cdin_mem_alloc_count(tag);
  }

  lua_newtable(L);

  lua_pushinteger(L, (lua_Integer)ren_glyph_bytes());
  lua_setfield(L, -2, "glyph_bytes");

  lua_pushinteger(L, (lua_Integer)ren_glyphset_count());
  lua_setfield(L, -2, "glyph_pages");

  lua_pushinteger(L, (lua_Integer)log_get_file_size());
  lua_setfield(L, -2, "log_bytes");

  lua_pushinteger(L, (lua_Integer)buf_peak);
  lua_setfield(L, -2, "command_buf_peak");

  lua_pushinteger(L, (lua_Integer)COMMAND_BUF_SIZE);
  lua_setfield(L, -2, "command_buf_capacity");

  lua_pushinteger(L, (lua_Integer)draw_text);
  lua_setfield(L, -2, "draw_text_count");

  lua_pushinteger(L, (lua_Integer)draw_rect);
  lua_setfield(L, -2, "draw_rect_count");

  /* Five parallel arrays of the same length — names, tags, and three counters —
   * rather than a table keyed by name: the Lua side only ever walks them in
   * order, and this keeps the per-subsystem report free of any table
   * allocation, which the reporting path must not do. `tags` carries the
   * CdinMemTag values so a caller can zip an index back to the allocator. */
  push_str_array(L, names,  TAGS, "names");
  push_int_array(L, tags,   TAGS, "tags");
  push_int_array(L, live,   TAGS, "alloc_by");
  push_int_array(L, peak,   TAGS, "peak_by");
  push_int_array(L, blocks, TAGS, "blocks_by");

  lua_pushinteger(L, (lua_Integer)cdin_mem_total_live());
  lua_setfield(L, -2, "alloc_total");

  lua_pushinteger(L, (lua_Integer)cdin_mem_total_peak());
  lua_setfield(L, -2, "peak_total");

  /* The leak count, not the leak report: the report prints to the log, and a
   * `core:memory` call must not write to the log. main() prints the full report
   * once at exit, where it belongs. */
  lua_pushinteger(L, (lua_Integer)cdin_mem_live_blocks());
  lua_setfield(L, -2, "live_blocks");

  lua_pushinteger(L, cdin_mem_debug_enabled() ? 1 : 0);
  lua_setfield(L, -2, "accounted");

  return 1;
}


/* ── fault injection, reachable from Lua ──────────────────────────────────
 *
 * The allocator can already be armed from C, and from CDIN_ALLOC_FAIL_AFTER in
 * the environment, but neither can reach the code this exists for.
 *
 * Arming at startup spends the injector on Lua's own allocations: the bundled
 * cdin-x panel raises a Lua error during the first frames, and the process ends
 * before a single glyph page is baked, so the renderer is never asked for
 * memory. Arming from a user init.lua instead lands it after the editor has
 * booted, so what is refused is the per-frame glyph and image work — the only
 * allocations where running out of memory used to end the process.
 *
 * This is test tooling with a real use: "what does the editor do when memory
 * runs out while drawing" is a question a reviewer asks, and without a way to
 * ask it in the running program the answer can only be argued. */

static int f_alloc_fail_after(lua_State *L) {
  lua_Integer n = (lua_Integer)luaL_checknumber(L, 1);
  if (n < 0) {
    /* Negative would arm a count that never decrements toward zero and so
     * refuses everything from the first call — reachable by accident, and
     * indistinguishable from passing 0. Refused rather than coerced. */
    cdin_error_raise(L, CDIN_ERR(CDIN_ERR_INVALID), "n");
    return 0;
  }
  cdin_alloc_fail_after((unsigned long)n);
  log_warn("system.alloc_fail_after(%d): every allocation after the next %d is "
           "refused", (int)n, (int)n);
  return 0;
}

static int f_alloc_failures(lua_State *L) {
  lua_pushinteger(L, (lua_Integer)cdin_alloc_failures());
  return 1;
}

static int f_alloc_fail_disable(lua_State *L) {
  cdin_alloc_fail_disable();
  return 0;
}

/* ── the libuv job loop, as the frame sees it ──────────────────────────────
 *
 * The frame owns the pump. SDL3 keeps the window, input and rendering, and this
 * is the only place the two asynchronous worlds meet: once per frame, dispatch
 * whatever libuv has ready and return.
 *
 * It is a single C call rather than something Lua schedules, because a job's
 * completion callback may fire while the Lua stack is mid-frame — a callback that
 * ran at an arbitrary point in Lua's execution would re-enter it. Dispatching
 * here means completions arrive at one predictable point in the frame instead.
 */

static int f_jobs_run(lua_State *L) {
  (void)L;
  /* Returns nothing: the interesting result is the callbacks this fires, and
   * those are delivered to whatever asked for them. A number here would be a
   * count of completions that the caller cannot act on. */
  job_loop_run_once();
  return 0;
}

static int f_jobs_pending(lua_State *L) {
  lua_pushinteger(L, (lua_Integer)job_pending());
  return 1;
}

static const luaL_Reg lib[] = {
  { "poll_event",            f_poll_event            },
  { "wait_event",            f_wait_event            },
  { "set_cursor",            f_set_cursor            },
  { "set_window_title",      f_set_window_title      },
  { "set_window_mode",       f_set_window_mode       },
  { "window_has_focus",      f_window_has_focus      },
  { "window_minimize",       f_window_minimize       },
  { "window_toggle_maximize",f_window_toggle_maximize},
  { "window_is_maximized",   f_window_is_maximized   },
  { "set_hit_regions",       f_set_hit_regions       },
  { "show_confirm_dialog",   f_show_confirm_dialog   },
  { "chdir",                 f_chdir                 },
  { "list_dir",              f_list_dir              },
  { "absolute_path",         f_absolute_path         },
  { "get_file_info",         f_get_file_info         },
  { "get_clipboard",         f_get_clipboard         },
  { "set_clipboard",         f_set_clipboard         },
  { "get_time",              f_get_time              },
  { "sleep",                 f_sleep                 },
  { "exec",                  f_exec                  },
  { "popen",                 f_popen                 },
  { "fuzzy_match",           f_fuzzy_match           },
  { "memory_stats",          f_memory_stats          },
  { "alloc_fail_after",      f_alloc_fail_after      },
  { "alloc_failures",        f_alloc_failures        },
  { "alloc_fail_disable",    f_alloc_fail_disable    },
  { "jobs_run",              f_jobs_run              },
  { "jobs_pending",          f_jobs_pending          },
  { NULL, NULL }
};

int luaopen_system(lua_State *L) {
  luaL_newlib(L, lib);
  return 1;
}
