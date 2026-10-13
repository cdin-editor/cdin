# The test build. Kept apart from mk/build.mk because none of this is
# production code: no optimisation, no stripping, sanitizers on request, and
# its own output directory so a test run never touches the shipping binary.
#
# Every target here is real and runs. Where a check cannot run in this
# environment it says so and reports SKIPPED with a reason, rather than
# exiting 0 and looking like a pass.

TEST_OUT_DIR := build/$(PLATFORM)-test
TEST_SRC_DIR := tests/c
TEST_BIN     := $(TEST_OUT_DIR)/cdin-tests

# The C suites link only the modules they test, plus stubs for the renderer.
# tests/c/stub_renderer.c satisfies renderer_cache.c's dependency on the
# renderer so the damage cache can be driven without SDL.
TEST_SRCS := $(TEST_SRC_DIR)/test_main.c \
             $(TEST_SRC_DIR)/test_logger.c \
             $(TEST_SRC_DIR)/test_rencache.c \
             $(TEST_SRC_DIR)/test_alloc.c \
             $(TEST_SRC_DIR)/test_base.c \
             $(TEST_SRC_DIR)/test_job.c \
             $(TEST_SRC_DIR)/stub_renderer.c

TEST_PRODUCT_SRCS := src/core/logger.c src/ui/renderer_cache.c \
                     src/loop/loop.c \
                     src/base/alloc.c src/base/arena.c src/base/error.c

TEST_OBJS := $(TEST_SRCS:%.c=$(TEST_OUT_DIR)/%.o) \
             $(TEST_PRODUCT_SRCS:%.c=$(TEST_OUT_DIR)/%.o)

# -DCDIN_JOB_TEST_HOOKS enables src/loop's test-only parking points, so the
# shutdown lifetime race can be held in a known state instead of raced for.
# TEST-ONLY: mk/config.mk's BASE_CFLAGS, which builds everything that ships,
# does not define it, so the hooks are absent from the release and debug binaries
# rather than present and unused. Verified with nm on the release object.
#
# The other test flags are the shipping warnings plus the two the project standard
# adds. -Wconversion is in the required set and the existing sources are not clean
# under it, so it is off here until they are converted; see `make check` and the
# baseline it gates against.
#
# -O0 -g3 -DDEBUG rather than BASE_CFLAGS' release flags, for one reason:
# src/base/alloc.c compiles its live-block registry, guard bytes and free
# quarantine under CDIN_ALLOC_DEBUG, which is tied to NDEBUG. A release-configured
# test runner would compile them out, and a test runner that cannot see a leak is
# not a leak checker — and the quarantine is what makes a use-after-free
# observable instead of a coin flip.
TEST_CFLAGS := -std=gnu11 -fno-strict-aliasing -O0 -g3 -DDEBUG \
               -Wall -Wextra -Wshadow -Wstrict-prototypes -Wformat=2 \
               -Wno-unused-parameter -Wno-conversion -Isrc \
               -DCDIN_JOB_TEST_HOOKS

# Where the suites write their scratch files, relative to $(CURDIR). Passed to
# the runner as an argument rather than compiled in, for two reasons: a path in
# a -D has to survive the makefile and the shell (and a Windows path's colon
# starts a new token), and $(CURDIR) is an MSYS path ("/d/CODE/cdin") that the
# native CRT cannot open. Relative, it is both.
TEST_SCRATCH := $(TEST_OUT_DIR)/test-scratch

# The sanitizer build of the tests. debug-san runs this.
#
# Whether ASan+UBSan is actually available is a property of the toolchain, not
# of the repository, so it is detected here rather than assumed. MinGW-w64
# ships without libasan/libubsan unless the gcc-libs package provides them; on
# this platform the flags reach the compiler and then fail at link time, which
# is a "make target that does not exist" in all but name. When they are missing,
# the suites still build and run uninstrumented and say so, so a report never
# claims a sanitizer pass that did not happen.
HAVE_SANITIZE := $(shell printf 'int main(void){return 0;}' > /tmp/cdin_san_probe.c 2>/dev/null && \
	$(CC) -fsanitize=address,undefined /tmp/cdin_san_probe.c -o /tmp/cdin_san_probe$(EXE) \
	>/dev/null 2>&1 && echo yes || echo no)

