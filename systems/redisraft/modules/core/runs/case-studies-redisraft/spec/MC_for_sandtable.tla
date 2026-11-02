---- MODULE MC_for_sandtable ----
\* Every Sand* action is in MCNext. Limits match the Specula cfg.
\* MonotonicCommitIndexProp is not used: Crash sets commitIndex back to 0.
EXTENDS base_for_sandtable

CONSTANTS
    MaxTermLimit, MaxTimeoutLimit, RequestLimit, CrashLimit, LoseLimit,
    SnapshotLimit, ConfigChangeLimit, ReadLimit, MaxMsgBufferLimit

VARIABLE counters
mcVars == <<counters>>

MCTimeout(i) ==
    /\ currentTerm[i] < MaxTermLimit
    /\ counters.timeout < MaxTimeoutLimit
    /\ SandTimeout(i)
    /\ counters' = [counters EXCEPT !.timeout = @ + 1]

MCClientRequest(i) ==
    /\ counters.request < RequestLimit
    /\ SandClientRequest(i)
    /\ counters' = [counters EXCEPT !.request = @ + 1]

MCCrash(i) ==
    /\ counters.crash < CrashLimit
    /\ SandCrash(i)
    /\ counters' = [counters EXCEPT !.crash = @ + 1]

MCLoseMessage(m) ==
    /\ counters.lose < LoseLimit
    /\ SandLoseMessage(m)
    /\ counters' = [counters EXCEPT !.lose = @ + 1]

MCTakeSnapshot(i) ==
    /\ counters.snapshot < SnapshotLimit
    /\ SandTakeSnapshot(i)
    /\ counters' = [counters EXCEPT !.snapshot = @ + 1]

MCSendInstallSnapshot(i, j) ==
    /\ counters.snapshot < SnapshotLimit
    /\ SandSendInstallSnapshot(i, j)
    /\ counters' = [counters EXCEPT !.snapshot = @ + 1]

MCProposeAddServer(i, target) ==
    /\ counters.configChange < ConfigChangeLimit
    /\ SandProposeAddServer(i, target)
    /\ counters' = [counters EXCEPT !.configChange = @ + 1]

MCProposeRemoveServer(i, target) ==
    /\ counters.configChange < ConfigChangeLimit
    /\ SandProposeRemoveServer(i, target)
    /\ counters' = [counters EXCEPT !.configChange = @ + 1]

MCClientNonQuorumRead(i) ==
    /\ counters.read < ReadLimit
    /\ SandClientNonQuorumRead(i)
    /\ counters' = [counters EXCEPT !.read = @ + 1]

MsgBufferConstraint ==
    \/ MaxMsgBufferLimit = 0
    \/ BagCardinality(messages) <= MaxMsgBufferLimit

MCInit ==
    /\ SandInit
    /\ counters = [timeout |-> 0, request |-> 0, crash |-> 0,
                   lose |-> 0, snapshot |-> 0, configChange |-> 0, read |-> 0]

MCNext ==
    \/ \E i \in Server :
        \/ MCTimeout(i)
        \/ /\ SandBecomeLeader(i) /\ UNCHANGED counters
        \/ MCClientRequest(i)
        \/ MCClientNonQuorumRead(i)
        \/ /\ SandAdvanceCommitIndex(i) /\ UNCHANGED counters
        \/ MCTakeSnapshot(i)
        \/ /\ SandEndLoadSnapshot(i) /\ UNCHANGED counters
        \/ \E j \in Server : /\ SandAppendEntries(i, j) /\ UNCHANGED counters
        \/ \E j \in Server : MCSendInstallSnapshot(i, j)
        \/ \E target \in Server : MCProposeAddServer(i, target)
        \/ \E target \in Server : MCProposeRemoveServer(i, target)
        \/ MCCrash(i)
    \/ \E m \in BagToSet(messages) :
        \/ /\ SandHandleRequestVoteRequest(m) /\ UNCHANGED counters
        \/ /\ SandHandleRequestVoteResponse(m) /\ UNCHANGED counters
        \/ /\ SandHandleAppendEntriesRequest(m) /\ UNCHANGED counters
        \/ /\ SandHandleAppendEntriesResponse(m) /\ UNCHANGED counters
        \/ /\ SandHandleInstallSnapshotRequest(m) /\ UNCHANGED counters
        \/ /\ SandDropStaleMessage(m) /\ UNCHANGED counters
    \/ \E m \in BagToSet(messages) : MCLoseMessage(m)

MCSpec == MCInit /\ [][MCNext]_<<allVars, scr, mcVars>>

DepthBound == TLCGet("level") < 31

MonotonicTermProp ==
    [][\A i \in Server : currentTerm'[i] >= currentTerm[i]]_allVars

LeaderAppendOnlyProp ==
    [][
        \A i \in Server :
            (state[i] = Leader /\ state'[i] = Leader
             /\ logOffset'[i] = logOffset[i]) =>
                /\ Len(log'[i]) >= Len(log[i])
                /\ SubSeq(log'[i], 1, Len(log[i])) =
                   SubSeq(log[i], 1, Len(log[i]))
    ]_allVars

LeaderCommitCurrentTermProp ==
    [][
        \A i \in Server :
            (state[i] = Leader /\ commitIndex'[i] > commitIndex[i]) =>
                TermAt(log'[i], logOffset'[i], snapshotLastIdx'[i], snapshotLastTerm'[i],
                       commitIndex'[i]) = currentTerm'[i]
    ]_allVars

====
