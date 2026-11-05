cmake_minimum_required(VERSION 3.22)

project(cdin_composition VERSION 0.1.0 LANGUAGES C)

include(CTest)
find_package(PkgConfig REQUIRED)
find_package(Lua 5.4 REQUIRED)

set(CDIN_KERNEL_MIN_VERSION "1.2.1" CACHE STRING "Minimum Kernel package version")
set(CDIN_BACKEND_SOURCE_DIR
    "${CMAKE_CURRENT_LIST_DIR}/../../backend"
    CACHE PATH "Path to the cdin-editor/backend checkout")
set(CDIN_RUNTIME_ROOT "" CACHE PATH "Installed Runtime Lua module root")

if(NOT IS_DIRECTORY "${CDIN_BACKEND_SOURCE_DIR}")
    message(FATAL_ERROR
        "Backend source checkout not found at '${CDIN_BACKEND_SOURCE_DIR}'. "
        "Set CDIN_BACKEND_SOURCE_DIR to the cdin-editor/backend checkout.")
endif()
if(NOT EXISTS "${CDIN_BACKEND_SOURCE_DIR}/CMakeLists.txt")
    message(FATAL_ERROR
        "CDIN_BACKEND_SOURCE_DIR does not contain CMakeLists.txt: "
        "${CDIN_BACKEND_SOURCE_DIR}")
endif()

pkg_check_modules(CDIN_KERNEL REQUIRED IMPORTED_TARGET
    "cdin-kernel>=${CDIN_KERNEL_MIN_VERSION}")

set(CDIN_WITH_LUA ON CACHE BOOL
    "Build Backend with its Lua 5.4 Runtime host" FORCE)
add_subdirectory("${CDIN_BACKEND_SOURCE_DIR}"
    "${CMAKE_CURRENT_BINARY_DIR}/backend" EXCLUDE_FROM_ALL)

if(NOT TARGET cdin::backend)
    message(FATAL_ERROR
        "Backend checkout did not define cdin::backend. "
        "Check CDIN_BUILD_BACKEND and the Backend package version.")
endif()

add_executable(cdin composition.c)
target_compile_features(cdin PRIVATE c_std_11)
target_link_libraries(cdin PRIVATE cdin::backend)
target_compile_definitions(cdin PRIVATE
    CDIN_VERSION="${PROJECT_VERSION}"
    CDIN_DEFAULT_RUNTIME_ROOT="${CDIN_RUNTIME_ROOT}")

if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(cdin PRIVATE
        -Wall -Wextra -Wshadow -Wconversion -Wstrict-prototypes
        -Wformat=2 -Wpedantic -Werror)
elseif(MSVC)
    target_compile_options(cdin PRIVATE /W4 /WX)
endif()

if(BUILD_TESTING)
    add_test(NAME composition_cli_help COMMAND cdin --help)
    add_test(NAME composition_cli_version COMMAND cdin --version)
endif()
