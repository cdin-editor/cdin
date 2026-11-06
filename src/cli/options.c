/*
 * ROOT-006: parse the Composition Root launch request. The selected adapter
 * owns its protocol/session setup; this module does not duplicate that logic.
 * https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md#L27-L27
 */
#include "cdin/options.h"

#include <string.h>

void cdin_options_init(cdin_options *options)
{
    if (options == NULL) return;
    memset(options, 0, sizeof(*options));
    options->runtime_entry = "cdin.runtime";
    options->frontend = "headless";
}

static int extension_name_valid(const char *name)
{
    size_t length;
    size_t index;
    if (name == NULL) return 0;
    length = strlen(name);
    if (length == 0u || length > 128u || name[0] == '.' ||
        name[length - 1u] == '.' || strstr(name, "..") != NULL) return 0;
    for (index = 0u; index < length; index++) {
        unsigned char ch = (unsigned char)name[index];
        if (ch >= 0x80u || !((ch >= 'a' && ch <= 'z') ||
                             (ch >= 'A' && ch <= 'Z') ||
                             (ch >= '0' && ch <= '9') ||
                             ch == '_' || ch == '-' || ch == '.')) return 0;
    }
    return 1;
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
            strcmp(arg, "--frontend") == 0 ||
            strcmp(arg, "--extension-root") == 0 ||
            strcmp(arg, "--load-extension") == 0) {
            if (i + 1 >= argc || argv[i + 1] == NULL || argv[i + 1][0] == '\0')
                return CDIN_OPTIONS_MISSING_VALUE;
            value = argv[++i];
            if (strcmp(arg, "--runtime-root") == 0) out->runtime_root = value;
            else if (strcmp(arg, "--runtime-entry") == 0) out->runtime_entry = value;
            else if (strcmp(arg, "--frontend") == 0) out->frontend = value;
            else if (strcmp(arg, "--extension-root") == 0) {
                if (out->extension_root != NULL) return CDIN_OPTIONS_INVALID_ARGUMENT;
                out->extension_root = value;
            } else {
                size_t extension_index;
                if (!extension_name_valid(value) ||
                    out->extension_count >= CDIN_OPTIONS_MAX_EXTENSIONS) {
                    return CDIN_OPTIONS_INVALID_ARGUMENT;
                }
                for (extension_index = 0u;
                     extension_index < out->extension_count;
                     extension_index++) {
                    if (strcmp(out->extension_names[extension_index], value) == 0)
                        return CDIN_OPTIONS_INVALID_ARGUMENT;
                }
                out->extension_names[out->extension_count++] = value;
            }
            continue;
        }
        return CDIN_OPTIONS_INVALID_ARGUMENT;
    }
    if (out->extension_count != 0u && out->extension_root == NULL)
        return CDIN_OPTIONS_INVALID_ARGUMENT;
    return CDIN_OPTIONS_OK;
}

const char *cdin_options_usage(void)
{
    return "Usage: cdin [--check] [--runtime-root PATH] [--runtime-entry MODULE] "
           "[--extension-root TRUSTED_DIR] [--load-extension NAME ...] "
           "[--frontend headless|tui] [--help] [--version]\n"
           "\nExtensions are opt-in trusted local code. --load-extension requires an "
           "administrator-controlled --extension-root; CDIN never discovers or loads "
           "extension directories automatically, and extension administration is not "
           "exposed over Frontend Protocol.\n"
           "\nThe headless frontend is selected by --check. The POSIX TUI is experimental "
           "and requires CDIN_ENABLE_EXPERIMENTAL_TUI=1. Windows TUI remains gated by "
           "native Console/ConPTY acceptance.\n";
}
