---- MODULE MC_trace ----
\* Restricted schedule for the 11-state LeaderCompleteness counterexample
\* written up in bug-report.md. Protocol actions are the MC wrappers
\* unchanged. step only selects which enabled action TLC may take, so
\* every state of TraceSpec is a state of MCSpec.
EXTENDS MC_witness

CONSTANTS s1, s2, s3, v1
VARIABLE step

TraceInit ==
    /\ MCInit
    /\ step = 0

TraceNext ==
    \/ /\ step = 0
       /\ MCTimeout(s1)
       /\ step' = 1
    \/ /\ step = 1
       \* s2 grants s1. The lease-reject disjunct leaves votedFor unchanged.
       /\ \E m \in BagToSet(messages) :
            /\ m.mtype = RequestVoteRequest
            /\ m.msource = s1
            /\ m.mdest = s2
            /\ MCHandleRequestVoteRequest(m.mdest, m.msource, m)
            /\ votedFor'[s2] = s1
       /\ step' = 2
    \/ /\ step = 2
       /\ MCTimeout(s2)
       /\ step' = 3
    \/ /\ step = 3
       /\ \E m \in BagToSet(messages) :
            /\ m.mtype = RequestVoteRequest
            /\ m.msource = s2
            /\ m.mdest = s3
            /\ MCHandleRequestVoteRequest(m.mdest, m.msource, m)
            /\ votedFor'[s3] = s2
       /\ step' = 4
    \/ /\ step = 4
       /\ \E m \in BagToSet(messages) :
            /\ m.mtype = RequestVoteResponse
            /\ m.msource = s3
            /\ m.mdest = s2
            /\ m.mvoteGranted = TRUE
            /\ MCHandleRequestVoteResponse(m.mdest, m.msource, m)
            /\ state'[s2] = Leader
       /\ step' = 5
    \/ /\ step = 5
       /\ MCClientRequest(s2, v1)
       /\ step' = 6
    \/ /\ step = 6
       \* Subset broadcast: only s3. Sending to s1 as well is also enabled,
       \* but then s1 can observe term 2 before the stale vote is delivered.
       /\ MCBroadcastAppendEntries(s2)
       /\ \A m \in BagToSet(messages') :
            (m.mtype = AppendEntriesRequest /\ m.msource = s2) => m.mdest = s3
       /\ step' = 7
    \/ /\ step = 7
       /\ \E m \in BagToSet(messages) :
            /\ m.mtype = AppendEntriesRequest
            /\ m.msource = s2
            /\ m.mdest = s3
            /\ MCHandleAppendEntriesRequest(m.mdest, m.msource, m)
            /\ Len(log'[s3]) = 1
       /\ step' = 8
    \/ /\ step = 8
       /\ \E m \in BagToSet(messages) :
            /\ m.mtype = AppendEntriesResponse
            /\ m.msource = s3
            /\ m.mdest = s2
            /\ MCHandleAppendEntriesResponse(m.mdest, m.msource, m)
            /\ commitIndex'[s2] = 1
       /\ step' = 9
    \/ /\ step = 9
       /\ \E m \in BagToSet(messages) :
            /\ m.mtype = RequestVoteResponse
            /\ m.msource = s2
            /\ m.mdest = s1
            /\ m.mvoteGranted = TRUE
            /\ MCHandleRequestVoteResponse(m.mdest, m.msource, m)
            /\ state'[s1] = Leader
       /\ step' = 10

TraceSpec == TraceInit /\ [][TraceNext]_<<allVars, mcVars, step>>

====
