#ifndef RENCACHE_H
#define RENCACHE_H

#include <stdbool.h>
#include "renderer.h"

void rencache_show_debug(bool enable);
void rencache_free_font(RenFont *font);
void rencache_set_clip_rect(RenRect rect);
void rencache_draw_rect(RenRect rect, RenColor color);
int  rencache_draw_text(RenFont *font, const char *text, int x, int y, RenColor color);
void rencache_invalidate(void);
void rencache_begin_frame(void);
void rencache_end_frame(void);

/* Frame statistics for core:memory. All values describe the last completed
 * frame; command_buf_peak is the high-water mark of the command buffer in
 * bytes. */
void rencache_get_stats(int *draw_text, int *draw_rect, int *buf_peak);

#endif
