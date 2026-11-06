#ifndef CDIN_FRONTEND_SMOKE_H
#define CDIN_FRONTEND_SMOKE_H

#include "cdin/backend.h"
#include "cdin/log.h"
#include "cdin/options.h"

int cdin_frontend_backend_smoke(cdin_backend *backend, cdin_log *log);
int cdin_frontend_extensions_load(cdin_backend *backend,
                                  const cdin_options *options,
                                  cdin_log *log,
                                  size_t *out_loaded);
int cdin_frontend_extensions_unload(cdin_backend *backend,
                                    const cdin_options *options,
                                    cdin_log *log,
                                    size_t loaded);
int cdin_frontend_tui_launch(const cdin_options *options, cdin_log *log);
#ifdef CDIN_ENABLE_GUI_SDL
int cdin_frontend_gui_sdl_launch(const cdin_options *options, cdin_log *log);
#endif

#endif
