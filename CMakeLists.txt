cmake_minimum_required(VERSION 3.22)

project(cdin VERSION 0.1.0 LANGUAGES C)

option(CDIN_BUILD_COMPOSITION "Build the cdin composition-root executable" ON)

if(NOT CDIN_BUILD_COMPOSITION)
    message(FATAL_ERROR "The cdin repository is a composition root; CDIN_BUILD_COMPOSITION=OFF is unsupported")
endif()

enable_testing()
add_subdirectory(composition)
