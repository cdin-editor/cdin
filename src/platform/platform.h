/* The platform layer: the three questions only the operating system can answer.
 *
 *   plat_early_init      anything that must happen before SDL starts
 *   plat_exe_filename    where this binary is, which is how data/ is found
 *   plat_display_scale   the display's content scale, which is SCALE in the log
 *
 * Why these three and nothing else: they are the only places in the runtime that
 * branch on the operating system for a reason SDL cannot paper over. Everything
 * else — windows, surfaces, events, timers, threads — goes through SDL and is
 * already one code path. A module that contains an OS guard is a module whose
 * behaviour differs per platform; the cheapest way to keep that contained is to
 * have as few modules with an OS guard as possible, and to name them here.
 *
 * This file is the one place a new operating system has to be taught. Before it
 * existed, `utils.c` and `boot.c` each carried their own #ifdef _WIN32, and the
 * display-scale branch was Windows-only even though SDL_GetDisplayContentScale is
 * cross-platform — so on Linux and macOS SCALE was a hardcoded 1.0 and HiDPI
 * displays got a bitmap-scaled window. See plat_display_scale.
 *
 * Ownership: stateless. No globals, no locks, nothing to free. Every function may
 * be called before or after the logger is up; plat_early_init is the exception
 * and logs at trace level for that reason, because there is no logger yet when it
 * runs first — see main.c, which initialises the logger before calling it.
 *
 * Threads: safe to call from any thread. Nothing here holds state between calls.
 */

#ifndef CDIN_PLATFORM_PLATFORM_H
#define CDIN_PLATFORM_PLATFORM_H

/* Windowing and HiDPI awareness that must be set before SDL initialises.
 *
 * A no-op where the OS needs nothing. Called once, early, from main(). */
void plat_early_init(void);

/* Writes this executable's absolute path into `buf`, NUL-terminated, and
 * returns 1 on success or 0 on failure.
 *
 * Returns a status rather than only filling the buffer because "could not find
 * out where I am" is a different situation from "found out, and it is ./cdin" —
 * the first is worth a warning in the log, the second is a normal relative
 * launch. Callers use the path to find data/ beside the binary.
 *
 * On failure `buf` is set to a usable fallback ("./cdin") rather than left
 * untouched, so a caller that ignores the return value still has a string it can
 * open. */
int plat_exe_filename(char *buf, int size);

/* The display's content scale: 1.0 on a standard-density display, 2.0 on a
 * typical HiDPI one.
 *
 * Real on every platform, which is the point of this function existing in one
 * place. Never returns 0: a zero scale would scale every coordinate to zero and
 * make the window look empty, and SDL reports failure by returning 0.0, so the
 * guard is not theoretical. */
double plat_display_scale(void);

#endif /* CDIN_PLATFORM_PLATFORM_H */