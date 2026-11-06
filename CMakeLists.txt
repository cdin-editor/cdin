cmake_minimum_required(VERSION 3.22)
project(cdin VERSION 0.2.0 LANGUAGES C)

include(GNUInstallDirs)
include(CTest)

option(CDIN_INSTALL_RUNTIME "Install the pinned Runtime Lua modules" ON)
option(CDIN_ENABLE_GUI_SDL "Compose and test the installable Frontend GUI-SDL adapter" OFF)

# ROOT-007 is PROPOSED: check compatibility of assembled component interfaces.
# https://github.com/cdin-editor/spec/blob/main/docs/components/cdin.md#L28-L28
# The Composition Root never compiles copied component sources.
find_package(m-mdy-m-log 0.1.0 CONFIG REQUIRED)
find_package(cdinFrontend 1.0.0 CONFIG REQUIRED)
find_package(cdinBackend 1.2.0 CONFIG REQUIRED)

add_library(cdin_options STATIC src/cli/options.c)
target_include_directories(cdin_options PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_compile_features(cdin_options PUBLIC c_std_11)

add_executable(cdin
    src/main.c
    src/diagnostics/log.c
    src/integration/frontend_smoke.c)
target_include_directories(cdin PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_compile_features(cdin PRIVATE c_std_11)
target_compile_definitions(cdin PRIVATE
    CDIN_VERSION="${PROJECT_VERSION}"
    CDIN_DEFAULT_RUNTIME_ROOT="${CMAKE_INSTALL_FULL_DATADIR}/cdin/lua")
if(NOT TARGET cdin::frontend_ui_tui)
    message(FATAL_ERROR "The pinned Frontend package must export cdin::frontend_ui_tui")
endif()
target_link_libraries(cdin PRIVATE
    cdin_options
    cdin::backend
    m-mdy-m::log
    cdin::frontend_core
    cdin::frontend_ui_tui)

if(CDIN_ENABLE_GUI_SDL)
    if(NOT TARGET cdin::frontend_ui_gui_sdl)
        message(FATAL_ERROR
            "CDIN_ENABLE_GUI_SDL requires the pinned Frontend package built with CDIN_FRONTEND_BUILD_UI_SDL=ON")
    endif()
    find_package(SDL3 3.2 CONFIG REQUIRED)
    target_sources(cdin PRIVATE src/integration/gui_sdl.c)
    target_link_libraries(cdin PRIVATE cdin::frontend_ui_gui_sdl SDL3::SDL3)
    target_compile_definitions(cdin PRIVATE CDIN_ENABLE_GUI_SDL=1)
endif()

# Resolve installed shared component libraries relative to the executable so
# the packaged tree runs without a developer-specific loader environment.
if(APPLE)
    set_property(TARGET cdin PROPERTY INSTALL_RPATH
        "@loader_path/../${CMAKE_INSTALL_LIBDIR}")
elseif(UNIX)
    set_property(TARGET cdin PROPERTY INSTALL_RPATH
        "\$ORIGIN/../${CMAKE_INSTALL_LIBDIR}")
endif()

function(cdin_enable_strict target)
    if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options(${target} PRIVATE
            -Wall -Wextra -Wshadow -Wconversion -Wstrict-prototypes
            -Wformat=2 -Wpedantic -Werror)
    elseif(MSVC)
        target_compile_options(${target} PRIVATE /W4 /WX)
    endif()
endfunction()
cdin_enable_strict(cdin_options)
cdin_enable_strict(cdin)

install(TARGETS cdin RUNTIME DESTINATION "${CMAKE_INSTALL_BINDIR}")
if(CDIN_INSTALL_RUNTIME)
    set(CDIN_RUNTIME_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/.deps/src/runtime" CACHE PATH
        "Path to the pinned cdin-editor/runtime checkout")
    if(NOT EXISTS "${CDIN_RUNTIME_SOURCE_DIR}/lua/cdin/runtime.lua")
        message(FATAL_ERROR "Pinned Runtime Lua modules are missing at ${CDIN_RUNTIME_SOURCE_DIR}; run make deps")
    endif()
    install(DIRECTORY "${CDIN_RUNTIME_SOURCE_DIR}/lua/"
        DESTINATION "${CMAKE_INSTALL_DATADIR}/cdin/lua")
endif()

if(BUILD_TESTING)
    find_package(Python3 3.11 COMPONENTS Interpreter REQUIRED)
    add_test(NAME cdin_cli_help
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/assert_cli.py"
                "$<TARGET_FILE:cdin>" 0 "Usage:" "-" --help)
    add_test(NAME cdin_cli_version
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/assert_cli.py"
                "$<TARGET_FILE:cdin>" 0 "cdin 0.2.0" "-" --version)
    add_test(NAME cdin_cli_help_describes_frontend_modes
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/assert_cli.py"
                "$<TARGET_FILE:cdin>" 0 "headless|tui" "-" --help)
    add_test(NAME cdin_cli_unknown_option
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/assert_cli.py"
                "$<TARGET_FILE:cdin>" 1 "-" "invalid arguments" --not-a-cdin-option)
    add_test(NAME cdin_cli_missing_runtime_root
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/assert_cli.py"
                "$<TARGET_FILE:cdin>" 1 "-" "invalid arguments" --runtime-root)
    add_test(NAME cdin_cli_missing_runtime_entry
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/assert_cli.py"
                "$<TARGET_FILE:cdin>" 1 "-" "invalid arguments" --runtime-entry)
    add_test(NAME cdin_cli_missing_frontend
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/assert_cli.py"
                "$<TARGET_FILE:cdin>" 1 "-" "invalid arguments" --frontend)
    add_test(NAME cdin_cli_help_describes_trusted_extensions
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/assert_cli.py"
                "$<TARGET_FILE:cdin>" 0 "extension-root" "-" --help)
    add_test(NAME cdin_cli_missing_extension_root
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/assert_cli.py"
                "$<TARGET_FILE:cdin>" 1 "-" "invalid arguments" --extension-root)
    add_test(NAME cdin_cli_missing_load_extension
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/assert_cli.py"
                "$<TARGET_FILE:cdin>" 1 "-" "invalid arguments" --load-extension)
    add_test(NAME cdin_cli_extension_requires_root
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/assert_cli.py"
                "$<TARGET_FILE:cdin>" 1 "-" "invalid arguments" --load-extension demo)
    add_test(NAME cdin_cli_unknown_frontend_is_rejected
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/assert_cli.py"
                "$<TARGET_FILE:cdin>" 3 "-" "not launchable" --frontend unknown)
    add_test(NAME cdin_cli_interactive_launch_is_gated
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/assert_cli.py"
                "$<TARGET_FILE:cdin>" 3 "-" "launch" --frontend tui)

    if(CDIN_ENABLE_GUI_SDL)
        add_test(NAME cdin_cli_gui_sdl_launch_is_gated
            COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/assert_cli.py"
                    "$<TARGET_FILE:cdin>" 3 "-" "experimental" --frontend gui-sdl)
        add_test(NAME cdin_gui_sdl_live_session_smoke
            COMMAND cdin --frontend gui-sdl --check)
        set_tests_properties(cdin_gui_sdl_live_session_smoke PROPERTIES
            ENVIRONMENT "SDL_VIDEODRIVER=dummy;CDIN_RUNTIME_ROOT=${CDIN_RUNTIME_SOURCE_DIR}/lua"
            TIMEOUT 90)
    endif()
    add_test(NAME cdin_headless_frontend_protocol_smoke COMMAND cdin --check)
    set_tests_properties(cdin_headless_frontend_protocol_smoke PROPERTIES
        ENVIRONMENT "CDIN_RUNTIME_ROOT=${CDIN_RUNTIME_SOURCE_DIR}/lua")
    add_test(NAME cdin_trusted_extension_cli_smoke
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/extension_cli_smoke.py"
                "$<TARGET_FILE:cdin>")
    set_tests_properties(cdin_trusted_extension_cli_smoke PROPERTIES
        ENVIRONMENT "CDIN_RUNTIME_ROOT=${CDIN_RUNTIME_SOURCE_DIR}/lua"
        TIMEOUT 60)
    if(UNIX)
        add_test(NAME cdin_tui_live_pty_smoke
            COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/tui_pty_smoke.py"
                    "$<TARGET_FILE:cdin>")
        set_tests_properties(cdin_tui_live_pty_smoke PROPERTIES
            ENVIRONMENT "CDIN_RUNTIME_ROOT=${CDIN_RUNTIME_SOURCE_DIR}/lua"
            TIMEOUT 60)
    elseif(WIN32)
        add_test(NAME cdin_tui_live_conpty_smoke
            COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/tui_conpty_smoke.py"
                    "$<TARGET_FILE:cdin>")
        set_tests_properties(cdin_tui_live_conpty_smoke PROPERTIES
            ENVIRONMENT "CDIN_RUNTIME_ROOT=${CDIN_RUNTIME_SOURCE_DIR}/lua"
            TIMEOUT 90)
    endif()
endif()
