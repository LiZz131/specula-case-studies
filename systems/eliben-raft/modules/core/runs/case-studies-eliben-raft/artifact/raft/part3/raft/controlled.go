package raft

import (
	"encoding/gob"
	"fmt"
	"sort"
	"strconv"
	"strings"
)

// Per-election vote counters. The stock startElection keeps votesReceived in
// the goroutine closure, so a later election does not reset an in-flight
// reply's counter. Keyed by the term captured when that election started.
var ctrlVotes = map[*ConsensusModule]map[int]int{}

func noteControlledElection(cm *ConsensusModule) {
	if ctrlVotes[cm] == nil {
		ctrlVotes[cm] = map[int]int{}
	}
	ctrlVotes[cm][cm.currentTerm] = 1
}

// onVoteReply is the body of the RequestVote reply goroutine (raft.go).
// Expects cm.mu to be held. F2a is the comparison against savedCurrentTerm.
func (cm *ConsensusModule) onVoteReply(savedCurrentTerm int, reply RequestVoteReply, votesReceived *int) {
	cm.dlog("received RequestVoteReply %+v", reply)
	if cm.state != Candidate {
		cm.dlog("while waiting for reply, state = %v", cm.state)
		return
	}
	if reply.Term > savedCurrentTerm {
		cm.dlog("term out of date in RequestVoteReply")
		cm.becomeFollower(reply.Term)
		return
	} else if reply.Term == savedCurrentTerm {
		if reply.VoteGranted {
			*votesReceived++
			if *votesReceived*2 > len(cm.peerIds)+1 {
				cm.dlog("wins election with %d votes", *votesReceived)
				cm.startLeader()
			}
		}
	}
}

// onAEReply is the body of the AppendEntries reply goroutine.
// Expects cm.mu to be held. Returns whether commitIndex advanced.
func (cm *ConsensusModule) onAEReply(peerId int, savedCurrentTerm int, ni int, entries []LogEntry, reply AppendEntriesReply) bool {
	if reply.Term > cm.currentTerm {
		cm.dlog("term out of date in heartbeat reply")
		cm.becomeFollower(reply.Term)
		return false
	}
	if cm.state == Leader && savedCurrentTerm == reply.Term {
		if reply.Success {
			cm.nextIndex[peerId] = ni + len(entries)
			cm.matchIndex[peerId] = cm.nextIndex[peerId] - 1
			savedCommitIndex := cm.commitIndex
			for i := cm.commitIndex + 1; i < len(cm.log); i++ {
				if cm.log[i].Term == cm.currentTerm {
					matchCount := 1
					for _, id := range cm.peerIds {
						if cm.matchIndex[id] >= i {
							matchCount++
						}
					}
					if matchCount*2 > len(cm.peerIds)+1 {
						cm.commitIndex = i
					}
				}
			}
			cm.dlog("AppendEntries reply from %d success: nextIndex := %v, matchIndex := %v; commitIndex := %d", peerId, cm.nextIndex, cm.matchIndex, cm.commitIndex)
			if cm.commitIndex != savedCommitIndex {
				cm.dlog("leader sets commitIndex := %d", cm.commitIndex)
				return true
			}
			return false
		}
		if reply.ConflictTerm >= 0 {
			lastIndexOfTerm := -1
			for i := len(cm.log) - 1; i >= 0; i-- {
				if cm.log[i].Term == reply.ConflictTerm {
					lastIndexOfTerm = i
					break
				}
			}
			if lastIndexOfTerm >= 0 {
				cm.nextIndex[peerId] = lastIndexOfTerm + 1
			} else {
				cm.nextIndex[peerId] = reply.ConflictIndex
			}
		} else {
			cm.nextIndex[peerId] = reply.ConflictIndex
		}
		cm.dlog("AppendEntries reply from %d !success: nextIndex := %d", peerId, ni-1)
	}
	return false
}

// OutMsg is one libc send. Peer is the SandTable node id (n1 → 1).
type OutMsg struct {
	Peer int
	Data string
}

func NewControlled(id int, peers []int) *ConsensusModule {
	controlledReplay = true
	gob.Register("")
	ready := make(chan any)
	commitCh := make(chan CommitEntry, 64)
	return NewConsensusModule(id, peers, nil, NewMapStorage(), ready, commitCh)
}

