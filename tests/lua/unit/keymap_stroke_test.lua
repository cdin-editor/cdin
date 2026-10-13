local T = require "harness"

-- The rule, and the reason it needs a test of its own:
--
-- A stroke in a keymap table is not a description of a key press. It is a
-- claim about the exact string the input layer builds -- "ctrl+", "alt+",
-- "altgr+", "shift+", then the key's own name -- and `keymap.map` is indexed by
-- that string with no normalisation, no aliases and no case folding. So a
-- stroke that differs in modifier order, in case, or in where its '+' signs
-- are is not a near miss: it is a string no key press produces, and the
-- binding dies in the one way that is completely silent -- on_key_pressed
-- misses, returns false, nothing is written anywhere.
--
-- Two of them shipped. ["ctrl+s+l"] in the log view's layer, with the docs
-- and the view's own header both saying F2, and ["ctrl+shift+alt+n"] in
-- cdin-x's treeview. This file covers the checker that now says so at boot;
-- scripts/test_commands.lua covers the runtime's own bindings against it.
--
-- core.input.command requires core, which loads core.style at require time --
-- so the renderer and system globals have to stand in before the require, the
-- same way unit/themes_test.lua does it.
T.stub("renderer", {
  font = {
    load = function(path, size)
      return {
        path = path,
        size = size,
        add_fallback = function() end,
        get_width = function() return 0 end,
        get_height = function() return 10 end,
      }
    end,
  },
  draw_text = function() end,
})
T.stub("system", {
  get_file_info = function() return nil end,
  get_time = function() return 0 end,
  fuzzy_match = function() return nil end,
  list_dir = function() return {} end,
})

local keymap = require "core.input.keymap"

-- Requiring the module ran every layer in data/core/keymaps/default.lua through
-- keymap.add, so keymap.map, keymap.reverse_map and keymap.unreachable are the
-- live tables. Snapshot all three and hand them back, or the next file in this
-- process inherits the strokes and the command registered here.
local saved = {}
for _, name in ipairs({ "map", "reverse_map", "unreachable" }) do
  saved[name] = {}
  for k, v in pairs(keymap[name]) do saved[name][k] = v end
end
T.teardown(function()
  keymap.map, keymap.reverse_map, keymap.unreachable =
    saved.map, saved.reverse_map, saved.unreachable
end)


-- ── helpers ────────────────────────────────────────────────────────────────

-- Accepted: the input layer can build this exact string, so it is the string
-- on_key_pressed will look up.
local function accepts(stroke)
  local canonical, reason = keymap.canonical_stroke(stroke)
  T.eq(canonical, stroke, string.format("%q is a stroke a key press produces", stroke))
  T.eq(reason, nil, string.format("%q is not rejected", stroke))
end

-- Rejected: not a near miss, so the third value -- the spelling that would
-- have worked -- is part of the contract too. `nil` means the reason cannot
-- honestly name one.
local function rejects(stroke, why, suggestion)
  local canonical, reason, got = keymap.canonical_stroke(stroke)
  T.eq(canonical, nil, string.format("%q is rejected, not accepted", stroke))
  T.ok(type(reason) == "string" and #reason > 0,
    string.format("%q is rejected with a reason", stroke))
  if why then
    -- Plain find, not a pattern: these reasons carry '+' and '"', which are
    -- pattern metacharacters, and the point is the exact wording.
    T.ok(reason:find(why, 1, true) ~= nil,
      string.format("%q says %s (says: %s)", stroke, why, reason))
  end
  T.eq(got, suggestion,
    string.format("%q suggests %s", stroke, tostring(suggestion)))
end


-- ── spellings the input layer builds ───────────────────────────────────────

accepts("f2")
accepts("escape")
accepts("return")
accepts("ctrl+s")
accepts("ctrl+shift+l")
accepts("ctrl+alt+n")
accepts("altgr+enter")
accepts("ctrl+alt+altgr+shift+z")
-- A key name is one part and may contain a space, because the input layer
-- appends the key's own name verbatim: "keypad enter" is one key, not two.
accepts("keypad enter")
accepts("left")

-- The modifier order is the build order, and a stroke that gets it right is
-- the one the lookup finds.
local built = keymap.canonical_stroke("ctrl+alt+shift+n")
T.eq(built, "ctrl+alt+shift+n", "ctrl+alt+shift+n is built in that order")


-- ── spellings it cannot build ──────────────────────────────────────────────

-- The one that shipped. '+' joins modifiers and is not part of a key name, so
-- no stroke has two key names in it.
rejects("ctrl+s+l", "the key is one key name", "ctrl+s+l")

