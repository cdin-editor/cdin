PREFIX ?= /usr/local
BINDIR := $(PREFIX)/bin
LIBDIR := $(PREFIX)/lib/cdin
DATADIR := $(LIBDIR)/data

BUILD ?= release
SDL_VERSION ?= auto
LUA_VERSION ?= auto
# Interpreter for the Lua data-layer tests, and the tree they resolve
# EXEDIR/data against. TEST_CDIN_DIR empty means "build a tree from
# scripts/fixtures/", which is the default and the only mode that needs
# nothing from the developer's disk.
LUA ?= $(shell command -v lua 2>/dev/null)

# The fixture tree `make test-lua` points the tests/lua theme tests at: a
# directory holding data/themes/<name>/theme.lua, which it becomes EXEDIR for.
# Same location scripts/test_lua.lua builds, so the two suites read one tree.
THEME_TREE ?= $(if $(TEMP),$(TEMP),$(if $(TMPDIR),$(TMPDIR),/tmp))/cdin-test-lua
ifeq ($(LUA),)
  LUA_RUNNER := lua
else
  LUA_RUNNER := $(LUA)
endif
TEST_CDIN_DIR ?=
CDIN_DIR ?= $(CURDIR)

# Interpreter for the two build-time Python steps: icon generation (mk/build.mk)
# and data assembly (mk/bundle.mk). Override with `make PYTHON=python`.
PYTHON ?= python3

PKG_CONFIG := $(shell command -v pkg-config 2>/dev/null)

ifeq ($(BUILD),debug)
  OPT := -O0 -g3 -DDEBUG
  STRIP :=
else ifeq ($(BUILD),tiny)
  OPT := -Os -DNDEBUG -ffunction-sections -fdata-sections -flto
  STRIP := -s
  LDFLAGS_TINY := -Wl,--gc-sections
else
  OPT := -O3 -DNDEBUG
  STRIP := -s
endif

# SDL selection: explicit value wins, otherwise prefer SDL3 then SDL2
ifeq ($(SDL_VERSION),auto)
  ifneq ($(PKG_CONFIG),)
    ifeq ($(shell $(PKG_CONFIG) --exists sdl3 && echo y),y)
      SDL_VERSION := 3
    else ifeq ($(shell $(PKG_CONFIG) --exists sdl2 && echo y),y)
      SDL_VERSION := 2
    else
      SDL_VERSION := 3
    endif
  else
    SDL_VERSION := 3
  endif
endif

SDL_PKG := sdl2
SDL_HEADER := SDL2/SDL.h
ifeq ($(SDL_VERSION),3)
  SDL_PKG := sdl3
  SDL_HEADER := SDL3/SDL.h
endif

ifneq ($(PKG_CONFIG),)
  SDL_CFLAGS := $(shell $(PKG_CONFIG) --cflags $(SDL_PKG) 2>/dev/null)
  SDL_LDFLAGS := $(shell $(PKG_CONFIG) --libs $(SDL_PKG) 2>/dev/null)
endif

ifeq ($(SDL_LDFLAGS),)
  ifeq ($(SDL_VERSION),3)
    SDL_LDFLAGS := -lSDL3
  else
    SDL_LDFLAGS := -lSDL2
  endif
endif

LUA_PKG :=
ifneq ($(PKG_CONFIG),)
  ifeq ($(LUA_VERSION),auto)
    LUA_PKG := $(firstword $(foreach p,lua5.4 lua54 lua5.3 lua53 lua,$(if $(shell $(PKG_CONFIG) --exists $(p) 2>/dev/null && echo y),$(p))))
  else
    LUA_PKG := lua$(LUA_VERSION)
  endif
endif

ifneq ($(LUA_PKG),)
  LUA_CFLAGS := $(shell $(PKG_CONFIG) --cflags $(LUA_PKG) 2>/dev/null)
  LUA_LDFLAGS := $(shell $(PKG_CONFIG) --libs $(LUA_PKG) 2>/dev/null)
  LUA_FOUND_VERSION := $(shell $(PKG_CONFIG) --modversion $(LUA_PKG) 2>/dev/null)
else
  LUA_LDFLAGS := -llua -lm -ldl
  LUA_FOUND_VERSION := unknown
endif

# libuv: asynchronous I/O, timers and thread-pool work off the main thread.
#
# Decision 1 approves libuv alongside SDL3, with SDL3 keeping the window, input
# and rendering and libuv handling everything that must not run on the frame
# thread. src/loop/ is its first consumer.
#
# The check below is a compile, not a guess from a variable: pkg-config knows
# nothing about libuv on every platform this builds on, and a make variable set
# to the wrong value would surface as a wall of undefined symbols in loop.c
# rather than as a missing dependency. One failed compile names the problem and
# the fix.
UV_PROBE := $(shell printf '#include <uv.h>\nint main(void){uv_loop_t l;uv_loop_init(&l);uv_run(&l,UV_RUN_NOWAIT);return 0;}\n' \
  | $(CC) -x c -fsyntax-only - >/dev/null 2>&1 && echo y)

ifeq ($(UV_PROBE),y)
  LIBUV_CFLAGS :=
  LIBUV_LDFLAGS := -luv
else
  LIBUV_CFLAGS :=
  LIBUV_LDFLAGS :=
endif

BASE_CFLAGS := -std=gnu11 -fno-strict-aliasing -Wall -Wextra -Wno-unused-parameter $(OPT) $(VERSION_CFLAGS) -Isrc
CFLAGS := $(BASE_CFLAGS) $(SDL_CFLAGS) $(LUA_CFLAGS) $(LIBUV_CFLAGS)
LDFLAGS := $(SDL_LDFLAGS) $(LUA_LDFLAGS) $(LIBUV_LDFLAGS) -lm $(LDFLAGS_TINY) $(STRIP)
ifeq ($(PLATFORM),windows)
  LDFLAGS += -mwindows
endif

OUT_DIR := build/$(PLATFORM)-$(BUILD)
OUT := $(OUT_DIR)/cdin$(EXE)
SRCS := $(shell find src -name '*.c' | sort)
OBJS := $(SRCS:%.c=$(OUT_DIR)/%.o)
DEPS := $(OBJS:.o=.d)