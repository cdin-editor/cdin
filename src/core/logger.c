#include "logger.h"
#include <string.h>
#include <stdio.h>

#define MAX_CALLBACKS 32

typedef struct {
  log_LogFn fn;
  void *udata;
  int level;
} Callback;

/* The file log's state: the stream, the path it came from (so the callback can
 * rotate it when it passes the cap mid-session, not only at startup), and its
 * current size.
 *
 * Module-owned, not per-callback: exactly one file log exists, and the logger
 * owns the handle. main.c used to open the file, hand the FILE* over and close
 * it itself, which left rotation impossible (a rotated stream has to be
 * closed, renamed and reopened by whoever holds it) and made the handle's
 * lifetime the caller's problem. */
static struct {
  FILE *fp;
  char  path[2048];
  long  size;
} file_log;

static struct {
  void        *udata;
  log_LockFn   lock;
  int          level;
  bool         quiet;
  char         path[2048];
  Callback     callbacks[MAX_CALLBACKS];
} L;

/* Which callback slot holds file_callback, or -1. Not inside L, because L is
 * zero-initialised and zero is a valid slot index — a sentinel that starts
 * life looking like a real slot is how "is a file log installed?" gets the
 * wrong answer on the first call. */
#define FILE_SLOT_NONE (-1)
static int file_slot = FILE_SLOT_NONE;


static const char *level_strings[] = {
  "TRACE", "DEBUG", "INFO ", "WARN ", "ERROR", "FATAL"
};

#ifdef LOG_USE_COLOR
static const char *level_colors[] = {
  "\x1b[90m",   /* TRACE — dark grey   */
  "\x1b[36m",   /* DEBUG — cyan        */
  "\x1b[32m",   /* INFO  — green       */
  "\x1b[33m",   /* WARN  — yellow      */
  "\x1b[31m",   /* ERROR — red         */
  "\x1b[35m",   /* FATAL — magenta     */
};
#endif


static void stderr_callback(log_Event *ev) {
  char tbuf[16];
  tbuf[strftime(tbuf, sizeof(tbuf), "%H:%M:%S", ev->time)] = '\0';

  const char *file = strrchr(ev->file, '/');
  file = file ? file + 1 : ev->file;
#ifdef _WIN32
  const char *file2 = strrchr(file, '\\');
  if (file2) file = file2 + 1;
#endif

#ifdef LOG_USE_COLOR
  fprintf(ev->udata,
    "%s %s%-5s\x1b[0m \x1b[90m%-18s:%3d\x1b[0m  ",
    tbuf,
    level_colors[ev->level],
    level_strings[ev->level],
    file,
    ev->line);
#else
  fprintf(ev->udata,
    "%s %-5s %-18s:%3d  ",
    tbuf,
    level_strings[ev->level],
    file,
    ev->line);
#endif
  vfprintf(ev->udata, ev->fmt, ev->ap);
  fprintf(ev->udata, "\n");
  fflush(ev->udata);
}


/* A log that grows forever is not a log, it is a leak with a .log suffix.
 * Past this size the previous run is kept as cdin-log.txt.1 and the new one
 * starts empty, so a crash report is one file rather than a directory.
 * Mirrors CDIN_LOG_MAX_BYTES in main.c, which owns the startup rotation. */
#define LOG_MAX_BYTES (4L * 1024L * 1024L)


