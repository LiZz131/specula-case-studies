#!/bin/bash
# Instrument eliben/raft with go tool cover and build libeliben.so.
# go build -cover -buildmode=c-shared leaves covermode invalid, so counters
# are inserted in the source and dumped from wraft_gcov_dump.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
SRC="$ROOT/artifact/raft/part3/raft"
BRIDGE="$ROOT/sandtable/driver/bridge"
OUT="$ROOT/sandtable/driver/libeliben.so"
WORK=$(mktemp -d)
COVER="$WORK/src"
mkdir -p "$COVER"
export PATH="${PATH}:/users/bingzhuo/sdk/go/bin"
export GO111MODULE=on

instrument() {
    local base=$1
    local var=$2
    go tool cover -mode=count -var="$var" "$SRC/$base.go" > "$COVER/$base.go"
}

instrument raft RaftCov
instrument server ServerCov
instrument storage StorageCov
instrument controlled ControlledCov
cp "$SRC/go.mod" "$SRC/go.sum" "$COVER/"

cat > "$COVER/cover_dump.go" <<EOF
package raft

import (
    "fmt"
    "io"
    "os"
)

func emitCover(w io.Writer, file string, count []uint32, pos []uint32, nstmt []uint16) {
    for i := range count {
        fmt.Fprintf(w, "%s\\t%d\\t%d\\t%d\\t%d\\n", file, pos[i*3], pos[i*3+1], nstmt[i], count[i])
    }
}

func WriteCoverProfile(path string) error {
    f, err := os.Create(path)
    if err != nil {
        return err
    }
    defer f.Close()
    emitCover(f, "$SRC/raft.go", RaftCov.Count[:], RaftCov.Pos[:], RaftCov.NumStmt[:])
    emitCover(f, "$SRC/server.go", ServerCov.Count[:], ServerCov.Pos[:], ServerCov.NumStmt[:])
    emitCover(f, "$SRC/storage.go", StorageCov.Count[:], StorageCov.Pos[:], StorageCov.NumStmt[:])
    emitCover(f, "$SRC/controlled.go", ControlledCov.Count[:], ControlledCov.Pos[:], ControlledCov.NumStmt[:])
    return nil
}
EOF

cat > "$WORK/go.mod" <<EOF
module elibendriver

go 1.23.1

require github.com/eliben/raft/part3/raft v0.0.0

replace github.com/eliben/raft/part3/raft => ./src
EOF
cp "$BRIDGE/main.go" "$WORK/main.go"
(
    cd "$WORK"
    go build -buildmode=c-shared -o "$OUT" .
)
rm -rf "$WORK"
echo "built $OUT"
