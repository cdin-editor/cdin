/* The platform layer. See platform.h for what this file is and why it is the
 * only one.
 *
 * The split below is per operating system, and each branch is the real API for
 * that system rather than a wrapper over something portable — the one exception
 * is the display scale, where SDL already does the work on every platform and
 * asking the OS directly would be strictly worse.
 */

#include "platform.h"

#include <SDL3/SDL.h>
#include <stdio.h>
#include <string.h>

#include "../core/logger.h"

#ifdef _WIN32
  #include <windows.h>
#elif defined(__linux__)
  #include <unistd.h>
#elif defined(__APPLE__)
  #include <mach-o/dyld.h>
#endif

void plat_early_init(void) {
#ifdef _WIN32
  /* SetProcessDPIAware has to be called before the first window exists, which is
   * why this is a separate entry point rather than part of window creation.
   *
   * Resolved by hand rather than by linking against user32 so that a build which
   * does not link user32 still runs: an editor that cannot set DPI awareness
   * should look slightly wrong, not fail to start. */
  log_debug("plat: requesting Windows DPI awareness");
  HINSTANCE lib = LoadLibrary("user32.dll");
  if (!lib) {
    log_warn("plat: could not load user32.dll; the window may be bitmap-scaled");
    return;
  }
  typedef int (*DPIAwareFunc)(void);
  /* The cast through void* is required by the C standard when a function
   * pointer is round-tripped through an object pointer; GetProcAddress is
   * declared to return FARPROC for exactly this reason. */
  DPIAwareFunc fn = (DPIAwareFunc)(void *)GetProcAddress(lib,
                                                         "SetProcessDPIAware");
  if (fn) {
    fn();
    log_debug("plat: SetProcessDPIAware() called");
  } else {
    log_warn("plat: SetProcessDPIAware not found in user32.dll");
  }
  FreeLibrary(lib);
#else
  /* SDL3 handles awareness on every other platform, so there is genuinely
   * nothing to do. Said at trace level so the line is there when someone reads
   * the log wondering why this function is empty on Linux. */
  log_trace("plat: nothing to set up before SDL on this platform");
#endif
}

int plat_exe_filename(char *buf, int size) {
  if (!buf || size <= 1) return 0;
  int ok = 0;

#ifdef _WIN32
  /* size - 1, then the terminator below. GetModuleFileNameA truncates rather than
   * failing when the buffer is too small, and does not always terminate on
   * truncation, so the length it returns is what decides the terminator's
   * position. */
  int len = GetModuleFileNameA(NULL, buf, size - 1);
  if (len <= 0) {
    log_warn("plat: GetModuleFileNameA failed; the exe path is unknown");
    len = 0;
  } else {
    ok = 1;
  }
  buf[(len < size) ? len : size - 1] = '\0';

#elif defined(__linux__)
  /* /proc/self/exe rather than building "/proc/<pid>/exe": it is one readlink, it
   * cannot be wrong about the pid, and it resolves symlinks, so an editor
   * reached through a link reports where the binary really is. */
  int len = (int)readlink("/proc/self/exe", buf, (size_t)size - 1);
  if (len < 0) {
    log_warn("plat: readlink(/proc/self/exe) failed; the exe path is unknown");
    len = 0;
  } else {
    ok = 1;
  }
  buf[(len < size) ? len : size - 1] = '\0';

#elif defined(__APPLE__)
  uint32_t sz = (uint32_t)size;
  if (_NSGetExecutablePath(buf, &sz) != 0) {
    log_warn("plat: _NSGetExecutablePath needs a buffer of %u bytes, have %d; "
             "the exe path is unknown", (unsigned)sz, size);
    buf[0] = '\0';
  } else if (realpath(buf, buf) == NULL) {
    /* _NSGetExecutablePath can return a path containing symlinks or "..", and
     * resolving it in place is safe here because realpath writes only when it
     * succeeds and buf is already NUL-terminated. */
    log_warn("plat: realpath failed on the exe path; using it unresolved");
    ok = 1;
  } else {
    ok = 1;
  }

#else
  log_warn("plat: unrecognised platform; assuming ./cdin");
#endif

  /* A usable string even on failure, so a caller that ignores the return value
   * has something it can open rather than an uninitialised buffer. */
  if (buf[0] == '\0') {
    snprintf(buf, (size_t)size, "./cdin");
    return 0;
  }

  log_debug("plat: exe filename resolved to \"%s\"", buf);
  return ok;
}

double plat_display_scale(void) {
  /* SDL, on every platform — including Windows.
   *
   * This used to be inside #ifdef _WIN32 with a `return 1.0` for everything
   * else, on the reasoning that "non-Windows means Unix means no scaling". That
   * was wrong: SDL_GetDisplayContentScale is cross-platform, so the guard was
   * excluding Linux and macOS from a value SDL was ready to give them. On a HiDPI
   * display that made the editor render at 1x into a 2x framebuffer, which looks
   * soft, and it made the SCALE in the log lie.
   *
   * The guard that does matter is the return value. SDL reports failure by
   * returning 0.0, and a 0 scale scales every coordinate to zero: an empty
   * window, no error, no clue. So anything below a plausible floor is treated as
   * "could not tell" and answered with 1.0.
   *
   * The floor is 0.5, not 1.0: a display genuinely can report 0.75 (Windows
   * 125% scaling), and clamping that to 1.0 would be wrong. */
  SDL_DisplayID display = SDL_GetPrimaryDisplay();
  if (display == 0) {
    log_warn("plat: no primary display; assuming a scale of 1.0");
    return 1.0;
  }

  double scale = (double)SDL_GetDisplayContentScale(display);
  if (!(scale >= 0.5)) {
    /* Written as !(scale >= 0.5) rather than scale < 0.5 so that a NaN — which
     * compares false against everything — takes this branch too. */
    log_warn("plat: display content scale came back as %f; assuming 1.0", scale);
    return 1.0;
  }

  log_debug("plat: display content scale = %.2f", scale);
  return scale;
}