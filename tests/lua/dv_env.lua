-- Host bootstrap for loading the real DocView outside the cdin process.
--
-- tests/lua/run.lua sets the same globals for the host, but a plain `lua`
-- invocation does not, and core.runtime.strict turns a read of an undefined
-- global into a hard error at require time. So everything data/core reads at
-- load time has to exist before the first require.
--
-- Returns the modules the tests need; does NOT touch config.direction or
-- install a font, since each test sets those up for its own case.

package.path = "data/?.lua;data/?/init.lua;tests/lua/?.lua;" .. package.path

local _stub = dofile("scripts/_stub_env.lua")
package.preload["fs"]   = function() return _stub.fs end
package.preload["path"] = function() return _stub.path end

for k, v in pairs({
  SCALE = 1, VERSION = "test", PLATFORM = "test", EXEDIR = ".",
  EXEFILE = "./cdin", ARGS = {}, PATHSEP = package.config:sub(1, 1),
  LOGFILE = "",
}) do rawset(_G, k, v) end

-- A font that answers get_width/get_height. style.lua loads four real fonts
-- at require time, so renderer.font.load has to exist BEFORE the first
-- require, and core.runtime.strict makes a missing global a hard error.
rawset(_G, "renderer", {
  draw_text = function(font, text, x, y, c) return x + #text end,
  draw_rect = function() end,
  draw_image = function() end,
  set_clip_rect = function() end,
  font = { load = function() return {
    get_height = function() return 16 end,
    get_width  = function(_, s) return #s * 8 end,
  } end },
})

rawset(_G, "system", {
  get_file_info = function() return nil end,
  get_time      = function() return 0 end,
  fuzzy_match   = function() return nil end,
  list_dir      = function() return {} end,
  jobs_run      = function() end,
  jobs_pending  = function() return 0 end,
})

-- Highlighter:new registers a tokenizing coroutine, and there is no
-- scheduler to run it outside core.step().
local core = require "core"
core.add_thread = function() return nil end

return {
  core     = core,
  DocView  = require "core.views.docview",
  Highlighter = require "core.doc.highlighter",
  config   = require "core.config",
  style    = require "core.style",
  syntax   = require "core.syntax",
  common   = require "core.utils.common",
}
