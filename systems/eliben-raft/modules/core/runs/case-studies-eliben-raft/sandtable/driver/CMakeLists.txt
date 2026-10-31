cmake_minimum_required(VERSION 3.16)
project(specula_eliben_driver C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(STOCK_DRIVER "/root/sandtable/systems/WRaft-series/driver" CACHE PATH "SandTable driver sources")
set(TLPI_LIB "/root/sandtable/cmake-build-debug/drivers/tlpi/libtlpi.a" CACHE FILEPATH "Prebuilt tlpi")

# Coverage and sanitizer are separate binaries. Never pass both.
option(SPECULA_SANITIZE "Build the C++ driver with -fsanitize=address,undefined and no coverage" OFF)

set(DRIVER_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/ElibenRaft.cpp
    ${STOCK_DRIVER}/main.cpp
    ${STOCK_DRIVER}/Network.cpp
    ${STOCK_DRIVER}/Config.cpp
    ${STOCK_DRIVER}/Repl.cpp
    ${STOCK_DRIVER}/common.cpp
    ${STOCK_DRIVER}/Node.cpp
    ${STOCK_DRIVER}/TcpNetwork.cpp)

add_executable(ElibenRaftDriver ${DRIVER_SOURCES})
target_include_directories(ElibenRaftDriver PRIVATE ${STOCK_DRIVER})
if(SPECULA_SANITIZE)
    target_compile_options(ElibenRaftDriver PRIVATE
        -g -O1 -Wall -Wextra -Wno-unused-parameter -Wno-unused-function -fno-omit-frame-pointer
        -fsanitize=address,undefined)
    target_link_options(ElibenRaftDriver PRIVATE
        -fsanitize=address,undefined -Wl,--export-dynamic)
else()
    target_compile_options(ElibenRaftDriver PRIVATE
        -Wall -Wextra -Wno-unused-parameter -Wno-unused-function)
    target_link_options(ElibenRaftDriver PRIVATE -Wl,--export-dynamic)
endif()
target_link_libraries(ElibenRaftDriver PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/libeliben.so
    readline gflags ${TLPI_LIB} pthread)
set_target_properties(ElibenRaftDriver PROPERTIES
    BUILD_RPATH "$ORIGIN"
    INSTALL_RPATH "$ORIGIN")
add_custom_command(TARGET ElibenRaftDriver POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        ${CMAKE_CURRENT_SOURCE_DIR}/libeliben.so
        $<TARGET_FILE_DIR:ElibenRaftDriver>/libeliben.so)
