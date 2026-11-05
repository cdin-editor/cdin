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
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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

static int run_check(const cdin_options *options, cdin_log *log)
{
    cdin_backend_config config;
    cdin_backend *backend = NULL;
    cdin_backend_status status;
    size_t processed = 0u;
    int result = EXIT_FAILURE;
    const char *runtime_root = options->runtime_root;
    if (runtime_root == NULL || runtime_root[0] == '\0') runtime_root = getenv("CDIN_RUNTIME_ROOT");
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
    status = cdin_backend_pump(backend, 64u, &processed);
    if (status != CDIN_BACKEND_OK) {
        MMLLOG_ERROR(log->logger, "Backend pump failed: %s", cdin_backend_status_name(status));
        goto cleanup;
    }
    result = EXIT_SUCCESS;
cleanup:
    if (backend != NULL) {
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
    int result;
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
    if (strcmp(options.frontend, "headless") != 0) {
        /*
         * FE-019 requires the TUI loop to multiplex input and Backend readiness.
         * Keep interactive launch disabled until that integration is implemented.
         * https://github.com/cdin-editor/spec/blob/main/docs/components/frontend.md#L82-L82
         */
        (void)fprintf(stderr, "cdin: frontend '%s' is not launchable; readiness/wakeup integration FE-019 is required\n",
                      options.frontend);
        return 3;
    }
    if (!options.check_only) {
        (void)fputs("cdin: interactive launch is not yet enabled; use --check for a lifecycle smoke test\n", stderr);
        return 3;
    }
    if (!cdin_log_open(&log)) {
        (void)fputs("cdin: failed to initialize m-mdy-m/log.c\n", stderr);
        return EXIT_FAILURE;
    }
    MMLLOG_INFO(log.logger, "Composition Root startup validation begins");
    result = run_check(&options, &log);
    MMLLOG_INFO(log.logger, "Composition Root startup validation %s", result == EXIT_SUCCESS ? "passed" : "failed");
    cdin_log_close(&log);
    return result;
}
