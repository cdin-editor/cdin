.PHONY: build clean distclean info help run debug debug-san _check_deps
.PHONY: test check bench size tiny install uninstall test-plugins test-workflows test-lua test-site-dir

ICON_INL := src/icon.inl

# gen_icon.py is a thin entry point; the work lives in scripts/_cdin/, so both are
# prerequisites — otherwise editing the generator would not regenerate icon.inl.
ICON_GEN := scripts/gen_icon.py scripts/_cdin/gen_icon.py

$(ICON_INL): $(ICON_GEN) scripts/icon.svg
	@command -v $(PYTHON) >/dev/null 2>&1 || { \
		echo '✗ $(PYTHON) not found (needed to generate $(ICON_INL))'; exit 1; }
	$(PYTHON) scripts/gen_icon.py scripts/icon.svg --out-inl $(ICON_INL) --out-dir scripts/icons

# Icons only: no --out-inl, so src/icon.inl is left alone. `make` writes it.
.PHONY: gen-icons
gen-icons: $(ICON_GEN) scripts/icon.svg
	@command -v $(PYTHON) >/dev/null 2>&1 || { \
		echo '✗ $(PYTHON) not found (needed to generate icons)'; exit 1; }
	$(PYTHON) scripts/gen_icon.py scripts/icon.svg --out-dir scripts/icons

# The `build` target (binary + assembled data/) lives in mk/bundle.mk, which
# is where the one build input naming an external checkout, CDINX_DIR, is
# read. This file owns compilation only; `bin` there is the compile half of
# `make`.

$(OUT): _check_deps $(OBJS)
	@mkdir -p $(dir $@)
	$(CC) $(OBJS) -o $@ $(LDFLAGS)

$(OUT_DIR)/src/core/window.o: src/core/window.c $(ICON_INL)
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -MMD -MP -c $< -o $@

$(OUT_DIR)/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -MMD -MP -c $< -o $@

-include $(DEPS)

_check_deps:
	@command -v $(word $(words $(CC)),$(CC)) >/dev/null || { echo 'compiler not found: $(CC)'; exit 1; }
	@printf '#include <SDL3/SDL.h>\n' | $(CC) $(CFLAGS) -x c -fsyntax-only - >/dev/null 2>&1 || { \
		echo '✗ SDL3/SDL.h not found — install libsdl3-dev or set SDL3_PREFIX=/path/to/sdl3'; \
		exit 1; }
	@printf '#include <lua.h>\n' | $(CC) $(CFLAGS) -x c -fsyntax-only - >/dev/null 2>&1 || { \
		echo '✗ lua.h not found'; \
		echo '  apt: sudo apt install liblua5.4-dev'; \
		echo '  pacman: sudo pacman -S lua'; \
		exit 1; }
	@printf '#include <uv.h>\n' | $(CC) $(CFLAGS) -x c -fsyntax-only - >/dev/null 2>&1 || { \
		echo '✗ uv.h not found — src/loop/ needs libuv (Decision 1)'; \
		echo '  apt:  sudo apt install libuv1-dev'; \
		echo '  pacman: sudo pacman -S mingw-w64-x86_64-libuv'; \
		echo '  brew: brew install libuv'; \
		exit 1; }

run: build
	@$(OUT)

debug:
	@$(MAKE) BUILD=debug

debug-san:
	@$(MAKE) BUILD=debug SANITIZE=1

clean:
	rm -rf $(OUT_DIR)

distclean:
	rm -rf build
	rm -f $(ICON_INL)

info:
	@echo ''
	@echo 'cdin build configuration'
	@echo '────────────────────────────────────────'
	@printf '  %-12s %s\n' 'VERSION' '$(VERSION)'
	@printf '  %-12s %s\n' 'COMMIT' '$(COMMIT)'
	@printf '  %-12s %s\n' 'TREE' '$(if $(DIRTY),dirty,clean)'
	@printf '  %-12s %s\n' 'PLATFORM' '$(PLATFORM)'
	@printf '  %-12s %s\n' 'BUILD' '$(BUILD)'
	@printf '  %-12s %s\n' 'SDL' '3 (required)'
	@printf '  %-12s %s [pkg: %s]\n' 'LUA' '$(LUA_FOUND_VERSION)' '$(if $(LUA_PKG),$(LUA_PKG),manual)'
	@printf '  %-12s %s\n' 'CC' '$(CC)'
	@printf '  %-12s %s\n' 'OUT' '$(OUT)'
	@printf '  %-12s %s\n' 'ICON_INL' '$(ICON_INL)'
	@printf '  %-12s %s\n' 'PREFIX' '$(PREFIX)'
	@printf '  %-12s %s\n' 'SRCS' '$(words $(SRCS)) files'
	@printf '  %-12s %s\n' 'CFLAGS' '$(CFLAGS)'
	@printf '  %-12s %s\n' 'LDFLAGS' '$(LDFLAGS)'
	@echo '────────────────────────────────────────'
	@echo ''

