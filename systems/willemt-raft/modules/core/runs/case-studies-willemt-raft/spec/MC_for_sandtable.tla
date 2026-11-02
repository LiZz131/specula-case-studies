---- MODULE MC_for_sandtable ----
\* Every action of base.tla is scheduled here. The formulas live in
\* base_for_sandtable.tla and are the same protocol updates as base.tla.
\* label records the witness (who, which message, which branch).
EXTENDS base_for_sandtable

CONSTANTS
    MaxTimeoutLimit, RequestLimit, CrashLimit, LoseLimit, DuplicateLimit,
    SnapshotLimit, BroadcastLimit, MaxMsgCount

VARIABLE counters
mcVars == <<counters>>

MCTimeout(i) ==
    /\ counters.timeout < MaxTimeoutLimit
    /\ Timeout(i)
    /\ counters' = [counters EXCEPT !.timeout = @ + 1]

MCClientRequest(i, v) ==
    /\ counters.request < RequestLimit
    /\ ClientRequest(i, v)
    /\ counters' = [counters EXCEPT !.request = @ + 1]

MCBroadcastAppendEntries(i) ==
    /\ counters.broadcast < BroadcastLimit
    /\ BroadcastAppendEntries(i)
    /\ counters' = [counters EXCEPT !.broadcast = @ + 1]

MCCrash(i) ==
    /\ counters.crash < CrashLimit
    /\ Crash(i)
    /\ counters' = [counters EXCEPT !.crash = @ + 1]

MCLoseMessage(m) ==
    /\ counters.lose < LoseLimit
    /\ LoseMessage(m)
    /\ counters' = [counters EXCEPT !.lose = @ + 1]

MCDuplicateMessage(m) ==
    /\ counters.duplicate < DuplicateLimit
    /\ DuplicateMessage(m)
    /\ counters' = [counters EXCEPT !.duplicate = @ + 1]

MCTakeSnapshot(i) ==
    /\ counters.snapshot < SnapshotLimit
    /\ TakeSnapshot(i)
    /\ counters' = [counters EXCEPT !.snapshot = @ + 1]

MCSendAppendEntries(i, j) ==
    /\ SendAppendEntries(i, j) /\ UNCHANGED counters
MCSendInstallSnapshot(i, j) ==
    /\ SendInstallSnapshot(i, j) /\ UNCHANGED counters
MCRecover(i) ==
    /\ Recover(i) /\ UNCHANGED counters
MCHandleRequestVoteRequest(i, j, m) ==
    /\ HandleRequestVoteRequest(i, j, m) /\ UNCHANGED counters
MCHandleRequestVoteResponse(i, j, m) ==
    /\ HandleRequestVoteResponse(i, j, m) /\ UNCHANGED counters
MCHandleAppendEntriesRequest(i, j, m) ==
    /\ HandleAppendEntriesRequest(i, j, m) /\ UNCHANGED counters
MCHandleAppendEntriesResponse(i, j, m) ==
    /\ HandleAppendEntriesResponse(i, j, m) /\ UNCHANGED counters
MCHandleInstallSnapshot(i, j, m) ==
    /\ HandleInstallSnapshot(i, j, m) /\ UNCHANGED counters

MsgBufferConstraint == BagCardinality(messages) <= MaxMsgCount

MCInit ==
    /\ Init
    /\ scr = [pc |-> <<"Init">>, nSent |-> 0]
    /\ label = <<"Init">>
    /\ counters = [timeout |-> 0, request |-> 0, crash |-> 0,
                   lose |-> 0, duplicate |-> 0, snapshot |-> 0,
                   broadcast |-> 0]

MCNext ==
    \/ \E i \in Server : MCTimeout(i)
    \/ \E i \in Server, v \in Value : MCClientRequest(i, v)
    \/ \E i \in Server : MCBroadcastAppendEntries(i)
    \/ \E i \in Server : MCCrash(i)
    \/ \E i \in Server : MCTakeSnapshot(i)
    \/ \E m \in BagToSet(messages) : MCLoseMessage(m)
    \/ \E m \in BagToSet(messages) : MCDuplicateMessage(m)
    \/ \E i, j \in Server : MCSendAppendEntries(i, j)
    \/ \E i, j \in Server : MCSendInstallSnapshot(i, j)
    \/ \E i \in Server : MCRecover(i)
    \/ \E m \in BagToSet(messages) : MCHandleRequestVoteRequest(m.mdest, m.msource, m)
    \/ \E m \in BagToSet(messages) : MCHandleRequestVoteResponse(m.mdest, m.msource, m)
    \/ \E m \in BagToSet(messages) : MCHandleAppendEntriesRequest(m.mdest, m.msource, m)
    \/ \E m \in BagToSet(messages) : MCHandleAppendEntriesResponse(m.mdest, m.msource, m)
    \/ \E m \in BagToSet(messages) : MCHandleInstallSnapshot(m.mdest, m.msource, m)

MCSpec == MCInit /\ [][MCNext]_<<allVars, scr, label, mcVars>>

DepthBound == TLCGet("level") < 31

TermNeverDecreases ==
    [][\A i \in Server : ~crashed[i] => currentTerm'[i] >= currentTerm[i]]_allVars

====
