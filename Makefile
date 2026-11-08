.PHONY: help deps registry registry-gui stack stack-gui configure build install instal test check integration clean package
BUILD_DIR ?= build
# Native Windows shells may not expose the OS variable to GNU Make consistently.
# ComSpec is a second reliable signal; keep python3 for Unix environments.
ifeq ($(OS),Windows_NT)
PYTHON ?= python
else ifneq ($(strip $(ComSpec)),)
PYTHON ?= python
else
PYTHON ?= python3
endif
PREFIX ?= $(CURDIR)/.deps/install
CDIN_FRONTEND_VARIANT ?= tui

help:
	@echo "make deps         checkout immutable non-component build dependencies"
	@echo "make registry     resolve and prepare the selected Registry component workspace"
	@echo "make registry-gui resolve and prepare the GUI-SDL + TUI workspace"
	@echo "make stack        build/test/install the selected component profile"
	@echo "make stack-gui    build/test/install the GUI-SDL + TUI profile"
	@echo "make configure    configure CDIN after its components are installed"
	@echo "make build        build cdin (requires installed components)"
	@echo "make install      build, test and install the complete selected profile"
	@echo "make instal       compatibility alias for install"
	@echo "make test         run full-stack integration and lifecycle E2E tests"
	@echo "make check        run Pipeline checks and architecture boundaries"
	@echo "make integration  run installed Backend/Runtime lifecycle smoke test"
	@echo "make package      create a source archive"

deps:
	$(PYTHON) scripts/deps.py

registry: deps
	$(PYTHON) scripts/registry.py --profile "$(CDIN_FRONTEND_VARIANT)"

registry-gui: deps
	$(PYTHON) scripts/registry.py --profile gui-sdl

stack: registry
	$(PYTHON) scripts/build_stack.py --profile "$(CDIN_FRONTEND_VARIANT)"

stack-gui: registry-gui
	$(PYTHON) scripts/build_stack.py --profile gui-sdl

configure: registry
	$(PYTHON) scripts/configure.py --build-dir "$(BUILD_DIR)" --profile "$(CDIN_FRONTEND_VARIANT)"

build: configure
	cmake --build "$(BUILD_DIR)" --parallel

# build_stack.py owns the full ordered component build, tests, CDIN build and
# installation. Make the common install entry point perform that complete
# operation rather than trying to configure CDIN before its component packages
# have been built and installed.
install: stack
	@echo "CDIN profile $(CDIN_FRONTEND_VARIANT) installed in $(PREFIX)"

instal: install

test: stack

check:
	pipeline run check

integration:
	"$(PREFIX)/bin/cdin" --check

package:
	$(PYTHON) scripts/package.py

clean:
	$(PYTHON) scripts/clean.py --build-dir "$(BUILD_DIR)"
