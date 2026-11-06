#ifndef CDIN_OPTIONS_H
#define CDIN_OPTIONS_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CDIN_OPTIONS_MAX_EXTENSIONS 32u

typedef enum cdin_options_status {
    CDIN_OPTIONS_OK = 0,
    CDIN_OPTIONS_HELP,
    CDIN_OPTIONS_VERSION,
    CDIN_OPTIONS_INVALID_ARGUMENT,
    CDIN_OPTIONS_MISSING_VALUE
} cdin_options_status;

typedef struct cdin_options {
    const char *runtime_root;
    const char *runtime_entry;
    const char *frontend;
    const char *extension_root;
    const char *extension_names[CDIN_OPTIONS_MAX_EXTENSIONS];
    size_t extension_count;
    int check_only;
} cdin_options;

void cdin_options_init(cdin_options *options);
cdin_options_status cdin_options_parse(int argc, char **argv, cdin_options *out_options);
const char *cdin_options_usage(void);

#ifdef __cplusplus
}
#endif
#endif