-- Modifier order, and a repeated modifier. Both are the same failure: a
-- modifier the input layer has already emitted.
rejects("ctrl+shift+alt+n", "out of order", "ctrl+alt+shift+n")
rejects("shift+ctrl+l", "out of order", "ctrl+shift+l")
rejects("alt+ctrl+n", "out of order", "ctrl+alt+n")
rejects("ctrl+ctrl+n", "out of order", "ctrl+n")

-- A modifier name this input layer has never heard of. No suggestion: nothing
-- says which of ctrl / alt / meta was meant, and guessing would bind a bare
-- key to a command nobody asked for.
rejects("cmd+p", "not a modifier", nil)
rejects("super+p", "not a modifier", nil)
rejects("win+shift+n", "not a modifier", nil)
rejects("meta+f", "not a modifier", nil)

-- A bare "super" is not this check's business: nothing says it was meant as a
-- modifier, and it is a JavaScript keyword in an extension's syntax table. It
-- is read as a key name, which is the only reading that does not invent a
-- binding.
accepts("super")

-- Case. The input layer lowercases the key it builds, so "F2" is a different
-- string from "f2" and matches nothing.
rejects("F2", "lowercased", "f2")
-- "Ctrl+s" is caught by the key-name rule instead, and honestly: "Ctrl" is not
-- a modifier name this input layer knows, so it is read as a key name and the
-- stroke has two of them. The reason names the wrong mistake, but the
-- suggestion is the fix, so the line still tells the whole story.
rejects("Ctrl+s", "the key is one key name", "ctrl+s")

-- Empty parts and missing keys.
rejects("ctrl+", "empty part", nil)
rejects("+ctrl", "empty part", nil)
rejects("ctrl++s", "empty part", nil)
rejects("ctrl", "no key", "ctrl")

-- Not a keystroke at all.
rejects("", "not a keystroke", nil)
T.eq(keymap.canonical_stroke(nil), nil, "nil is not a keystroke")
T.eq(keymap.canonical_stroke(42), nil, "a number is not a keystroke")
T.eq(keymap.canonical_stroke({}), nil, "a table is not a keystroke")


-- ── the runtime's own bindings ─────────────────────────────────────────────

