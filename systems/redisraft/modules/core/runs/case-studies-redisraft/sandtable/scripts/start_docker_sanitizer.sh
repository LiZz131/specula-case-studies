#!/bin/bash

source $(dirname "$(realpath "$0")")/env.sh
source $START_DOCKER_COMMON_SH "$@"

CLIENT=/root/sandtable/specula-ce/sandtable/driver/build-san/RedisRaftDriver

HOST_CMD="$CONTROLLER -detail -config $CONFIG_FILE -tmpdir $TMPDIR; exit"

# No GCOV_PREFIX: this binary is not a coverage build, and its counters
# must not land in the coverage round.
# Stock interceptor already LD_PRELOADs libinterceptor.so and wraps malloc.
# Prepending libasan makes every node SEGV at pc 0 during constructors.
# verify_asan_link_order=0 lets the dynamic ASan runtime start after that
# preload; heap-buffer-overflow and UBSan runtime error still fire.
# Leak detection stays off.
cat <<EOF | "$SPSSH_SH" -H -S -q -t -e -s -r "$HOST_CMD" -w "$TMPDIR" root@n{1,2,3}
cd $TESTCASE_DIR
export PROGRAM_PATH=$CLIENT
export ASAN_OPTIONS=detect_leaks=0:verify_asan_link_order=0
$INTERCEPTOR_SH -config $CONFIG_FILE $CLIENT -config $CONFIG_FILE -detail -name "n\${SSH_NO}"; exit
EOF

source $WAIT_TMUX_COMMON_SH
