---- MODULE MC_for_sandtable ----
\* Bounded random walk over the controllable subset of base_for_sandtable.
\* MCNext only contains actions the stock RedisRaft driver can execute:
\* timeout, client append, send-all, message handlers, and losing the
\* single message on a TCP channel.
\* Crash, snapshot, membership, and non-quorum read stay out. Their limits
\* are still conjuncts of MCInit so each hunt cfg keeps its original numbers.
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

MCLoseMessage(m) ==
    /\ counters.lose < LoseLimit
    /\ SandLoseMessage(m)
    /\ counters' = [counters EXCEPT !.lose = @ + 1]

MsgBufferConstraint ==
    \/ MaxMsgBufferLimit = 0
    \/ BagCardinality(messages) <= MaxMsgBufferLimit

MCInit ==
    /\ SandInit
    /\ counters = [timeout |-> 0, request |-> 0, crash |-> 0,
                   lose |-> 0, snapshot |-> 0, configChange |-> 0, read |-> 0]
    \* Record the hunt limits MCNext does not read.
    /\ CrashLimit \in Nat /\ SnapshotLimit \in Nat
    /\ ConfigChangeLimit \in Nat /\ ReadLimit \in Nat

MCNext ==
    \/ \E i \in Server : MCTimeout(i)
    \/ \E i \in Server : MCClientRequest(i)
    \/ \E i \in Server : MCAppendEntriesAll(i)
    \/ \E m \in BagToSet(messages) : MCHandleRequestVoteRequest(m.mdest, m.msource, m)
    \/ \E m \in BagToSet(messages) : MCHandleRequestVoteResponse(m.mdest, m.msource, m)
    \/ \E m \in BagToSet(messages) : MCHandleAppendEntriesRequest(m.mdest, m.msource, m)
    \/ \E m \in BagToSet(messages) : MCHandleAppendEntriesResponse(m.mdest, m.msource, m)
    \/ \E m \in BagToSet(messages) : MCLoseMessage(m)

MCSpec == MCInit /\ [][MCNext]_<<allVars, scr, mcVars>>

DepthBound == TLCGet("level") < 31

MonotonicCommitIndexProp ==
    [][\A i \in Server : commitIndex'[i] >= commitIndex[i]]_allVars

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
