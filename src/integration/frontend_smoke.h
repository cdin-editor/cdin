#ifndef CDIN_FRONTEND_SMOKE_H
#define CDIN_FRONTEND_SMOKE_H

#include "cdin/backend.h"
#include "cdin/log.h"
#include "cdin/options.h"

int cdin_frontend_backend_smoke(cdin_backend *backend, cdin_log *log);
int cdin_frontend_tui_launch(const cdin_options *options, cdin_log *log);

#endif
