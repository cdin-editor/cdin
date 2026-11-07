.PHONY: help deps registry stack configure build install test check integration clean package
BUILD_DIR ?= build
PREFIX ?= $(CURDIR)/.deps/install

help:
	@printf '%s\n' 'make deps         checkout immutable non-component build dependencies' \
	  'make registry     resolve and prepare the Registry component workspace' \
	  'make stack        build/test/install the full pinned component stack' \
	  'make configure    configure the Composition Root' \
	  'make build        build cdin (requires installed components)' \
	  'make install      install cdin and pinned Runtime Lua modules' \
	  'make test         run full-stack integration and lifecycle E2E tests' \
	  'make check        run Pipeline checks and architecture boundaries' \
	  'make integration  run installed Backend/Runtime lifecycle smoke test' \
	  'make package      create a source archive'

deps:
	python3 scripts/deps.py

registry: deps
	python3 scripts/registry.py

stack: registry
	python3 scripts/build_stack.py

configure:
	cmake -S . -B "$(BUILD_DIR)" -DCMAKE_BUILD_TYPE=Release \
	  -DCMAKE_INSTALL_PREFIX="$(PREFIX)" -DCDIN_RUNTIME_SOURCE_DIR="$(CURDIR)/.deps/src/runtime"

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
