# Bundling: turning a cdin-x checkout into a runnable editor.
#
# This is the *only* place cdin knows cdin-x exists, and it knows it as a
# path: CDINX_DIR. Nothing under src/ or data/ refers to cdin-x, nothing is
# fetched, and no submodule or sibling lookup happens at runtime. A build
# takes a directory and reads files out of it.
#
#   CDINX_DIR   a cdin-x checkout. Defaults to ../cdin-x, i.e. the usual
#               two-checkouts-in-one-directory layout. Override with
#               `make CDINX_DIR=/elsewhere/cdin-x`.
#
# Targets:
#
#   make bin     compile the binary only. No cdin-x, no data/ assembly. This
#                is what you want when iterating on C, and it is what a build
#                machine runs when it is not producing a release.
#
#   make bundle  assemble $(OUT_DIR)/data: core/ plus the mandatory set that
#                cdin-x provides (the vim plugin, the default theme, the
#                fonts). Requires CDINX_DIR.
#
#   make         the default goal: bin, then bundle.

CDINX_DIR ?= $(abspath $(CURDIR)/../cdin-x)

.PHONY: bin bundle

bin: $(OUT)

bundle:
	@command -v $(PYTHON) >/dev/null 2>&1 || { \
		echo '✗ $(PYTHON) not found (needed to assemble data/)'; exit 1; }
	@$(PYTHON) scripts/assemble_data.py \
		--src data \
		--out "$(OUT_DIR)/data" \
		--cdinx "$(CDINX_DIR)"

# `make` alone: a runnable editor, not just a binary.
#
# The DLL copy is here as well as in `bare`, because "runnable" is the whole claim
# this target makes and a tree missing its shared libraries does not run. It was
# absent here while present in `bare`, which is exactly the shape of a bug that
# only bites people who do not have the toolchain on PATH.
build: bin bundle
	$(call copy-runtime-dlls,$(OUT_DIR))
	@printf '\n✓ Built %s\n\n' '$(OUT)'

# `make bare`: the runtime with an empty site directory.
#
# The configuration the master prompt describes as cdin's real one — the core,
# the fonts and the themes, and nothing else. No plugins, no extension manager,
# no BUNDLE.lua, no cdin-x at run time. It exists because it is the only tree
# whose behaviour depends on nothing outside this repository, which makes it the
# right tree for measuring startup and idle CPU (scripts/measure_runtime.py) and
# the right tree for deciding whether a failure is cdin's or the bundle's.
#
# The fonts and themes come from $(OUT_DIR)/data, i.e. from what the bundler
# already copied, rather than from a path inside cdin-x. Two reasons: cdin then
# has no second place that knows where cdin-x keeps things, and this target works
# against any bundle output rather than a particular cdin-x layout.
#
# core is copied rather than linked. A stale core is the worst possible outcome —
# the editor would silently run yesterday's code — and a copy that is recreated
# on every run cannot be stale. The cost is a copy per bare build, which is not
# worth optimising away.
BARE_DIR ?= build/bare

# The DLLs the linked binary actually imports, read from its own import table
# rather than a hand-written list. A hardcoded list is a list that goes stale the
# next time a dependency is added or renamed, and the failure is silent and late:
# the tree builds, and then the editor dies at launch with
# STATUS_DLL_NOT_FOUND (0xC0000135) before main() can log a single line, so every
# measurement taken against it reads "NOT MEASURED" for reasons that have nothing
# to do with what is being measured. Reading the imports cannot drift from the
# binary it is describing.
#
# Recursively expanded (`=`, not `:=`) on purpose. `:=` runs objdump when this
# file is PARSED, which is before the `bin` prerequisite has built anything — so on
# a clean tree, where build/windows-release/cdin.exe does not yet exist, the list
# comes back empty, no DLLs are copied, and the bare tree cannot start. That
# failure only reproduces from a clean checkout, which is exactly where it would
# be least expected. Expanded here, it is evaluated when the recipe runs, after
# the binary exists.
#
# System DLLs (KERNEL32, USER32, msvcrt) are filtered out by the shell case below:
# they are not in the toolchain's bin directory and must not be shipped.
BARE_DLLS = $(shell objdump -p "$(OUT)" 2>/dev/null | \
	awk '/DLL Name:/ {print $$3}' | sort -u)

# copy-runtime-dlls: put the DLLs cdin.exe imports next to it.
#
# One macro, used by both `build` and `bare`, because the bug was in exactly the
# places a single definition would have prevented. cdin links SDL3, Lua and libuv
# dynamically, so the binary is not self-contained; a tree containing only
# cdin.exe and data/ dies at launch with STATUS_DLL_NOT_FOUND (0xC0000135)
# before main() logs a single line. On a developer machine it still starts,
# because the toolchain's bin directory is usually on PATH — which is why this
# survived: it reproduces only for someone without that PATH, or once the
# toolchain moves.
#
# @1 is the directory to fill. Prints what it copied, and SKIPPED with the reason
# for anything it could not find, so a tree that cannot start says so here rather
# than at launch.
define copy-runtime-dlls
	@copied=''; skipped=''; \
	for d in $(BARE_DLLS); do \
	  if [ -f "$(CC_BINDIR)/$$d" ]; then \
	    cp "$(CC_BINDIR)/$$d" "$(1)/"; copied="$$copied $$d"; \
	  elif [ -f "$(BINDIR)/$$d" ]; then \
	    cp "$(BINDIR)/$$d" "$(1)/"; copied="$$copied $$d"; \
	  else \
	    case "$$d" in \
	      KERNEL32*|USER32*|msvcrt*|ADVAPI32*|SHELL32*|ole32*|OLEAUT32*|\
GDI32*|SHELL32*|comdlg32*|IMM32*|WINMM*|setupapi*) ;; \
	      *) skipped="$$skipped $$d" ;; \
	    esac; \
	  fi; \
	done; \
	if [ -n "$$copied" ]; then echo "  runtime DLLs:$$copied"; fi; \
	if [ -n "$$skipped" ]; then \
	  echo "SKIPPED:$$skipped imported by cdin$(EXE) but not found in $(CC_BINDIR) or $(BINDIR)."; \
	  echo "  This tree will not start unless they are on PATH or copied in."; \
	fi
endef

.PHONY: bare
bare: bin
	@rm -rf "$(BARE_DIR)"
	@mkdir -p "$(BARE_DIR)/data"
	@cp "$(OUT)" "$(BARE_DIR)/cdin$(EXE)"
	@cp -r data/core "$(BARE_DIR)/data/core"
	@missing=''; \
	for d in fonts themes; do \
	  if [ -d "$(OUT_DIR)/data/$$d" ]; then \
	    cp -r "$(OUT_DIR)/data/$$d" "$(BARE_DIR)/data/$$d"; \
	  else \
	    missing="$$missing $$d"; \
	  fi \
	done; \
	if [ -n "$$missing" ]; then \
	  echo "SKIPPED:$$missing not in $(OUT_DIR)/data — run 'make bundle' first."; \
	  echo "  The bare tree will not start without them; this is not a pass."; \
	fi
	$(call copy-runtime-dlls,$(BARE_DIR))
	@printf '\n✓ Bare tree: %s (core + fonts + themes, no plugins)\n\n' '$(BARE_DIR)'
