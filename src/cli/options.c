/* ROOT-006: CLI parsing only; no editor-domain policy lives here. */
#include "cdin/options.h"
#include <string.h>

void cdin_options_init(cdin_options *options)
{
    if (options == NULL) return;
    options->runtime_root = NULL;
    options->runtime_entry = "cdin.runtime";
    options->frontend = "headless";
    options->check_only = 0;
}

cdin_options_status cdin_options_parse(int argc, char **argv, cdin_options *out)
{
    int i;
    if (argc < 0 || argv == NULL || out == NULL) return CDIN_OPTIONS_INVALID_ARGUMENT;
    cdin_options_init(out);
    for (i = 1; i < argc; ++i) {
        const char *arg = argv[i];
        const char *value;
        if (arg == NULL) return CDIN_OPTIONS_INVALID_ARGUMENT;
        if (strcmp(arg, "--help") == 0 || strcmp(arg, "-h") == 0) return CDIN_OPTIONS_HELP;
        if (strcmp(arg, "--version") == 0) return CDIN_OPTIONS_VERSION;
        if (strcmp(arg, "--check") == 0) { out->check_only = 1; continue; }
        if (strcmp(arg, "--runtime-root") == 0 ||
            strcmp(arg, "--runtime-entry") == 0 ||
            strcmp(arg, "--frontend") == 0) {
            if (i + 1 >= argc || argv[i + 1] == NULL || argv[i + 1][0] == '\0')
                return CDIN_OPTIONS_MISSING_VALUE;
            value = argv[++i];
            if (strcmp(arg, "--runtime-root") == 0) out->runtime_root = value;
            else if (strcmp(arg, "--runtime-entry") == 0) out->runtime_entry = value;
            else out->frontend = value;
            continue;
        }
        return CDIN_OPTIONS_INVALID_ARGUMENT;
    }
    return CDIN_OPTIONS_OK;
}

const char *cdin_options_usage(void)
{
    return "Usage: cdin [--check] [--runtime-root PATH] [--runtime-entry MODULE] "
           "[--frontend headless] [--help] [--version]\n"
           "\nThe Composition Root validates and launches pinned components. "
           "Interactive adapters remain gated until Backend readiness is available.\n";
}