func (cm *ConsensusModule) snapshotAEsLocked() []OutMsg {
	if cm.state != Leader {
		return nil
	}
	saved := cm.currentTerm
	out := make([]OutMsg, 0, len(cm.peerIds))
	for _, peerId := range cm.peerIds {
		ni := cm.nextIndex[peerId]
		prevLogIndex := ni - 1
		prevLogTerm := -1
		var entries []LogEntry
		if prevLogIndex >= 0 && prevLogIndex < len(cm.log) {
			prevLogTerm = cm.log[prevLogIndex].Term
		}
		if ni >= 0 && ni < len(cm.log) {
			entries = append([]LogEntry(nil), cm.log[ni:]...)
		}
		args := AppendEntriesArgs{
			Term:         saved,
			LeaderId:     cm.id,
			PrevLogIndex: prevLogIndex,
			PrevLogTerm:  prevLogTerm,
			Entries:      entries,
			LeaderCommit: cm.commitIndex,
		}
		out = append(out, OutMsg{Peer: peerId, Data: encodeAE(args)})
	}
	return out
}

func (cm *ConsensusModule) ControlledTimeout() []OutMsg {
	cm.mu.Lock()
	defer cm.mu.Unlock()
	if cm.state != Follower && cm.state != Candidate {
		return nil
	}
	cm.startElection()
	saved := cm.currentTerm
	lastIdx, lastTerm := cm.lastLogIndexAndTerm()
	out := make([]OutMsg, 0, len(cm.peerIds))
	for _, peerId := range cm.peerIds {
		args := RequestVoteArgs{
			Term:         saved,
			CandidateId:  cm.id,
			LastLogIndex: lastIdx,
			LastLogTerm:  lastTerm,
		}
		out = append(out, OutMsg{Peer: peerId, Data: encodeRV(args)})
	}
	return out
}

func (cm *ConsensusModule) ControlledHeartbeat() []OutMsg {
	cm.mu.Lock()
	defer cm.mu.Unlock()
	return cm.snapshotAEsLocked()
}

func (cm *ConsensusModule) ControlledSubmit(command string) []OutMsg {
	cm.mu.Lock()
	defer cm.mu.Unlock()
	if cm.state != Leader {
		return nil
	}
	cm.log = append(cm.log, LogEntry{Command: command, Term: cm.currentTerm})
	cm.persistToStorage()
	return cm.snapshotAEsLocked()
}

func (cm *ConsensusModule) ControlledDeliver(payload string) ([]OutMsg, error) {
	fields := strings.Fields(payload)
	if len(fields) == 0 {
		return nil, fmt.Errorf("empty payload")
	}
	switch fields[0] {
	case "RV":
		return cm.deliverRV(fields)
	case "RVR":
		return cm.deliverRVR(fields)
	case "AE":
		return cm.deliverAE(fields)
	default:
		return nil, fmt.Errorf("unknown message %q", fields[0])
	}
}

func (cm *ConsensusModule) deliverRV(fields []string) ([]OutMsg, error) {
	if len(fields) != 5 {
		return nil, fmt.Errorf("RV fields %d", len(fields))
	}
	term, err1 := strconv.Atoi(fields[1])
	cand, err2 := strconv.Atoi(fields[2])
	lastIdx, err3 := strconv.Atoi(fields[3])
	lastTerm, err4 := strconv.Atoi(fields[4])
	if err1 != nil || err2 != nil || err3 != nil || err4 != nil {
		return nil, fmt.Errorf("RV parse")
	}
	args := RequestVoteArgs{Term: term, CandidateId: cand, LastLogIndex: lastIdx, LastLogTerm: lastTerm}
	var reply RequestVoteReply
	if err := cm.RequestVote(args, &reply); err != nil {
		return nil, err
	}
	return []OutMsg{{Peer: cand, Data: encodeRVR(reply, args.Term)}}, nil
}

func (cm *ConsensusModule) deliverRVR(fields []string) ([]OutMsg, error) {
	if len(fields) != 4 {
		return nil, fmt.Errorf("RVR fields %d", len(fields))
	}
	term, err1 := strconv.Atoi(fields[1])
	granted, err2 := strconv.Atoi(fields[2])
	saved, err3 := strconv.Atoi(fields[3])
	if err1 != nil || err2 != nil || err3 != nil {
		return nil, fmt.Errorf("RVR parse")
	}
	reply := RequestVoteReply{Term: term, VoteGranted: granted != 0}
	cm.mu.Lock()
	defer cm.mu.Unlock()
	votes := 0
	if bucket := ctrlVotes[cm]; bucket != nil {
		votes = bucket[saved]
	}
	before := cm.state
	cm.onVoteReply(saved, reply, &votes)
	if ctrlVotes[cm] == nil {
		ctrlVotes[cm] = map[int]int{}
	}
	ctrlVotes[cm][saved] = votes
	if before != Leader && cm.state == Leader {
		return cm.snapshotAEsLocked(), nil
	}
	return nil, nil
}