static void file_callback(log_Event *ev) {
  (void)ev;
  FILE *fp = file_log.fp;
  if (!fp) return;

  /* Rotate during the session, not only at startup. __gc-driven font frees
   * and a trace-level draw loop can push a long run past the cap while it
   * is still the live log, and the whole point of the cap is that a crash
   * report is one file a person can read. Rotation is silent by design: it
   * runs inside a callback with the log lock held, so anything that
   * re-enters the logger would recurse. */
  if (file_log.size >= LOG_MAX_BYTES) {
    /* Close before renaming. Windows refuses to rename an open file, so a
     * rename-first rotation fails there and the log silently keeps growing —
     * the exact behaviour this is meant to prevent, on the one platform where
     * it is easiest to hit. */
    fclose(fp);
    file_log.fp = NULL;

    char prev[2100];
    int  n = snprintf(prev, sizeof(prev), "%s.1", file_log.path);
    if (n > 0 && (size_t)n < sizeof(prev)) {
      remove(prev);
      rename(file_log.path, prev);
    }

    fp = fopen(file_log.path, "a");
    if (fp) {
      file_log.fp   = fp;
      file_log.size = 0;
    } else {
      /* The log is gone and cannot be reopened. Stop trying rather than
       * writing to a stream of unknown validity; stderr still works. */
      file_log.size = 0;
      return;
    }
  }

  char tbuf[32];
  tbuf[strftime(tbuf, sizeof(tbuf), "%Y-%m-%d %H:%M:%S", ev->time)] = '\0';

  const char *file = strrchr(ev->file, '/');
  file = file ? file + 1 : ev->file;

  int start = ftell(fp);
  fprintf(fp,
    "%s %-5s %-22s:%3d  ",
    tbuf,
    level_strings[ev->level],
    file,
    ev->line);
  vfprintf(fp, ev->fmt, ev->ap);
  fprintf(fp, "\n");
  fflush(fp);

  int end = ftell(fp);
  if (start >= 0 && end >= start) {
    file_log.size = (file_log.size - start) + end;
  } else {
    /* ftell is unavailable on some streams; fall back to counting bytes
     * written from now on rather than losing the cap entirely. */
    file_log.size += (long)(end >= 0 ? end : 0);
  }
}


static void do_lock(void)   { if (L.lock) L.lock(true,  L.udata); }
static void do_unlock(void) { if (L.lock) L.lock(false, L.udata); }


const char *log_level_string(int level) {
  return level_strings[level];
}

void log_set_lock(log_LockFn fn, void *udata) {
  L.lock  = fn;
  L.udata = udata;
}

void log_set_level(int level) { L.level = level; }
void log_set_quiet(bool enable) { L.quiet = enable; }

const char *log_get_path(void) { return L.path[0] ? L.path : NULL; }

void log_set_path(const char *path) {
  if (!path) { L.path[0] = '\0'; return; }
  strncpy(L.path, path, sizeof(L.path) - 1);
  L.path[sizeof(L.path) - 1] = '\0';
}

int log_add_callback(log_LogFn fn, void *udata, int level) {
  for (int i = 0; i < MAX_CALLBACKS; i++) {
    if (!L.callbacks[i].fn) {
      L.callbacks[i] = (Callback){ fn, udata, level };
      return 0;
    }
  }
  return -1; /* no free slot */
}

int log_add_fp(FILE *fp, int level) {
  /* One file log, and the logger owns the handle: a second call replaces the
   * first, closing the previous stream. That is what makes the tests able to
   * point the log at a fresh file per case, and it is also the only shape in
   * which rotation works — a rotated stream has to be reopened by whoever
   * holds it. */
  if (file_slot != FILE_SLOT_NONE) {
    if (file_log.fp) { fclose(file_log.fp); file_log.fp = NULL; }
    L.callbacks[file_slot].fn = NULL;
    file_slot = FILE_SLOT_NONE;
  }

  file_log.fp   = fp;
  file_log.size = ftell(fp);
  if (file_log.size < 0) file_log.size = 0;
  /* L.path is set before this is called by main(); the size cap is checked
   * per write, so the path is all that rotation needs. */
  snprintf(file_log.path, sizeof(file_log.path), "%s", L.path);

  if (log_add_callback(file_callback, NULL, level) != 0) return -1;
  for (int i = 0; i < MAX_CALLBACKS; i++) {
    if (L.callbacks[i].fn == file_callback) { file_slot = i; break; }
  }
  return 0;
}


long log_get_file_size(void) {
  return file_log.fp ? file_log.size : -1;
}


static void init_event(log_Event *ev, void *udata) {
  if (!ev->time) {
    time_t t = time(NULL);
    ev->time = localtime(&t);
  }
  ev->udata = udata;
}


void log_log(int level, const char *file, int line, const char *fmt, ...) {
  log_Event ev = {
    .fmt   = fmt,
    .file  = file,
    .line  = line,
    .level = level,
  };

  do_lock();

  if (!L.quiet && level >= L.level) {
    init_event(&ev, stderr);
    va_start(ev.ap, fmt);
    stderr_callback(&ev);
    va_end(ev.ap);
  }

  for (int i = 0; i < MAX_CALLBACKS && L.callbacks[i].fn; i++) {
    Callback *cb = &L.callbacks[i];
    if (level >= cb->level) {
      init_event(&ev, cb->udata);
      va_start(ev.ap, fmt);
      cb->fn(&ev);
      va_end(ev.ap);
    }
  }

  do_unlock();
}
