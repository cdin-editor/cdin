#ifndef CDIN_LOG_H
#define CDIN_LOG_H
#include <stddef.h>
#include <stdint.h>
#include "m-mdy-m/log.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct cdin_log { mmlog_logger_t *logger; } cdin_log;
int cdin_log_open(cdin_log *log);
void cdin_log_close(cdin_log *log);
void cdin_log_write(cdin_log *log, int32_t level, const char *component,
                    const char *layer, const char *message, size_t length);
void cdin_log_backend_sink(void *context, int level, const char *message, size_t length);
#ifdef __cplusplus
}
#endif
#endif