func (cm *ConsensusModule) deliverAE(fields []string) ([]OutMsg, error) {
	if len(fields) < 7 {
		return nil, fmt.Errorf("AE fields %d", len(fields))
	}
	nums := make([]int, len(fields)-1)
	for i, text := range fields[1:] {
		value, err := strconv.Atoi(text)
		if err != nil {
			return nil, err
		}
		nums[i] = value
	}
	nEntries := nums[5]
	if len(nums) != 6+nEntries {
		return nil, fmt.Errorf("AE entry count")
	}
	entries := make([]LogEntry, nEntries)
	for i := 0; i < nEntries; i++ {
		entries[i] = LogEntry{Term: nums[6+i], Command: "v"}
	}
	args := AppendEntriesArgs{
		Term:         nums[0],
		LeaderId:     nums[1],
		PrevLogIndex: nums[2],
		PrevLogTerm:  nums[3],
		LeaderCommit: nums[4],
		Entries:      entries,
	}
	var reply AppendEntriesReply
	if err := cm.AppendEntries(args, &reply); err != nil {
		return nil, err
	}
	return []OutMsg{{Peer: args.LeaderId, Data: encodeAER(reply, args)}}, nil
}

// ControlledDeliverFrom is Deliver plus the TCP source. The AE-reply closure
// captured peerId, and the wire format does not repeat it.
func (cm *ConsensusModule) ControlledDeliverFrom(from int, payload string) ([]OutMsg, error) {
	fields := strings.Fields(payload)
	if len(fields) == 0 {
		return nil, fmt.Errorf("empty payload")
	}
	if fields[0] != "AER" {
		return cm.ControlledDeliver(payload)
	}
	if len(fields) != 8 {
		return nil, fmt.Errorf("AER fields %d", len(fields))
	}
	nums := make([]int, 7)
	for i := 0; i < 7; i++ {
		value, err := strconv.Atoi(fields[i+1])
		if err != nil {
			return nil, err
		}
		nums[i] = value
	}
	reply := AppendEntriesReply{
		Term:          nums[0],
		Success:       nums[1] != 0,
		ConflictIndex: nums[2],
		ConflictTerm:  nums[3],
	}
	ni := nums[4] + 1
	entries := make([]LogEntry, nums[5])
	saved := nums[6]
	cm.mu.Lock()
	defer cm.mu.Unlock()
	advanced := cm.onAEReply(from, saved, ni, entries, reply)
	if advanced {
		return cm.snapshotAEsLocked(), nil
	}
	return nil, nil
}

func (cm *ConsensusModule) ControlledGet(key string) string {
	cm.mu.Lock()
	defer cm.mu.Unlock()
	switch key {
	case "commitIdx":
		return strconv.Itoa(cm.commitIndex + 1)
	case "currentTerm":
		return strconv.Itoa(cm.currentTerm)
	case "state":
		return strconv.Itoa(int(cm.state))
	case "log":
		if len(cm.log) == 0 {
			return "[]"
		}
		parts := make([]string, len(cm.log))
		for i, entry := range cm.log {
			parts[i] = fmt.Sprintf("(%d, 'v')", entry.Term)
		}
		return "[" + strings.Join(parts, ", ") + "]"
	case "nextIdx", "matchIdx":
		if cm.state != Leader {
			return "{}"
		}
		ids := append([]int(nil), cm.peerIds...)
		sort.Ints(ids)
		parts := make([]string, 0, len(ids))
		for _, id := range ids {
			value := cm.nextIndex[id] + 1
			if key == "matchIdx" {
				value = cm.matchIndex[id] + 1
			}
			parts = append(parts, fmt.Sprintf("'n%d': %d", id, value))
		}
		return "{" + strings.Join(parts, ", ") + "}"
	default:
		return ""
	}
}

func encodeRV(args RequestVoteArgs) string {
	return fmt.Sprintf("RV %d %d %d %d", args.Term, args.CandidateId, args.LastLogIndex, args.LastLogTerm)
}

func encodeRVR(reply RequestVoteReply, savedTerm int) string {
	granted := 0
	if reply.VoteGranted {
		granted = 1
	}
	return fmt.Sprintf("RVR %d %d %d", reply.Term, granted, savedTerm)
}

func encodeAE(args AppendEntriesArgs) string {
	parts := []string{fmt.Sprintf("AE %d %d %d %d %d %d", args.Term, args.LeaderId, args.PrevLogIndex, args.PrevLogTerm, args.LeaderCommit, len(args.Entries))}
	for _, entry := range args.Entries {
		parts = append(parts, strconv.Itoa(entry.Term))
	}
	return strings.Join(parts, " ")
}

func encodeAER(reply AppendEntriesReply, args AppendEntriesArgs) string {
	success := 0
	if reply.Success {
		success = 1
	}
	return fmt.Sprintf("AER %d %d %d %d %d %d %d", reply.Term, success, reply.ConflictIndex, reply.ConflictTerm, args.PrevLogIndex, len(args.Entries), args.Term)
}
