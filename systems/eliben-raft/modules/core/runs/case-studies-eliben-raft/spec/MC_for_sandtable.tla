---- MODULE MC_for_sandtable ----
\* Controllable subset of base_for_sandtable.
\* MCNext is timeout, client append, send-all, the four message handlers,
\* and losing the only message on a TCP channel.
\* Crash and PartialPersist stay out: the driver has no restart command.
\* MaxCrashLimit is still recorded so each hunt cfg keeps its number.
\* Random walks do not execute the crash-recovery families F1b and F1c.
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

MCAppendEntriesAll(i) ==
    /\ counters.append < MaxAppendLimit
    /\ SandAppendEntriesAll(i)
    /\ counters' = [counters EXCEPT !.append = @ + 1]

MCHandleRequestVoteRequest(i, j, m) ==
    /\ SandHandleRequestVoteRequest(i, j, m) /\ UNCHANGED counters
MCHandleRequestVoteResponse(i, j, m) ==
    /\ SandHandleRequestVoteResponse(i, j, m) /\ UNCHANGED counters
MCHandleAppendEntriesRequest(i, j, m) ==
    /\ SandHandleAppendEntriesRequest(i, j, m) /\ UNCHANGED counters
MCHandleAppendEntriesResponse(i, j, m) ==
    /\ SandHandleAppendEntriesResponse(i, j, m) /\ UNCHANGED counters

MCLoseMessage(m) ==
    /\ counters.lose < MaxLoseLimit
    /\ SandLoseMessage(m)
    /\ counters' = [counters EXCEPT !.lose = @ + 1]

MsgBufferConstraint ==
    BagCardinality(messages) <= MaxMsgBufferLimit

MCInit ==
    /\ SandInit
    /\ counters = [timeout |-> 0, request |-> 0, crash |-> 0,
                   lose |-> 0, append |-> 0]
    /\ MaxCrashLimit \in Nat

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

CandidateVotedForSelfInv == CandidateVotedForSelf
CommitIndexBoundInv == CommitIndexBound
LeaderTermPositiveInv == LeaderTermPositive
NextIndexPositiveInv == NextIndexPositive
PersistedTermConsistencyInv == PersistedTermConsistency

====
