#!/bin/bash

source $(dirname "$(realpath "$0")")/env.sh
source $START_DOCKER_COMMON_SH "$@"

CLIENT=/root/sandtable/specula-ce/sandtable/driver/build-san/RedisRaftDriver
LAUNCHER=/root/sandtable/specula-ce/sandtable/scripts/interceptor_asan.sh

HOST_CMD="$CONTROLLER -detail -config $CONFIG_FILE -tmpdir $TMPDIR; exit"

# No GCOV_PREFIX: this binary is not a coverage build, and its counters
# must not land in the coverage round.
cat <<EOF | "$SPSSH_SH" -H -S -q -t -e -s -r "$HOST_CMD" -w "$TMPDIR" root@n{1,2,3}
cd $TESTCASE_DIR
export PROGRAM_PATH=$CLIENT
export ASAN_OPTIONS=detect_leaks=0
$LAUNCHER -config $CONFIG_FILE $CLIENT -config $CONFIG_FILE -detail -name "n\${SSH_NO}"; exit
EOF

source $WAIT_TMUX_COMMON_SH
