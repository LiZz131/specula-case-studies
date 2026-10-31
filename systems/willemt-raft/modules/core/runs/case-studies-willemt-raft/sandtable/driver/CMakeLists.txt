cmake_minimum_required(VERSION 3.16)
project(specula_wraft_driver C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Stock driver sources are compiled from the SandTable tree but not modified.
set(STOCK_DRIVER "/root/sandtable/systems/WRaft-series/driver" CACHE PATH "SandTable driver sources")
set(TLPI_LIB "/root/sandtable/cmake-build-debug/drivers/tlpi/libtlpi.a" CACHE FILEPATH "Prebuilt tlpi")
get_filename_component(RAFT_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../artifact/raft" ABSOLUTE)

set(RAFT_SOURCES
    ${RAFT_ROOT}/src/raft_log.c
    ${RAFT_ROOT}/src/raft_server.c
    ${RAFT_ROOT}/src/raft_node.c
    ${RAFT_ROOT}/src/raft_server_properties.c)

add_library(WRaft STATIC ${RAFT_SOURCES})
target_include_directories(WRaft PUBLIC ${RAFT_ROOT}/include)
target_compile_options(WRaft PRIVATE
    -g -Wall -Wextra -Werror -Wno-unused-parameter -Wno-unused-function --coverage)
set_target_properties(WRaft PROPERTIES C_STANDARD 99 C_STANDARD_REQUIRED ON C_EXTENSIONS OFF)

set(DRIVER_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/WRaft.cpp
    ${STOCK_DRIVER}/main.cpp
    ${STOCK_DRIVER}/Network.cpp
    ${STOCK_DRIVER}/Config.cpp
    ${STOCK_DRIVER}/Repl.cpp
    ${STOCK_DRIVER}/common.cpp
    ${STOCK_DRIVER}/Node.cpp
    ${STOCK_DRIVER}/TcpNetwork.cpp)

add_executable(WRaftDriver ${DRIVER_SOURCES})
target_include_directories(WRaftDriver PRIVATE ${STOCK_DRIVER} ${RAFT_ROOT}/include)
target_compile_options(WRaftDriver PRIVATE
    -Wall -Wextra -Werror -Wno-unused-parameter -Wno-unused-function --coverage)
target_link_options(WRaftDriver PRIVATE --coverage -Wl,--export-dynamic)
target_link_libraries(WRaftDriver PRIVATE WRaft readline gflags ${TLPI_LIB} pthread)
