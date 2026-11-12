#if !defined(_WIN32)
#define _POSIX_C_SOURCE 200809L
#define _XOPEN_SOURCE 700
#endif
/*
 * Implements ARCH-001 and ROOT-001: assemble components without reimplementing
 * their editor-domain behavior.
 * https://github.com/cdin-editor/spec/blob/main/docs/architecture/overview.md#L113-L113
 * https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md#L22-L22
 */
#include "cdin/backend.h"
#include "cdin/log.h"
#include "cdin/options.h"
#include "cdin/frontend/core/protocol/wire.h"
#include "integration/frontend_smoke.h"
#ifdef CDIN_ENABLE_GUI_SDL
#include "cdin/frontend/ui/gui_sdl/gui_sdl.h"
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#endif

#if CDIN_BACKEND_PROTOCOL_MAJOR != CDIN_FRONTEND_PROTOCOL_VERSION_MAJOR
#error "Backend and Frontend protocol major versions differ"
#endif
#if CDIN_BACKEND_PROTOCOL_MINOR != CDIN_FRONTEND_PROTOCOL_VERSION_MINOR
#error "Backend and Frontend protocol minor versions differ"
#endif

#ifndef CDIN_VERSION
#define CDIN_VERSION "0.2.0"
#endif
#ifndef CDIN_DEFAULT_RUNTIME_ROOT
#define CDIN_DEFAULT_RUNTIME_ROOT "./lua"
#endif

#define CDIN_EXECUTABLE_PATH_CAPACITY 4096u

static int resolve_executable_path(
    const char *argv0, char *resolved, size_t capacity)
{
#ifdef _WIN32
    DWORD length;
    if (capacity == 0u || capacity > (size_t)UINT32_MAX) return 0;
    length = GetModuleFileNameA(NULL, resolved, (DWORD)capacity);
    return length != 0u && (size_t)length < capacity;
#else
    const char *path;
    const char *segment;
    char candidate[CDIN_EXECUTABLE_PATH_CAPACITY];
    if (argv0 == NULL || argv0[0] == '\0' || resolved == NULL || capacity == 0u)
        return 0;
    if (strchr(argv0, '/') != NULL)
        return realpath(argv0, resolved) != NULL;

    path = getenv("PATH");
    if (path == NULL) return realpath(argv0, resolved) != NULL;
    segment = path;
    for (;;) {
        const char *separator = strchr(segment, ':');
        size_t length = separator != NULL
            ? (size_t)(separator - segment) : strlen(segment);
        int written;
        if (length == 0u) {
            written = snprintf(candidate, sizeof(candidate), "./%s", argv0);
        } else if (length < (size_t)INT_MAX) {
            written = snprintf(candidate, sizeof(candidate), "%.*s/%s",
                               (int)length, segment, argv0);
        } else {
            return 0;
        }
        if (written > 0 && (size_t)written < sizeof(candidate) &&
            access(candidate, X_OK) == 0 &&
            realpath(candidate, resolved) != NULL) {
            return 1;
        }
        if (separator == NULL) break;
        segment = separator + 1;
    }
    return 0;
#endif
}

static char *last_path_separator(char *path)
{
    char *separator = strrchr(path, '/');
#ifdef _WIN32
    char *backslash = strrchr(path, '\\');
    if (backslash != NULL && (separator == NULL || backslash > separator))
        separator = backslash;
#endif
    return separator;
}

/*
 * A relocatable installation contains:
 *   bin/cdin
 *   share/cdin/lua/cdin/runtime.lua
 *
 * Resolve that layout relative to the actual executable before falling back
 * to the build-time CMake prefix. Explicit --runtime-root and CDIN_RUNTIME_ROOT
 * remain higher-priority overrides.
 */
