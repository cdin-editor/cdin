local config = require "core.config"

local function install(core)
  local run_threads = coroutine.wrap(function()
    while true do
      local max_time = 1 / config.fps - 0.004
      local ran_any  = false
      local to_remove = {}

      for k, thread in pairs(core.threads) do
        if thread.wake < system.get_time() then
          local _, wait = assert(coroutine.resume(thread.cr))
          if coroutine.status(thread.cr) == "dead" then
            table.insert(to_remove, k)
          elseif wait then
            thread.wake = system.get_time() + wait
          end
          ran_any = true
        end
        if system.get_time() - core.frame_start > max_time then
          coroutine.yield()
        end
      end

      for i = #to_remove, 1, -1 do
        local k = to_remove[i]
        if type(k) == "number" then table.remove(core.threads, k)
        else                        core.threads[k] = nil
        end
      end

      if not ran_any then coroutine.yield() end
    end
  end)

  function core.step()
    local did_keymap  = false
    local mouse_moved = false
    local mouse       = { x = 0, y = 0, dx = 0, dy = 0 }

    -- Dispatch completed background jobs once per frame, before anything reads
    -- the state they change.
    --
    -- Here rather than deeper in the loop, and once rather than at several
    -- points, because a job's completion may re-enter Lua: doing it at one
    -- predictable point in the frame is what keeps that from landing in the
    -- middle of a half-built view. It is also the first thing, so a job that
    -- finished during the last frame is acted on this one rather than a frame
    -- later.
    --
    -- Never sleeps — system.jobs_run dispatches what is ready and returns, so
    -- an editor with nothing outstanding costs one call per frame.
    system.jobs_run()

    for type, a, b, c, d in system.poll_event do
      if type == "mousemoved" then
        mouse_moved = true
        mouse.x, mouse.y   = a, b
        mouse.dx, mouse.dy = mouse.dx + c, mouse.dy + d
      elseif type == "textinput" and did_keymap then
        did_keymap = false
      else
        local _, res = core.try(core.on_event, type, a, b, c, d)
        did_keymap   = res or did_keymap
      end
      core.redraw = true
    end
    if mouse_moved then
      core.try(core.on_event, "mousemoved", mouse.x, mouse.y, mouse.dx, mouse.dy)
    end

    local width, height = renderer.get_size()
    core.root_view.size.x, core.root_view.size.y = width, height
    core.root_view:update()
    if not core.redraw then return false end
    core.redraw = false

    for i = #core.docs, 1, -1 do
      local doc = core.docs[i]
      if #core.get_views_referencing_doc(doc) == 0 then
        table.remove(core.docs, i)
        core.log_quiet('Closed doc "%s"', doc:get_name())
      end
    end

    local name  = core.active_view:get_name()
    local title = (name ~= "---") and (name .. " - cdin") or "cdin"
    if title ~= core.window_title then
      system.set_window_title(title)
      core.window_title = title
    end

    renderer.begin_frame()
    core.clip_rect_stack[1] = { 0, 0, width, height }
    renderer.set_clip_rect(table.unpack(core.clip_rect_stack[1]))
    core.root_view:draw()
    renderer.end_frame()
    return true
  end

  -- `_quitting` is core.quit's request (see core/init.lua): the loop returns,
  -- and main() unwinds the window in the right order. It is checked at the top
  -- of the frame so the frame that asked to quit is also the last one drawn —
  -- a loop that checked it only after rendering would draw one more frame with
  -- a half-torn-down editor in it.
  function core.run()
    while not core._quitting do
      core.frame_start = system.get_time()
      local did_redraw = core.step()
      run_threads()
      if not did_redraw and not system.window_has_focus() then
        system.wait_event(0.25)
      end
      local elapsed = system.get_time() - core.frame_start
      system.sleep(math.max(0, 1 / config.fps - elapsed))
    end
  end
end

return { install = install }
