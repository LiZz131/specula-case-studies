---- MODULE MC_for_sandtable ----
\* Bounded checker over base_for_sandtable.
\* Same numeric bounds as MC.cfg. AppendEntriesAll is the code's
\* raft_send_appendentries_all, so it is not gated by BroadcastLimit
\* (that counter gated the nondeterministic subset broadcast). The
\* message-buffer constraint still limits how many sends are in flight.
EXTENDS base_for_sandtable

CONSTANTS
    MaxTimeoutLimit, RequestLimit, CrashLimit, LoseLimit, DuplicateLimit,
    SnapshotLimit, BroadcastLimit, MaxMsgCount

VARIABLE counters
mcVars == <<counters>>

MCTimeout(i) ==
    /\ counters.timeout < MaxTimeoutLimit
    /\ SandTimeout(i)
    /\ counters' = [counters EXCEPT !.timeout = @ + 1]

MCClientRequest(i, v) ==
    /\ counters.request < RequestLimit
    /\ SandClientRequest(i, v)
    /\ counters' = [counters EXCEPT !.request = @ + 1]

MCTakeSnapshot(i) ==
    /\ counters.snapshot < SnapshotLimit
    /\ SandTakeSnapshot(i)
    /\ counters' = [counters EXCEPT !.snapshot = @ + 1]

MCAppendEntriesAll(i) ==
    /\ SandAppendEntriesAll(i)
    /\ UNCHANGED counters

MCHandleRequestVoteRequest(i, j, m) ==
    /\ SandHandleRequestVoteRequest(i, j, m) /\ UNCHANGED counters
MCHandleRequestVoteResponse(i, j, m) ==
    /\ SandHandleRequestVoteResponse(i, j, m) /\ UNCHANGED counters
MCHandleAppendEntriesRequest(i, j, m) ==
    /\ SandHandleAppendEntriesRequest(i, j, m) /\ UNCHANGED counters
MCHandleAppendEntriesResponse(i, j, m) ==
    /\ SandHandleAppendEntriesResponse(i, j, m) /\ UNCHANGED counters
MCHandleInstallSnapshot(i, j, m) ==
    /\ SandHandleInstallSnapshot(i, j, m) /\ UNCHANGED counters

MCLoseMessage(m) ==
    /\ counters.lose < LoseLimit
    /\ SandLoseMessage(m)
    /\ counters' = [counters EXCEPT !.lose = @ + 1]

MsgBufferConstraint == BagCardinality(messages) <= MaxMsgCount

MCInit ==
    /\ SandInit
    /\ counters = [timeout |-> 0, request |-> 0, crash |-> 0,
                   lose |-> 0, duplicate |-> 0, snapshot |-> 0,
                   broadcast |-> 0]

MCNext ==
    \/ \E i \in Server : MCTimeout(i)
    \/ \E i \in Server, v \in Value : MCClientRequest(i, v)
    \/ \E i \in Server : MCAppendEntriesAll(i)
    \/ \E i \in Server : MCTakeSnapshot(i)
    \/ \E m \in BagToSet(messages) : MCHandleRequestVoteRequest(m.mdest, m.msource, m)
    \/ \E m \in BagToSet(messages) : MCHandleRequestVoteResponse(m.mdest, m.msource, m)
    \/ \E m \in BagToSet(messages) : MCHandleAppendEntriesRequest(m.mdest, m.msource, m)
    \/ \E m \in BagToSet(messages) : MCHandleAppendEntriesResponse(m.mdest, m.msource, m)
    \/ \E m \in BagToSet(messages) : MCHandleInstallSnapshot(m.mdest, m.msource, m)
    \/ \E m \in BagToSet(messages) : MCLoseMessage(m)

MCSpec == MCInit /\ [][MCNext]_<<allVars, scr, mcVars>>

\* Stop a random simulation at this level so TLC prints the behavior.
\* Level 1 is the initial state. Hunt configs need a commit before a snapshot;
\* 11-step walks almost never reach TakeSnapshot.
DepthBound == TLCGet("level") < 31

\* Same formula as MC.tla. The subscript is allVars, so an update that only
\* touches scr or counters is a stutter for this property.
TermNeverDecreases ==
    [][\A i \in Server : ~crashed[i] => currentTerm'[i] >= currentTerm[i]]_allVars

====