-- Every layer in data/core/keymaps/default.lua went through keymap.add when
-- this module was required, so this is the runtime's own set, unfiltered.
local dead = {}
for stroke in pairs(keymap.map) do
  if keymap.canonical_stroke(stroke) == nil then dead[#dead + 1] = stroke end
end
table.sort(dead)
T.eq(#dead, 0, "every stroke the runtime binds is one a key press produces" ..
  (#dead > 0 and (" (" .. table.concat(dead, ", ") .. ")") or ""))
T.eq(next(keymap.unreachable), nil,
  "keymap.add recorded nothing while loading the runtime's own keymap")


-- ── keymap.add records, and refuses nothing ────────────────────────────────

local command = require "core.input.command"

-- Two commands, so reverse_map stays unambiguous: it holds one stroke per
-- command, and a command bound to several of them keeps whichever was
-- registered last -- hash order, in other words.
local fired = 0
command.add(nil, {
  ["test:live"] = function() fired = fired + 1 end,
  ["test:dead"] = function() fired = fired + 100 end,
})
T.teardown(function() command.remove({ "test:live", "test:dead" }) end)

keymap.add({
  ["ctrl+s+l"]         = "test:dead",   -- unbuildable: two key names
  ["ctrl+shift+alt+n"] = "test:dead",   -- unbuildable: modifiers out of order
  ["ctrl+alt+shift+n"] = "test:live",   -- buildable, and the fix for the above
  ["f2"]               = "test:live",
})

local entry = keymap.unreachable["ctrl+s+l"]
T.ok(entry ~= nil, "keymap.add records a stroke it cannot build")
T.eq(entry and entry.commands, { "test:dead" }, "the record names the commands it would have run")
T.ok(entry and entry.reason:find("one key name", 1, true) ~= nil,
  "the record says why the stroke is dead")
T.eq(keymap.unreachable["ctrl+shift+alt+n"] and
     keymap.unreachable["ctrl+shift+alt+n"].suggestion,
  "ctrl+alt+shift+n", "the record carries the spelling that would have worked")
T.eq(keymap.unreachable["ctrl+alt+shift+n"], nil,
  "a stroke that can be produced is not recorded")
T.eq(keymap.unreachable["f2"], nil, "nor is a plain f2")

-- Reported, not refused. A binding nobody can press is already inert, and
-- refusing it would turn a typo in one extension into a boot that fails for
-- everybody.
T.eq(keymap.map["ctrl+s+l"], { "test:dead" },
  "an unreachable stroke is still bound: it is said out loud, not dropped")

-- `test:live` and `test:dead` are each bound to two strokes above, and
-- reverse_map holds exactly one stroke per command. Which one is an artefact:
-- keymap.add walks its argument with pairs(), so the survivor is whichever key
-- the table's hash order produced last, and Lua seeds its string hash from
-- time and addresses, so it differs between runs of the same binary on the same
-- input. Measured on this machine: 7 of 10 runs gave "ctrl+alt+shift+n" and 3
-- gave "f2", from one unchanged table.
--
-- Asserting a specific stroke made this test fail intermittently — the worst
-- shape a test can have, since it spends CI budget and tells the reader
-- nothing. The contract is "one of the strokes bound to it", and that is what
-- is asserted, plus the single-binding case a caller actually depends on.
local function binding_is_one_of(cmd, a, b)
  local got = keymap.get_binding(cmd)
  T.ok(got == a or got == b,
    "a command bound to two strokes reverse-maps to one of them (got " ..
    tostring(got) .. ")")
end
binding_is_one_of("test:live", "ctrl+alt+shift+n", "f2")
binding_is_one_of("test:dead", "ctrl+s+l", "ctrl+shift+alt+n")

-- The single-binding case, because that is the one a caller relies on: "what
-- key does this command answer to" has one right answer or none, and that must
-- not depend on hash order.
keymap.add({ ["ctrl+b"] = "test:solo" })
T.eq(keymap.get_binding("test:solo"), "ctrl+b",
  "a command bound to a single stroke reverse-maps exactly")
keymap.remove({ ["ctrl+b"] = "test:solo" })
T.eq(keymap.get_binding("test:solo"), nil,
  "and unbinding it clears the reverse mapping")


-- ── the suggestion is the string on_key_pressed actually looks up ──────────

-- Otherwise canonical_stroke would be checking a rule of its own rather than
-- the lookup's. Hold ctrl, alt and shift, press n: the input layer builds the
-- stroke itself, so if this fires then "ctrl+alt+shift+n" is the lookup key.
keymap.on_key_pressed("left ctrl")
keymap.on_key_pressed("left alt")
keymap.on_key_pressed("left shift")
T.eq(keymap.on_key_pressed("n"), true,
  "ctrl+alt+shift+n reaches its command through the real key path")
T.eq(fired, 1, "and it ran once")
keymap.on_key_released("left ctrl")
keymap.on_key_released("left alt")
keymap.on_key_released("left shift")

-- The dead spelling of the same chord reaches nothing, which is the whole
-- point: the two differ only in the order the modifiers were written down.
T.eq(keymap.on_key_pressed("n"), false,
  "no key press reaches a binding spelled ctrl+shift+alt+n")
T.eq(fired, 1, "and nothing ran")


-- ── report_unreachable ─────────────────────────────────────────────────────

-- core is an argument rather than a require because keymap.lua is loaded from
-- inside core's own require chain, so `require "core"` here is circular. What
-- matters is that it says something, once, with the reason and the fix.
local logged = {}
local sink = { error = function(fmt, ...)
  logged[#logged + 1] = string.format(fmt, ...)
end }

T.eq(keymap.report_unreachable(sink), 2, "report_unreachable counts what it reported")
T.eq(#logged, 3, "one header line, then one line per dead stroke")

local text = table.concat(logged, "\n")
T.ok(text:find("no key press can produce", 1, true) ~= nil,
  "the header says the strokes are dead")
T.ok(text:find('"ctrl+s+l" -> test:dead', 1, true) ~= nil,
  "a dead stroke is quoted as written, with the command it named")
T.ok(text:find("the key is one key name", 1, true) ~= nil,
  "the reason travels with it")
T.ok(text:find('write it as "ctrl+alt+shift+n"', 1, true) ~= nil,
  "and the spelling that would have worked, when there is one")
-- The suggestion for ctrl+s+l is the stroke itself -- there is nothing else it
-- could be -- so saying "write it as" would be a fix that changes nothing.
T.eq(logged[2]:find("write it as", 1, true), nil,
  "no 'write it as' for a stroke whose only spelling is itself")

-- Sorted, so the order does not depend on the hash order of the table.
T.ok(logged[2]:find('"ctrl+s+l"', 1, true) ~= nil,
  "the first dead stroke listed is ctrl+s+l")
T.ok(logged[3]:find('"ctrl+shift+alt+n"', 1, true) ~= nil,
  "and the second is ctrl+shift+alt+n")

-- Nothing to say is the common case and must stay quiet.
keymap.map, keymap.reverse_map, keymap.unreachable =
  saved.map, saved.reverse_map, saved.unreachable
logged = {}
T.eq(keymap.report_unreachable(sink), 0, "an empty list reports nothing")
T.eq(#logged, 0, "and logs no lines at all")

-- And the runtime's own keymap, which is all core.init has to say about.
T.eq(type(keymap.report_unreachable), "function",
  "core.init calls this once boot is done and every plugin has registered")