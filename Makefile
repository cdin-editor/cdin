.PHONY: help deps registry registry-gui stack stack-gui configure build install test check integration clean package
BUILD_DIR ?= build
PREFIX ?= $(CURDIR)/.deps/install
CDIN_FRONTEND_VARIANT ?= tui

help:
	@printf '%s\n' 'make deps         checkout immutable non-component build dependencies' \
	  'make registry     resolve and prepare the selected Registry component workspace' \
	  'make registry-gui resolve and prepare the GUI-SDL + TUI workspace' \
	  'make stack        build/test/install the selected component profile' \
	  'make stack-gui    build/test/install the GUI-SDL + TUI profile' \
	  'make configure    configure the selected Composition Root profile' \
	  'make build        build cdin (requires installed components)' \
	  'make install      install cdin and pinned Runtime Lua modules' \
	  'make test         run full-stack integration and lifecycle E2E tests' \
	  'make check        run Pipeline checks and architecture boundaries' \
	  'make integration  run installed Backend/Runtime lifecycle smoke test' \
	  'make package      create a source archive'

deps:
	python3 scripts/deps.py

registry: deps
	CDIN_FRONTEND_VARIANT="$(CDIN_FRONTEND_VARIANT)" python3 scripts/registry.py --profile "$(CDIN_FRONTEND_VARIANT)"

registry-gui: deps
	python3 scripts/registry.py --profile gui-sdl

stack: registry
	python3 scripts/build_stack.py --profile "$(CDIN_FRONTEND_VARIANT)"

stack-gui: registry-gui
	python3 scripts/build_stack.py --profile gui-sdl

configure: registry
	cmake -S . -B "$(BUILD_DIR)" -DCMAKE_BUILD_TYPE=Release \
	  -DCMAKE_INSTALL_PREFIX="$(PREFIX)" \
	  -DCDIN_RUNTIME_SOURCE_DIR="$(CURDIR)/.deps/src/runtime" \
	  -DCDIN_REGISTRY_PROFILE="$(CDIN_FRONTEND_VARIANT)" \
	  -DCDIN_BACKEND_PACKAGE_VERSION="$$(python3 scripts/registry_version.py backend --profile $(CDIN_FRONTEND_VARIANT))" \
	  -DCDIN_FRONTEND_PACKAGE_VERSION="$$(python3 scripts/registry_version.py frontend --variant tui --profile $(CDIN_FRONTEND_VARIANT))" \
	  -DCDIN_ENABLE_GUI_SDL="$(if $(filter gui-sdl,$(CDIN_FRONTEND_VARIANT)),ON,OFF)"

build: configure
	cmake --build "$(BUILD_DIR)" --parallel

install: build
	cmake --install "$(BUILD_DIR)"

test: stack

check:
	pipeline run check

integration:
	"$(PREFIX)/bin/cdin" --check

package:
	python3 scripts/package.py

clean:
	rm -rf "$(BUILD_DIR)" "$(BUILD_DIR)-tests" dist .deps/registry-workspace-* .deps/registry-replay-*
