-- luacheck configuration for cdin's data layer.
--
-- Two kinds of file live under data/ and they want different rules:
--
--   data/core/**    the runtime. Strict globals on (core.runtime.strict raises
--                   on any undeclared global at require time), so a typo is a
--                   load-time error rather than a nil that surfaces three
--                   frames later.
--   data/plugins/**  bundled plugins, and site extensions loadable from the
--                   user's own directory. Cannot be strict — a plugin may use
--                   any of the host globals listed below, and an extension
--                   author's own globals are their business.
--
-- The host globals are declared here rather than in each file because they are
-- a contract (docs/architecture/extension-contract.md, "Globals and the host
-- tables"), and a contract that is only written in prose is not checked.

std = "lua54"

-- ── the six globals C sets at bootstrap (src/lua/api.c) ───────────────────
read_globals = {
  -- The contract lists ARGS, VERSION, PLATFORM, SCALE, EXEFILE, PATHSEP as the
  -- six the host sets. They may be *reassigned* silently, because
  -- core.runtime.strict only fires on a missing key — do not write to them.
  "ARGS", "VERSION", "PLATFORM", "SCALE", "EXEFILE", "PATHSEP",
  -- Derived by the bootstrap in src/lua/api.c before core loads, and read by
  -- core.fs, core.plugins, core.themes and extensions resolving their own
  -- directories. Assigned exactly once, at bootstrap.
  "EXEDIR",
  -- Where main() put the file log, or "" when file logging is off.
  -- Read by data/core/logging.lua at require time; see the comment there.
  "LOGFILE",
}

-- ── the host tables ───────────────────────────────────────────────────────
globals = {
  "system",    -- src/api/system.c
  "renderer",  -- src/api/renderer_compat.c
}

-- ── files that are strict globals ──────────────────────────────────────────
files["data/core/"] = {
  -- core.init() and the rest of the runtime legitimately assign these.
  globals = {
    "core",
    -- Written by main.c's bootstrap before any file loads: EXEDIR is derived
    -- from EXEFILE there, and PATHSEP from package.config.
    "EXEDIR", "PATHSEP",
  },
}

-- ── generated and vendored code ───────────────────────────────────────────
-- data/core/rootview/logo.lua is generated from scripts/icon.svg and says so
-- at the top. Regenerating it should not be able to break the build.
ignore = {
  "data/core/rootview/logo.lua",
}