ifeq ($(SANITIZE),1)
  ifeq ($(HAVE_SANITIZE),yes)
    TEST_CFLAGS  += -fsanitize=address,undefined -fno-omit-frame-pointer \
                   -fno-sanitize-recover=all
    TEST_LDFLAGS := -fsanitize=address,undefined
  endif
endif

.PHONY: test test-c test-lua test-plugins test-workflows test-site-dir
.PHONY: test-san valgrind fuzz test-handle tsan

$(TEST_OUT_DIR)/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(TEST_CFLAGS) -MMD -MP -c $< -o $@

$(TEST_BIN): $(TEST_OBJS)
	@mkdir -p $(dir $@)
	$(CC) $(TEST_OBJS) -o $@ $(TEST_LDFLAGS) $(LIBUV_LDFLAGS)

test-c: $(TEST_BIN)
	@mkdir -p "$(TEST_SCRATCH)"
	@cd $(CURDIR) && echo 'â”€â”€ C unit tests â”€â”€' && $(TEST_BIN) "$(TEST_SCRATCH)"


# â”€â”€ Lua-boundary tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#
# A second binary, because the handle convention and the error convention are the
# only code here that needs a real lua_State, and the first binary deliberately
# links none: it tests modules in isolation, and pulling Lua into it would make
# every other suite depend on Lua being present and correct.
#
# So these cases live here, where linking Lua is the point. The alternative -
# testing them through the Lua integration suite with a stub - cannot work,
# because the thing under test IS the binding.
#
# LUA_CFLAGS/LUA_LDFLAGS come from mk/config.mk and are already resolved; if Lua
# was not found the target says so and skips rather than failing, because a
# machine without Lua's headers cannot run these but can run everything else.
LUA_TEST_BIN := $(TEST_OUT_DIR)/cdin-tests-lua
LUA_TEST_SRCS := $(TEST_SRC_DIR)/test_handle.c \
                 $(TEST_SRC_DIR)/test_font.c \
                 $(TEST_SRC_DIR)/stub_handle_lua.c \
                 $(TEST_SRC_DIR)/stub_font.c \
                 $(TEST_SRC_DIR)/lua_harness.c \
                 $(TEST_SRC_DIR)/test_main_lua.c
LUA_TEST_PRODUCT_SRCS := src/lua/handle.c src/lua/error.c \
                         src/api/renderer_font.c \
                         src/base/alloc.c src/base/error.c src/core/logger.c
LUA_TEST_OBJS := $(LUA_TEST_SRCS:%.c=$(TEST_OUT_DIR)/lua/%.o) \
                 $(LUA_TEST_PRODUCT_SRCS:%.c=$(TEST_OUT_DIR)/lua/%.o)

$(TEST_OUT_DIR)/lua/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(TEST_CFLAGS) $(LUA_CFLAGS) -MMD -MP -c $< -o $@

$(LUA_TEST_BIN): $(LUA_TEST_OBJS)
	@mkdir -p $(dir $@)
	$(CC) $(LUA_TEST_OBJS) -o $@ $(TEST_LDFLAGS) $(LUA_LDFLAGS) -lm

test-handle: $(LUA_TEST_BIN)
	@if [ -z "$(LUA_LDFLAGS)" ]; then \
	  echo 'SKIPPED handle/error suites: Lua development files not found -'; \
	  echo '  that is not a pass. They need lua.h and liblua.'; \
	  exit 1; \
	fi
	@echo 'â”€â”€ handle + error convention (real lua_State) â”€â”€'
	@$(LUA_TEST_BIN)


# â”€â”€ the whole `make test` â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#
# The C suites and the Lua data-layer suites. Cross-repo targets stay separate
# (test-plugins, test-workflows, test-site-dir) because they need a cdin-x
# checkout; `make test` is everything that runs from a clean clone.

