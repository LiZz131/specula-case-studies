package main

/*
#cgo LDFLAGS: -pthread
*/
import "C"

import (
	"fmt"
	"os"
	"path/filepath"
	"unsafe"

	raft "github.com/eliben/raft/part3/raft"
)

func main() {}

var (
	cm      *raft.ConsensusModule
	pending []raft.OutMsg
)

func setPending(msgs []raft.OutMsg, err error) C.int {
	if err != nil {
		fmt.Fprintf(os.Stderr, "eliben: %v\n", err)
		pending = nil
		return -1
	}
	pending = append(pending[:0], msgs...)
	return 0
}

//export ElibenInit
func ElibenInit(id C.int, npeers C.int, peers *C.int) {
	raw := unsafe.Slice(peers, int(npeers))
	ps := make([]int, len(raw))
	for i, peer := range raw {
		ps[i] = int(peer)
	}
	cm = raft.NewControlled(int(id), ps)
	pending = nil
}

//export ElibenTimeout
func ElibenTimeout() C.int {
	if cm == nil {
		return -1
	}
	return setPending(cm.ControlledTimeout(), nil)
}

//export ElibenHeartbeat
func ElibenHeartbeat() C.int {
	if cm == nil {
		return -1
	}
	return setPending(cm.ControlledHeartbeat(), nil)
}

//export ElibenSubmit
func ElibenSubmit(cmd *C.char) C.int {
	if cm == nil {
		return -1
	}
	return setPending(cm.ControlledSubmit(C.GoString(cmd)), nil)
}

//export ElibenDeliver
func ElibenDeliver(from C.int, data *C.char, n C.int) C.int {
	if cm == nil {
		return -1
	}
	payload := C.GoStringN(data, n)
	msgs, err := cm.ControlledDeliverFrom(int(from), payload)
	return setPending(msgs, err)
}

//export ElibenPop
func ElibenPop(dst *C.int, buf *C.char, cap C.int) C.int {
	if len(pending) == 0 {
		return 0
	}
	msg := pending[0]
	pending = pending[1:]
	if len(msg.Data) >= int(cap) {
		fmt.Fprintf(os.Stderr, "eliben: outgoing message too large\n")
		return -1
	}
	*dst = C.int(msg.Peer)
	out := unsafe.Slice((*byte)(unsafe.Pointer(buf)), int(cap))
	copy(out, msg.Data)
	return C.int(len(msg.Data))
}

//export ElibenGet
func ElibenGet(key *C.char) *C.char {
	text := ""
	if cm != nil {
		text = cm.ControlledGet(C.GoString(key))
	}
	// C.CString allocates with malloc. The driver frees the pointer.
	return C.CString(text)
}

//export ElibenDumpCover
func ElibenDumpCover() {
	dir := os.Getenv("GOCOVERDIR")
	if dir == "" {
		return
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		fmt.Fprintf(os.Stderr, "eliben: cover dir: %v\n", err)
		return
	}
	path := filepath.Join(dir, fmt.Sprintf("cover.%d.tsv", os.Getpid()))
	if err := raft.WriteCoverProfile(path); err != nil {
		fmt.Fprintf(os.Stderr, "eliben: cover profile: %v\n", err)
	}
}