static const char *discover_bundled_runtime_root(
    const char *argv0, char *storage, size_t capacity)
{
    char executable[CDIN_EXECUTABLE_PATH_CAPACITY];
    char marker[CDIN_EXECUTABLE_PATH_CAPACITY];
    char *separator;
    struct stat metadata;
    int written;

    if (!resolve_executable_path(argv0, executable, sizeof(executable)))
        return NULL;
    separator = last_path_separator(executable);
    if (separator == NULL) return NULL;
    *separator = '\0';
    separator = last_path_separator(executable);
    if (separator == NULL) return NULL;
#ifdef _WIN32
    if (_stricmp(separator + 1, "bin") != 0) return NULL;
#else
    if (strcmp(separator + 1, "bin") != 0) return NULL;
#endif
    *separator = '\0';
#ifdef _WIN32
    written = snprintf(storage, capacity, "%s\\share\\cdin\\lua", executable);
    if (written <= 0 || (size_t)written >= capacity) return NULL;
    written = snprintf(marker, sizeof(marker), "%s\\cdin\\runtime.lua", storage);
#else
    written = snprintf(storage, capacity, "%s/share/cdin/lua", executable);
    if (written <= 0 || (size_t)written >= capacity) return NULL;
    written = snprintf(marker, sizeof(marker), "%s/cdin/runtime.lua", storage);
#endif
    if (written <= 0 || (size_t)written >= sizeof(marker) ||
        stat(marker, &metadata) != 0 || !S_ISREG(metadata.st_mode)) {
        return NULL;
    }
    return storage;
}

static int run_check(const cdin_options *options, cdin_log *log, const char *argv0)
{
    cdin_backend_config config;
    cdin_backend *backend = NULL;
    cdin_backend_status status;
    size_t processed = 0u;
    size_t loaded_extensions = 0u;
    int result = EXIT_FAILURE;
    char bundled_runtime_root[CDIN_EXECUTABLE_PATH_CAPACITY];
    const char *runtime_root = options->runtime_root;
    if (runtime_root == NULL || runtime_root[0] == '\0') runtime_root = getenv("CDIN_RUNTIME_ROOT");
    if (runtime_root == NULL || runtime_root[0] == '\0')
        runtime_root = discover_bundled_runtime_root(argv0, bundled_runtime_root,
                                                     sizeof(bundled_runtime_root));
    if (runtime_root == NULL || runtime_root[0] == '\0') runtime_root = CDIN_DEFAULT_RUNTIME_ROOT;

    {
        char expected[32];
        (void)snprintf(expected, sizeof(expected), "%u.%u.%u",
                       CDIN_BACKEND_VERSION_MAJOR, CDIN_BACKEND_VERSION_MINOR,
                       CDIN_BACKEND_VERSION_PATCH);
        if (cdin_backend_version() == NULL || strcmp(cdin_backend_version(), expected) != 0) {
            MMLLOG_FATAL(log->logger, "Backend ABI version mismatch: expected %s, found %s",
                         expected, cdin_backend_version() != NULL ? cdin_backend_version() : "(null)");
            return EXIT_FAILURE;
        }
    }
    cdin_backend_config_init(&config);
    config.runtime_root = runtime_root;
    config.runtime_entry = options->runtime_entry;
    config.extension_source_root = options->extension_root;
    config.enable_lua = 1;
    config.enable_headless_protocol = 1;
    config.log_output = CDIN_BACKEND_LOG_OUTPUT_CALLBACK;
    config.log_level = CDIN_BACKEND_LOG_INFO;
    config.log_callback = cdin_log_backend_sink;
    config.log_context = log;

    status = cdin_backend_create(&config, &backend);
    if (status != CDIN_BACKEND_OK) {
        MMLLOG_ERROR(log->logger, "Backend create failed: %s", cdin_backend_status_name(status));
        goto cleanup;
    }
    status = cdin_backend_start(backend);
    if (status != CDIN_BACKEND_OK) {
        MMLLOG_ERROR(log->logger, "Backend start failed: %s", cdin_backend_status_name(status));
        goto cleanup;
    }
    if (cdin_frontend_extensions_load(
            backend, options, log, &loaded_extensions) != 0) {
        MMLLOG_ERROR(log->logger, "Could not load the requested trusted Runtime extensions");
        goto cleanup;
    }
    status = cdin_backend_pump(backend, 64u, &processed);
    if (status != CDIN_BACKEND_OK) {
        MMLLOG_ERROR(log->logger, "Backend pump failed: %s", cdin_backend_status_name(status));
        goto cleanup;
    }
    if (cdin_frontend_backend_smoke(backend, log) != 0) {
        MMLLOG_ERROR(log->logger, "Headless Frontend/Backend protocol smoke failed");
        goto cleanup;
    }
    result = EXIT_SUCCESS;
cleanup:
    if (backend != NULL) {
        if (loaded_extensions != 0u &&
            cdin_frontend_extensions_unload(
                backend, options, log, loaded_extensions) != 0) {
            MMLLOG_ERROR(log->logger, "One or more trusted Runtime extensions failed to unload");
            result = EXIT_FAILURE;
        }
        status = cdin_backend_shutdown(backend, 0);
        if (status != CDIN_BACKEND_OK) {
            MMLLOG_ERROR(log->logger, "Backend shutdown failed: %s", cdin_backend_status_name(status));
            result = EXIT_FAILURE;
        }
        cdin_backend_destroy(backend);
    }
    return result;
}