test: test-c test-handle test-lua


test-lua:
	@command -v $(LUA) >/dev/null 2>&1 || command -v lua >/dev/null 2>&1 || { \
		echo 'âœ— lua not found (apt: sudo apt install lua5.4)'; exit 1; }
	@echo 'â”€â”€ loader + keymap integrity â”€â”€'
	@CDIN_SRC="$(CURDIR)" CDIN_DIR="$(TEST_CDIN_DIR)" $(LUA_RUNNER) scripts/test_lua.lua >/dev/null
	@CDIN_SRC="$(CURDIR)" CDIN_DIR="$(TEST_CDIN_DIR)" $(LUA_RUNNER) scripts/test_commands.lua
	@echo 'â”€â”€ unit + integration â”€â”€'
	@CDIN_THEME_TREE="$(THEME_TREE)" $(LUA_RUNNER) tests/lua/run.lua


# â”€â”€ sanitizers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# Runs the C suites under ASan + UBSan. The Lua suites are run against the
# sanitizer-built binary only in debug-san; here the point is the C code the
# sanitizer can actually see.
test-san:
	@$(MAKE) SANITIZE=1 test-c


# ASan+UBSan on the debug binary, then the C suites under them.
#
# Exits NON-ZERO when the runtimes are unavailable and none of the requested
# sanitizers actually ran. This target previously ran the suites uninstrumented
# and then exited 0 with a SKIPPED line printed - a false green, where a report
# reading only the exit code would record a sanitizer pass that never happened.
#
# The uninstrumented suites are still run first, because they are real tests and
# their results are worth having; but the target's own verdict is the sanitizers,
# so that is what the exit code reports.
debug-san: $(TEST_BIN)
	@$(MAKE) BUILD=debug SANITIZE=1
	@mkdir -p "$(TEST_SCRATCH)"
	@cd $(CURDIR) && echo '' && echo 'â”€â”€ C suites (ASan + UBSan) â”€â”€' && \
		$(TEST_BIN) "$(TEST_SCRATCH)"
	@if [ "$(HAVE_SANITIZE)" = "yes" ]; then \
		echo 'ASan + UBSan: instrumented run above - this is a real pass'; \
	else \
		echo ''; \
		echo 'NOT RUN - ASan/UBSan: this toolchain has no libasan/libubsan'; \
		echo '   reproduce:  gcc -fsanitize=address,undefined t.c -o t'; \
		echo '   fails with: ld: cannot find -lasan'; \
		echo '   fix (MinGW-w64): pacman -S mingw-w64-x86_64-gcc-libs'; \
		echo '   fix (Debian):   apt install libasan8 libubsan1'; \
		echo '   The suites above ran UNINSTRUMENTED. That is not a pass.'; \
		exit 1; \
	fi

# TSan, for the worker-pool code.
#
# Separate from debug-san because it is a different runtime with a different
# availability story, and because src/loop/ is the only threaded code here: TSan
# is the check that would catch a worker reading a request the main thread freed,
# which no assertion in the suite can catch reliably (measured: that race
# crashes about 1 run in 6, so a test asserting on the outcome asserts on luck).
#
# Detected the same way as ASan - by trying to link - rather than assumed.
HAVE_TSAN := $(shell printf 'int main(void){return 0;}' > /tmp/cdin_tsan_probe.c 2>/dev/null && \
	$(CC) -fsanitize=thread /tmp/cdin_tsan_probe.c -o /tmp/cdin_tsan_probe$(EXE) \
	>/dev/null 2>&1 && echo yes || echo no)

TSAN_TEST_BIN := $(TEST_OUT_DIR)/cdin-tests-tsan

tsan:
ifeq ($(HAVE_TSAN),yes)
	@mkdir -p $(dir $(TSAN_TEST_BIN))
	@echo 'â”€â”€ C suites under TSan â”€â”€'
	@$(CC) $(TEST_CFLAGS) -fsanitize=thread -fno-omit-frame-pointer \
		-o $(TSAN_TEST_BIN) $(filter-out $(TEST_OUT_DIR)/%.o,$(TEST_OBJS)) \
		$(TEST_OUT_DIR)/src/loop/%.o -luv
	@mkdir -p "$(TEST_SCRATCH)"
	@cd $(CURDIR) && $(TSAN_TEST_BIN) "$(TEST_SCRATCH)"
	@echo 'TSan: instrumented run above - this is a real pass'
