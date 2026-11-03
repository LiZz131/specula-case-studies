---- MODULE MC_for_sandtable ----
\* Every action of base_for_sandtable's Next, plus the partial-persist
\* fault from MC.tla. Counter bounds match that module.
EXTENDS base_for_sandtable

CONSTANTS
    MaxTermLimit, MaxTimeoutLimit, MaxRequestLimit, MaxCrashLimit,
    MaxLoseLimit, MaxAppendLimit, MaxMsgBufferLimit

VARIABLE counters
mcVars == <<counters>>
allVars == vars

MCTimeout(i) ==
    /\ currentTerm[i] + 1 <= MaxTermLimit
    /\ counters.timeout < MaxTimeoutLimit
    /\ SandTimeout(i)
    /\ counters' = [counters EXCEPT !.timeout = @ + 1]

MCClientRequest(i) ==
    /\ counters.request < MaxRequestLimit
    /\ SandClientRequest(i)
    /\ counters' = [counters EXCEPT !.request = @ + 1]

MCCrash(i) ==
    /\ counters.crash < MaxCrashLimit
    /\ SandCrash(i)
    /\ counters' = [counters EXCEPT !.crash = @ + 1]

\* Same crash budget as MC.tla. Writes the term key, then recovers.
MCPartialPersist(i) ==
    /\ counters.crash < MaxCrashLimit
    /\ currentTerm[i] /= persistedTerm[i]
    /\ persistedTerm' = [persistedTerm EXCEPT ![i] = currentTerm[i]]
    /\ UNCHANGED persistedVotedFor
    /\ currentTerm' = [currentTerm EXCEPT ![i] = currentTerm[i]]
    /\ votedFor' = [votedFor EXCEPT ![i] = persistedVotedFor[i]]
    /\ state' = [state EXCEPT ![i] = Follower]
    /\ commitIndex' = [commitIndex EXCEPT ![i] = 0]
    /\ nextIndex' = [nextIndex EXCEPT ![i] = [j \in Server |-> 1]]
    /\ matchIndex' = [matchIndex EXCEPT ![i] = [j \in Server |-> 0]]
    /\ votesGranted' = [votesGranted EXCEPT ![i] = {}]
    /\ scr' = [scr EXCEPT !.pc = <<"PartialPersist", i>>, !.nSent = scr.nSent]
    /\ UNCHANGED <<log, messages>>
    /\ counters' = [counters EXCEPT !.crash = @ + 1]

MCLoseMessage(m) ==
    /\ counters.lose < MaxLoseLimit
    /\ SandLoseMessage(m)
    /\ counters' = [counters EXCEPT !.lose = @ + 1]

MCAppendEntries(i, j) ==
    /\ counters.append < MaxAppendLimit
    /\ SandAppendEntries(i, j)
    /\ counters' = [counters EXCEPT !.append = @ + 1]

MCBecomeLeader(i) ==
    /\ SandBecomeLeader(i) /\ UNCHANGED counters
MCAdvanceCommitIndex(i) ==
    /\ SandAdvanceCommitIndex(i) /\ UNCHANGED counters
MCHandleRequestVoteRequest(i, j, m) ==
    /\ SandHandleRequestVoteRequest(i, j, m) /\ UNCHANGED counters
MCHandleRequestVoteResponse(i, j, m) ==
    /\ SandHandleRequestVoteResponse(i, j, m) /\ UNCHANGED counters
MCHandleAppendEntriesRequest(i, j, m) ==
    /\ SandHandleAppendEntriesRequest(i, j, m) /\ UNCHANGED counters
MCHandleAppendEntriesResponse(i, j, m) ==
    /\ SandHandleAppendEntriesResponse(i, j, m) /\ UNCHANGED counters
MCDropStaleMessage(m) ==
    /\ SandDropStaleMessage(m) /\ UNCHANGED counters

MsgBufferConstraint ==
    BagCardinality(messages) <= MaxMsgBufferLimit

MCInit ==
    /\ SandInit
    /\ counters = [timeout |-> 0, request |-> 0, crash |-> 0,
                   lose |-> 0, append |-> 0]

MCNext ==
    \/ \E i \in Server :
        \/ MCTimeout(i)
        \/ MCBecomeLeader(i)
        \/ MCClientRequest(i)
        \/ MCAdvanceCommitIndex(i)
        \/ MCCrash(i)
        \/ MCPartialPersist(i)
    \/ \E i, j \in Server : MCAppendEntries(i, j)
    \/ \E m \in DOMAIN messages :
        \/ MCHandleRequestVoteRequest(m.mdest, m.msource, m)
        \/ MCHandleRequestVoteResponse(m.mdest, m.msource, m)
        \/ MCHandleAppendEntriesRequest(m.mdest, m.msource, m)
        \/ MCHandleAppendEntriesResponse(m.mdest, m.msource, m)
        \/ MCDropStaleMessage(m)
        \/ MCLoseMessage(m)

MCSpec == MCInit /\ [][MCNext]_<<allVars, scr, mcVars>>

DepthBound == TLCGet("level") < 31

CandidateVotedForSelfInv == CandidateVotedForSelf
CommitIndexBoundInv == CommitIndexBound
LeaderTermPositiveInv == LeaderTermPositive
NextIndexPositiveInv == NextIndexPositive
PersistedTermConsistencyInv == PersistedTermConsistency

====