int main(int argc, char **argv)
{
    cdin_options options;
    cdin_options_status parsed;
    cdin_log log;
    int result = EXIT_FAILURE;
    parsed = cdin_options_parse(argc, argv, &options);
    if (parsed == CDIN_OPTIONS_HELP) { (void)fputs(cdin_options_usage(), stdout); return EXIT_SUCCESS; }
    if (parsed == CDIN_OPTIONS_VERSION) {
        (void)printf("cdin %s\n", CDIN_VERSION);
        return EXIT_SUCCESS;
    }
    if (parsed != CDIN_OPTIONS_OK) {
        (void)fprintf(stderr, "cdin: invalid arguments\n%s", cdin_options_usage());
        return EXIT_FAILURE;
    }
    if (strcmp(options.frontend, "headless") == 0) {
        if (!options.check_only) {
            (void)fputs("cdin: headless mode is a validation target; use --check\n", stderr);
            return 3;
        }
    } else if (strcmp(options.frontend, "tui") == 0) {
        if (options.check_only) {
            (void)fputs("cdin: --check is only supported by the headless frontend\n", stderr);
            return 3;
        }
#ifdef CDIN_ENABLE_GUI_SDL
    } else if (strcmp(options.frontend, "gui-sdl") == 0) {
        /* --check runs a live Backend/Runtime session against SDL dummy video. */
#else
    } else if (strcmp(options.frontend, "gui-sdl") == 0) {
        (void)fputs("cdin: frontend 'gui-sdl' was not built with SDL3 support\n", stderr);
        return 3;
#endif
    } else {
        (void)fprintf(stderr, "cdin: frontend '%s' is not launchable\n", options.frontend);
        return 3;
    }
    if (!cdin_log_open(&log)) {
        (void)fputs("cdin: failed to initialize m-mdy-m/log.c\n", stderr);
        return EXIT_FAILURE;
    }
    if (strcmp(options.frontend, "headless") == 0) {
        MMLLOG_INFO(log.logger, "Composition Root startup validation begins");
        result = run_check(&options, &log, argc > 0 ? argv[0] : NULL);
        MMLLOG_INFO(log.logger, "Composition Root startup validation %s",
                    result == EXIT_SUCCESS ? "passed" : "failed");
    } else if (strcmp(options.frontend, "tui") == 0) {
        MMLLOG_INFO(log.logger, "Composition Root TUI startup begins");
        result = cdin_frontend_tui_launch(&options, &log);
        MMLLOG_INFO(log.logger, "Composition Root TUI session %s",
                    result == EXIT_SUCCESS ? "stopped normally" :
                    result == 3 ? "was not launched" : "failed");
#ifdef CDIN_ENABLE_GUI_SDL
    } else {
        MMLLOG_INFO(log.logger, "Composition Root GUI-SDL startup begins");
        result = cdin_frontend_gui_sdl_launch(&options, &log);
        MMLLOG_INFO(log.logger, "Composition Root GUI-SDL session %s",
                    result == EXIT_SUCCESS ? "stopped normally" :
                    result == 3 ? "was not launched" : "failed");
#endif
    }
    cdin_log_close(&log);
    return result;
}