else
	@echo 'NOT RUN - TSan: this toolchain has no libtsan'
	@echo '   reproduce:  gcc -fsanitize=thread t.c -o t'
	@echo '   fails with: ld: cannot find -ltsan'
	@echo '   fix (MinGW-w64): pacman -S mingw-w64-x86_64-gcc-libs'
	@echo '   NOTE: src/loop/ runs libuv worker threads. TSan is the only check'
	@echo '   that would catch a worker touching a request the main thread freed.'
	@echo '   No other check here substitutes for it.'
	@exit 1
endif


# â”€â”€ Valgrind â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# Valgrind on Windows is not available; on Linux and macOS it is. The target
# reports SKIPPED with the reason rather than passing silently, because a
# sanitizer result that never ran and one that found nothing must not look
# the same in a report.
# Valgrind. The guard has to skip the whole recipe, not just a line of it:
# `command -v valgrind || { echo SKIPPED; exit 0; }` exits the shell that line
# runs in, and make then carries on to the next one - which is how "SKIPPED:
# not installed" was once printed directly above "valgrind: command not found".
valgrind: test-c
	@if ! command -v valgrind >/dev/null 2>&1; then \
		echo 'SKIPPED valgrind: not installed (apt: sudo apt install valgrind)'; \
		exit 0; \
	fi; \
	mkdir -p "$(TEST_SCRATCH)"; \
	cd $(CURDIR) && echo 'â”€â”€ C suites under valgrind â”€â”€' && \
		valgrind --error-exitcode=1 --leak-check=full \
			--errors-for-leak-kinds=definite $(TEST_BIN) "$(TEST_SCRATCH)"


# â”€â”€ fuzz harnesses â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# Every parser of external input must have a harness. The list is the policy,
# not a set of what happens to exist: `make fuzz` reports MISSING for one that
# is listed and not written, so a parser cannot quietly acquire no fuzzing.
#
# The harnesses so far test reference transcriptions of the parsers that live in
# Lua today (utf8, EOL/BOM, path). When each moves to C - Phase 1 for utf8,
# Phase 4 for the rest - the harness changes its include and nothing else, which
# is why they are kept separate from the implementations.
FUZZ_TARGETS := tests/fuzz/fuzz_utf8.c tests/fuzz/fuzz_eol.c tests/fuzz/fuzz_path.c
FUZZ_COMMON  := tests/fuzz/common.h

fuzz:
	@echo 'â”€â”€ fuzz harnesses â”€â”€'
	@missing=0; \
	for f in $(FUZZ_COMMON) $(FUZZ_TARGETS); do \
		if [ -f "$$f" ]; then \
			echo "   present  $$f"; \
		else \
			echo "   MISSING  $$f"; missing=1; \
		fi; \
	done; \
	if [ -d tests/fuzz/corpus ]; then \
		echo "   corpus   tests/fuzz/corpus/"; \
	else \
		echo "   corpus   (none checked in yet)"; \
	fi; \
	if [ $$missing -ne 0 ]; then \
		echo 'fuzz: a listed harness is not written yet'; exit 1; \
	fi; \
	echo ''; \
	echo '   NOT RUN: this target lists the harnesses; it does not build or'; \
	echo '   drive them. Driving one needs a libFuzzer-capable compiler:'; \
	echo '     clang -fsanitize=fuzzer,address,undefined -I src tests/fuzz/fuzz_utf8.c -o fuzz_utf8'; \
	echo '     ./fuzz_utf8 -max_total_time=60 tests/fuzz/corpus/utf8'; \
	echo '   See tests/fuzz/common.h for the rules a harness follows.'

-include $(TEST_OBJS:.o=.d)
