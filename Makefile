.PHONY: help deps registry registry-gui stack stack-gui configure build install instal test check integration clean package
BUILD_DIR ?= build
ifeq ($(OS),Windows_NT)
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
	@echo "make configure    configure the selected Composition Root profile"
	@echo "make build        build cdin (requires installed components)"
	@echo "make install      install cdin and pinned Runtime Lua modules"
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
	cmake -S . -B "$(BUILD_DIR)" -DCMAKE_BUILD_TYPE=Release \
	  -DCMAKE_INSTALL_PREFIX="$(PREFIX)" \
	  -DCDIN_RUNTIME_SOURCE_DIR="$(CURDIR)/.deps/src/runtime" \
	  -DCDIN_REGISTRY_PROFILE="$(CDIN_FRONTEND_VARIANT)" \
	  -DCDIN_BACKEND_PACKAGE_VERSION="$$($(PYTHON) scripts/registry_version.py backend --profile $(CDIN_FRONTEND_VARIANT))" \
	  -DCDIN_FRONTEND_PACKAGE_VERSION="$$($(PYTHON) scripts/registry_version.py frontend --variant $(CDIN_FRONTEND_VARIANT) --profile $(CDIN_FRONTEND_VARIANT))" \
	  -DCDIN_ENABLE_GUI_SDL="$(if $(filter gui-sdl,$(CDIN_FRONTEND_VARIANT)),ON,OFF)"

build: configure
	cmake --build "$(BUILD_DIR)" --parallel

install: build
	cmake --install "$(BUILD_DIR)"

instal: install

test: stack

check:
	pipeline run check

integration:
	"$(PREFIX)/bin/cdin" --check

package:
	$(PYTHON) scripts/package.py

clean:
	rm -rf "$(BUILD_DIR)" "$(BUILD_DIR)-tests" dist .deps/registry-workspace-* .deps/registry-replay-*