help:
	@echo 'Targets: build (default), run, debug, clean, distclean, install, uninstall, info, help'
	@echo ''
	@echo 'A plain "make" is all you need — plugins and themes ship inside data/,'
	@echo 'so there is nothing to fetch, clone or install first.'
	@echo ''
	@echo 'Options: SDL3_PREFIX=/path BUILD=release|debug PREFIX=/usr/local LUA_VERSION=auto|5.4'
	@echo 'Quality: test, check, bench, size, tiny (BUILD=tiny, -Os + gc-sections)'
	@echo '          test-plugins  — keymap + loader, runtime only (needs lua)'
	@echo '          test-workflows — the cdin-x workflows and their strokes (needs lua + CDINX_DIR)'
	@echo '          test-lua      — unit + integration suite in tests/lua (needs lua)'

check:
	python scripts/check.py

test-plugins:
	@command -v $(LUA) >/dev/null 2>&1 || command -v lua >/dev/null 2>&1 || { \
		echo '✗ lua not found (apt: sudo apt install lua5.4)'; exit 1; }
	@echo '── keymap integrity, 0 plugins ──'
	@CDIN_SRC="$(CURDIR)" CDIN_DIR="$(TEST_CDIN_DIR)" $(LUA_RUNNER) scripts/test_commands.lua
	@for site in full empty; do \
		for sel in nil false demo raiser; do \
			case "$$sel" in \
				nil)     v='' ;; \
				false)   v=false ;; \
				*)       v=$$sel ;; \
			esac; \
			echo ''; \
			echo "── loader: site=$$site config.plugins=$$sel ──"; \
			CDIN_SRC="$(CURDIR)" CDIN_DIR="$(TEST_CDIN_DIR)" CDIN_SITE=$$site CDIN_PLUGINS="$$v" \
				$(LUA_RUNNER) scripts/test_lua.lua || exit 1; \
		done; \
	done

test-workflows:
	@command -v $(LUA) >/dev/null 2>&1 || command -v lua >/dev/null 2>&1 || { \
		echo '✗ lua not found (apt: sudo apt install lua5.4)'; exit 1; }
	@for site in full empty; do \
		echo ''; \
		echo "── workflows: site=$$site ──"; \
		CDIN_SRC="$(CURDIR)" CDINX_DIR="$(CDINX_DIR)" CDIN_SITE=$$site \
			$(LUA_RUNNER) scripts/test_workflows.lua || exit 1; \
	done

test-site-dir:
	@command -v $(LUA) >/dev/null 2>&1 || command -v lua >/dev/null 2>&1 || { \
		echo 'lua not found (apt: sudo apt install lua5.4)'; exit 1; }
	@test -d "$(CDINX_DIR)" || { \
		echo 'CDINX_DIR does not exist: $(CDINX_DIR)'; exit 1; }
	@echo '-- site directory name --'
	@CDIN_SRC="$(CURDIR)" CDINX_DIR="$(CDINX_DIR)" $(LUA_RUNNER) scripts/test_site_dir.lua

test-lua:
	@command -v $(LUA) >/dev/null 2>&1 || command -v lua >/dev/null 2>&1 || { \
		echo '✗ lua not found (apt: sudo apt install lua5.4)'; exit 1; }
	@CDIN_SRC="$(CURDIR)" CDIN_DIR="$(TEST_CDIN_DIR)" CDIN_SITE=empty CDIN_PLUGINS=false \
		$(LUA_RUNNER) scripts/test_lua.lua >/dev/null
	@echo '── unit + integration ──'
	@CDIN_THEME_TREE="$(THEME_TREE)" $(LUA_RUNNER) tests/lua/run.lua

size:
	@echo '-- binary / data sizes --'
	@python scripts/bench.py
	@echo ''
	@echo '-- largest data dirs --'
	@python -c "from pathlib import Path; r=Path('data'); ds=sorted(((sum(f.stat().st_size for f in d.rglob('*') if f.is_file()), d) for d in r.iterdir() if d.is_dir()), reverse=True); [print(f'  {d}: {s/1024:.1f} KiB') for s,d in ds]"

tiny:
	@$(MAKE) BUILD=tiny
