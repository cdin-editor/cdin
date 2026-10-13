#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#include <SDL3/SDL.h>
#include <lua.h>
#include <lauxlib.h>
#include <lualib.h>

#include "api/api.h"
#include "core/window.h"
#include "lua/api.h"
#include "core/logger.h"
#include "base/alloc.h"
#include "loop/loop.h"
#include "platform/platform.h"
#include "ui/renderer.h"

SDL_Window *window;

/* A log that grows forever is not a log, it is a leak with a .log suffix.
 * Past this size the previous run is kept as cdin-log.txt.1 and the new one
 * starts empty, so a crash report is one file rather than a directory. */
#define CDIN_LOG_MAX_BYTES (4L * 1024L * 1024L)


/* "trace" | "debug" | "info" | "warn" | "error" | "fatal", else the fallback. */
static int level_from_env(const char *name, int fallback) {
  const char *v = getenv(name);
  if (!v || !*v) return fallback;

  struct { const char *name; int level; } table[] = {
    { "trace", LOG_TRACE }, { "debug", LOG_DEBUG }, { "info",  LOG_INFO  },
    { "warn",  LOG_WARN  }, { "error", LOG_ERROR }, { "fatal", LOG_FATAL },
  };
  for (size_t i = 0; i < sizeof(table) / sizeof(table[0]); i++) {
    if (strcmp(v, table[i].name) == 0) return table[i].level;
  }
  return fallback;
}


static long file_size(const char *path) {
  struct stat st;
  if (stat(path, &st) != 0) return -1;
  return (long)st.st_size;
}


/* Keeps one previous run, then starts over. Renaming over an existing
 * destination fails on some platforms, so the old one is unlinked first. */
static void rotate_log(const char *path) {
  if (file_size(path) < CDIN_LOG_MAX_BYTES) return;

  char prev[2100];
  snprintf(prev, sizeof(prev), "%s.1", path);
  remove(prev);
  if (rename(path, prev) != 0) remove(path);
}


static FILE *setup_logging(const char *exefile) {
  /* stderr is the console, so it stays at INFO unless asked otherwise.
   * The file is the record: it defaults to DEBUG because the per-frame
   * renderer traces are noise in a log nobody can read, and a boot that
   * fails after the console closed still needs to be readable. */
  log_set_level(level_from_env("CDIN_LOG_LEVEL", LOG_INFO));

  char log_path[2080];
  const char *custom = getenv("CDIN_LOG_FILE");
  if (custom && *custom) {
    snprintf(log_path, sizeof(log_path), "%s", custom);
  } else {
    char dir[2048];
    strncpy(dir, exefile, sizeof(dir) - 1);
    dir[sizeof(dir) - 1] = '\0';

    char *slash = strrchr(dir, '/');
#ifdef _WIN32
    char *bslash = strrchr(dir, '\\');
    if (!slash || (bslash && bslash > slash)) slash = bslash;
#endif
    if (slash) *slash = '\0';
    else dir[0] = '\0';

    snprintf(log_path, sizeof(log_path), "%s%s%s", dir, dir[0] ? "/" : "",
             dir[0] ? "cdin-log.txt" : "./cdin-log.txt");
  }

  rotate_log(log_path);

  FILE *fp = fopen(log_path, "a");
  if (fp) {
    log_set_path(log_path);
    log_add_fp(fp, level_from_env("CDIN_LOG_FILE_LEVEL", LOG_DEBUG));
  } else {
    log_warn("could not open %s for writing, file logging disabled", log_path);
  }
  return fp;
}


