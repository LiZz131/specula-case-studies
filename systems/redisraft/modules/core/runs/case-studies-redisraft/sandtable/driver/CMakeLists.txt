cmake_minimum_required(VERSION 3.16)
project(specula_redisraft_driver C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Stock driver sources are compiled from the SandTable tree but not modified.
set(STOCK_DRIVER "/root/sandtable/systems/WRaft-series/driver" CACHE PATH "SandTable driver sources")
set(TLPI_LIB "/root/sandtable/cmake-build-debug/drivers/tlpi/libtlpi.a" CACHE FILEPATH "Prebuilt tlpi")
get_filename_component(RAFT_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../artifact/redisraft" ABSOLUTE)

set(RAFT_SOURCES
    ${RAFT_ROOT}/src/raft_log.c
    ${RAFT_ROOT}/src/raft_server.c
    ${RAFT_ROOT}/src/raft_node.c
    ${RAFT_ROOT}/src/raft_server_properties.c)

add_library(RedisRaft STATIC ${RAFT_SOURCES})
target_include_directories(RedisRaft PUBLIC ${RAFT_ROOT}/include)
# Same warning level and -O2 as deps/RedisRaft/Makefile LIB_CFLAGS.
target_compile_options(RedisRaft PRIVATE
    -g -O2 -Wall -Wextra -pedantic -Werror -fno-omit-frame-pointer -fsigned-char --coverage)
set_target_properties(RedisRaft PROPERTIES C_STANDARD 99 C_STANDARD_REQUIRED ON C_EXTENSIONS OFF)

set(DRIVER_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/RedisRaft.cpp
    ${STOCK_DRIVER}/main.cpp
    ${STOCK_DRIVER}/Network.cpp
    ${STOCK_DRIVER}/Config.cpp
    ${STOCK_DRIVER}/Repl.cpp
    ${STOCK_DRIVER}/common.cpp
    ${STOCK_DRIVER}/Node.cpp
    ${STOCK_DRIVER}/TcpNetwork.cpp)

add_executable(RedisRaftDriver ${DRIVER_SOURCES})
target_include_directories(RedisRaftDriver PRIVATE ${STOCK_DRIVER} ${RAFT_ROOT}/include)
target_compile_options(RedisRaftDriver PRIVATE
    -Wall -Wextra -Wno-unused-parameter -Wno-unused-function --coverage)
target_link_options(RedisRaftDriver PRIVATE --coverage -Wl,--export-dynamic)
target_link_libraries(RedisRaftDriver PRIVATE RedisRaft readline gflags ${TLPI_LIB} pthread)
