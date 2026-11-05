#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <cdin/backend.h>
#ifndef CDIN_VERSION
#define CDIN_VERSION "development"
#endif
#ifndef CDIN_DEFAULT_RUNTIME_ROOT
#define CDIN_DEFAULT_RUNTIME_ROOT ""
#endif
static void usage(FILE *stream) {
  (void)fprintf(stream, "Usage: cdin [--help] [--version] [--check]\n\n  --help       Show help.\n  --version    Show versions.\n  --check      Start and stop Backend/Runtime to validate startup.\n");
}
static const char *runtime_root(void) {
  const char *value = getenv("CDIN_RUNTIME_ROOT");
  return value != NULL && value[0] != '\0' ? value : CDIN_DEFAULT_RUNTIME_ROOT;
}
static int check_startup(void) {
  cdin_backend_config config; cdin_backend *backend = NULL; cdin_backend_status status;
  cdin_backend_config_init(&config); config.runtime_root = runtime_root();
  config.runtime_entry = "cdin.runtime"; config.enable_lua = 1; config.enable_headless_protocol = 1;
  status = cdin_backend_create(&config, &backend);
  if (status != CDIN_BACKEND_OK) { (void)fprintf(stderr, "[CDIN] create: %s\n", cdin_backend_status_name(status)); return EXIT_FAILURE; }
  status = cdin_backend_start(backend);
  if (status != CDIN_BACKEND_OK) { (void)fprintf(stderr, "[CDIN] start: %s\n", cdin_backend_status_name(status)); cdin_backend_destroy(backend); return EXIT_FAILURE; }
  status = cdin_backend_shutdown(backend, 0);
  if (status != CDIN_BACKEND_OK) { (void)fprintf(stderr, "[CDIN] shutdown: %s\n", cdin_backend_status_name(status)); cdin_backend_destroy(backend); return EXIT_FAILURE; }
  cdin_backend_destroy(backend); (void)puts("[CDIN] startup check passed"); return EXIT_SUCCESS;
}
int main(int argc, char **argv) {
  int check = 0; int i;
  for (i = 1; i < argc; ++i) {
    if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) { usage(stdout); return EXIT_SUCCESS; }
    if (strcmp(argv[i], "--version") == 0) { (void)printf("cdin %s\nbackend %s\n", CDIN_VERSION, cdin_backend_version()); return EXIT_SUCCESS; }
    if (strcmp(argv[i], "--check") == 0) { check = 1; continue; }
    (void)fprintf(stderr, "cdin: unknown option: %s\n", argv[i]); usage(stderr); return 2;
  }
  if (!check) { usage(stderr); return 2; }
  return check_startup();
}
