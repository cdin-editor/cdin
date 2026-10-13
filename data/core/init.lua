require "core.runtime.strict"

local config = require "core.config"

local preboot = require "core.preboot"
if config.session_restore_theme == nil then config.session_restore_theme = true end
if config.session_restore_dir  == nil then config.session_restore_dir  = true  end
local _boot_session = preboot.read()
if config.session_restore_theme and _boot_session.theme then
  config.theme = _boot_session.theme
end

local style = require "core.style"

local core = {}
require("core.logging").install(core)

-- Installs core.register_help_shortcuts / core.unregister_help_shortcuts.
-- Required here, before any view is built, because plugins call it from their
-- own init() and must not depend on which views happened to be constructed
-- before them.
require("core.help").install(core)

core.project_dir = nil

-- Set by core.quit, read by core.run. It is a REQUEST, not an exit: the frame
-- loop is on the stack whenever this is called (a keymap -> a command ->
-- a submit callback), and tearing the process down from there is what used to
-- hang the editor. `os.exit()` ran atexit(SDL_Quit) -> SDL_DestroyWindow
-- while SDL was still inside the event dispatch that called us, and what came
-- back was a live process with no window and no event loop: still
-- unresponsive to every key, still drawing nothing, unkillable from inside.
-- Returning from the loop instead lets main() destroy the window itself, in
-- order, after the Lua state is closed.
core._quitting = false

function core.quit(force)
  core.log("core.quit called with force=%s, already_quitting=%s", tostring(force), tostring(core._quitting))
  if core._quitting then return end
  if force then
    core._quitting = true
    core.log("core.quit: force path; the loop will stop")
    return
  end
  local dirty_count, dirty_name = 0, nil
  for _, doc in ipairs(core.docs) do
    if doc:is_dirty() then
      dirty_count = dirty_count + 1
      dirty_name  = doc:get_name()
    end
  end
  if dirty_count > 0 then
    local text = dirty_count == 1
      and string.format('"%s" has unsaved changes. Quit anyway?', dirty_name)
      or  string.format("%d docs have unsaved changes. Quit anyway?", dirty_count)
    if not system.show_confirm_dialog("Unsaved Changes", text) then return end
  end
  core.quit(true)
end

require("core.lifecycle").install(core)

-- `core:memory()` — where the bytes are. Defined here, on the core table,
-- because that is the name the report is reached by; the accounting itself
-- lives in core/memory.lua, which is where a later phase replaces the Lua-side
-- guesses with the C buffer's own counters. Required lazily inside the method
-- so nothing is loaded at boot unless somebody asks.
function core:memory()
  return require("core.memory").report()
end

local state = require "core.state"

function core.init()
  local command     = require "core.input.command"
  local keymap      = require "core.input.keymap"
  local RootView    = require "core.rootview"
  local StatusView  = require "core.views.statusview"
  local CommandView = require "core.views.commandview"
  local TitleBar    = require "core.views.titlebar"
  local Doc         = require "core.doc"

  -- Command-line flags. Parsed first so --no-plugins can veto a
  -- config.plugins list. Flags are not paths, so they are kept out of the
  -- file/dir scan below.
  local no_plugins = false
  local positional = {}
  local i = 2
  while i <= #ARGS do
    local a = ARGS[i]
    if a == "--no-plugins" or a == "-u" then
      no_plugins = true
      if a == "-u" then i = i + 1 end  -- swallow the "-u NONE" argument
    else
      positional[#positional + 1] = a
    end
    i = i + 1
  end

  local project_dir = EXEDIR
  local explicit_dir = false
  local files = {}
  for _, arg in ipairs(positional) do
    local abs  = system.absolute_path(arg) or arg
    local info = system.get_file_info(abs) or {}
    if     info.type == "file" then table.insert(files, abs)
    elseif info.type == "dir"  then project_dir = abs; explicit_dir = true
    end
  end

  if not explicit_dir and config.session_restore_dir and _boot_session.last_dir then
    local info = system.get_file_info(_boot_session.last_dir)
    if info and info.type == "dir" then
      project_dir = _boot_session.last_dir
    end
  end

  system.chdir(project_dir)
  core.project_dir = system.absolute_path(".") or project_dir

  core._boot_session = _boot_session

  state.setup_state(core)

  function core.set_active_view(view)
    assert(view, "Tried to set active view to nil")
    if view ~= core.active_view then
      core.last_active_view = core.active_view
      core.active_view      = view
    end
  end

  function core.add_thread(f, weak_ref)
    local key = weak_ref or #core.threads + 1
    local fn  = function() return core.try(f) end
    core.threads[key] = { cr = coroutine.create(fn), wake = 0 }
  end

  state.setup_views(core, RootView, CommandView, StatusView, TitleBar)
  require("core.docs").install(core, Doc)
  require("core.events").install(core, keymap)
  require("core.loop").install(core)

  local project = require "core.project"
  core.add_thread(function() project.thread(core) end)

  -- Switching project directory is a runtime operation: the working
  -- directory IS the project, and the file list and revision the views read
  -- are runtime state. The prompt that asks the user which directory is a
  -- workflow and lives in an extension, which calls this.
  core.set_project_dir = function(path) return project.set_project_dir(path) end

  command.add_defaults()

  -- Load user configuration from ~/.config/cdin/user/init.lua
  local user_path = config.user_dir .. "/init.lua"
  local got_user_error = not core.try(function()
    if system.get_file_info(user_path) then
      dofile(user_path)
    end
  end)

  if no_plugins then config.plugins = false end

  local got_plugins_error = not core.try(function()
    require("core.plugins").load_all()
  end)
  if got_plugins_error then
    core.log("plugin loading failed; continuing with core only")
  end

  keymap.report_unreachable(core)

  core.try(function()
    if not config.theme then return end
    if config.theme == style.theme_name then return end
    local themes = require "core.themes"
    if not themes.path(config.theme) then return end
    themes.apply(style, config.theme)
  end)

  local got_project_error = not core.load_project_module()

  for _, filename in ipairs(files) do
    core.root_view:open_doc(core.open_doc(filename))
  end
end


function core.active_docview()
  local DocView     = require "core.views.docview"
  local CommandView = require "core.views.commandview"
  local v = core.active_view
  if v and v:is(DocView) and not v:is(CommandView) then return v end
  return nil
end

return core