int main(int argc, char **argv) {
  char exefile[2048] = {0};
  plat_exe_filename(exefile, sizeof(exefile));
  FILE *log_fp = setup_logging(exefile);
  log_info("cdin starting");

  /* CDIN_ALLOC_FAIL_AFTER=<n> arms the allocator to allow n allocations and
   * refuse every one after.
   *
   * Arming here refuses allocations from the very first call, which is the
   * "out of memory immediately" case and stays reachable only because disarming
   * is a separate call rather than a magic n.
   *
   * The value is the count from the first allocation, so this is useful for the
   * load path and for proving the injector works at all. It does NOT reach the
   * draw path usefully: the bundled cdin-x panel raises a Lua error in the
   * first frames, which ends the process before any glyph page is baked, so
   * what gets refused is Lua's own allocation and the renderer is never asked.
   * To exercise the draw path, arm it from a user init.lua instead — see
   * system.alloc_fail_after(), which is what the OOM checks use. */
  {
    const char *fail_after = getenv("CDIN_ALLOC_FAIL_AFTER");
    if (fail_after && *fail_after) {
      char *end = NULL;
      unsigned long n = strtoul(fail_after, &end, 10);
      if (end && *end == '\0') {
        cdin_alloc_fail_after(n);
        log_warn("main: fault injection armed - %lu allocations allowed, every "
                 "allocation after that refused", n);
      } else {
        log_warn("main: CDIN_ALLOC_FAIL_AFTER=\"%s\" is not a number, ignoring",
                 fail_after);
      }
    }
  }

  plat_early_init();

  if (!SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS)) {
    log_fatal("SDL_Init failed: %s", SDL_GetError());
    if (log_fp) fclose(log_fp);
    return EXIT_FAILURE;
  }
  SDL_SetHint("SDL_MOUSE_FOCUS_CLICKTHROUGH", "1");
  atexit(SDL_Quit);
  SDL_DisplayID display = SDL_GetPrimaryDisplay();
  SDL_Rect usable = {0};
  int win_w, win_h;
  if (SDL_GetDisplayUsableBounds(display, &usable) && usable.w > 0) {
    win_w = (int)(usable.w * 0.8f);
    win_h = (int)(usable.h * 0.8f);
  } else {
    const SDL_DisplayMode *dm = SDL_GetCurrentDisplayMode(display);
    float dscale = SDL_GetDisplayContentScale(display);
    if (dscale < 0.5f) dscale = 1.0f;
    win_w = dm ? (int)(dm->w * 0.8f / dscale) : 1280;
    win_h = dm ? (int)(dm->h * 0.8f / dscale) : 800;
  }

  window = window_create(win_w, win_h);
  if (!window) {
    log_fatal("window_create failed, exiting");
    if (log_fp) fclose(log_fp);
    return EXIT_FAILURE;
  }
  window_set_icon(window);

  SDL_StartTextInput(window);

  ren_init(window);

  double scale = plat_display_scale();

  lua_State *L = luaL_newstate();
  if (!L) {
    log_fatal("failed to create Lua state");
    SDL_DestroyWindow(window);
    if (log_fp) fclose(log_fp);
    return EXIT_FAILURE;
  }
  luaL_openlibs(L);
  api_load_libs(L);

  lua_setup_globals(L, argc, argv, scale, exefile);

  /* The libuv loop, created before core.init() so that anything the Lua side
   * does during boot can already queue a job.
   *
   * Created here rather than lazily because a lazily-created loop has no
   * contract: the first caller would pay for uv_loop_init on whatever frame
   * happened to need it, which is the frame that was already busy. Failing to
   * create it is not fatal — SDL3 owns the window, input and rendering, and
   * none of them need libuv — so a failure is logged and the editor continues
   * with every synchronous path intact.
   */
  if (job_loop_init() != 0) {
    log_warn("main: libuv loop unavailable — file I/O stays on the frame thread");
  }

  lua_run_core(L);
  log_info("cdin shutting down cleanly");

  /* Closed after Lua, because a completion callback marshals bytes for the Lua
   * side and must not outlive it. Anything still in flight is abandoned by
   * design — see job_loop_close — and at this point nothing is waiting for it. */
  job_loop_close();

  lua_close(L);
  SDL_DestroyWindow(window);
  if (log_fp) fclose(log_fp);
  return EXIT_SUCCESS;
}