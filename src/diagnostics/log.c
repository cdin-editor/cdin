/* CDIN diagnostic adapter using the pinned m-mdy-m/log.c library. */
#include "cdin/log.h"

int cdin_log_open(cdin_log *log)
{
    mmlog_logger_config_t config;
    if (log == NULL) return 0;
    log->logger = NULL;
    if (mmlog_logger_config_init(&config) != MMLLOG_OK) return 0;
    config.min_level = MMLLOG_LEVEL_INFO;
    config.output = MMLLOG_OUTPUT_STDERR;
    config.format_flags = MMLLOG_F_TIMESTAMP | MMLLOG_F_LAYER | MMLLOG_F_COMPONENT;
    return mmlog_logger_create(&config, &log->logger) == MMLLOG_OK;
}

void cdin_log_close(cdin_log *log)
{
    if (log != NULL && log->logger != NULL) {
        (void)mmlog_logger_flush(log->logger);
        mmlog_logger_destroy(log->logger);
        log->logger = NULL;
    }
}

void cdin_log_write(cdin_log *log, int32_t level, const char *component,
                    const char *layer, const char *message, size_t length)
{
    mmlog_event_t event;
    if (log == NULL || log->logger == NULL || message == NULL) return;
    if (mmlog_event_init(&event) != MMLLOG_OK) return;
    event.level = level;
    event.component = component != NULL ? component : "CDIN";
    event.layer = layer != NULL ? layer : "composition";
    event.message = message;
    event.message_length = length;
    (void)mmlog_logger_write(log->logger, &event);
}

void cdin_log_backend_sink(void *context, int level, const char *message, size_t length)
{
    int32_t mapped;
    switch (level) {
    case 0: mapped = MMLLOG_LEVEL_ERROR; break;
    case 1: mapped = MMLLOG_LEVEL_WARN; break;
    case 2: mapped = MMLLOG_LEVEL_INFO; break;
    case 3: mapped = MMLLOG_LEVEL_DEBUG; break;
    case 4: mapped = MMLLOG_LEVEL_TRACE; break;
    case 5: mapped = MMLLOG_LEVEL_FATAL; break;
    default: mapped = MMLLOG_LEVEL_WARN; break;
    }
    cdin_log_write((cdin_log *)context, mapped, "BACKEND", "backend", message, length);
}
