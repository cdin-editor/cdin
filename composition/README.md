# Composition Root

This directory is the new executable boundary. It owns process arguments and startup only. Editing, keymaps, commands, plugins and UI policy remain in Runtime and peer repositories.

The executable uses only Backend's public lifecycle API. The --check command exercises Backend/Runtime startup and orderly shutdown; it does not claim that a frontend is connected.

Configure with an installed Kernel package and Backend dependencies visible to pkg-config:

```sh
cmake -S composition -B build/composition -DCDIN_RUNTIME_ROOT=/absolute/path/to/runtime/lua
cmake --build build/composition
ctest --test-dir build/composition --output-on-failure
```

Set CDIN_RUNTIME_ROOT at runtime to override the configured Lua module root.
