---- MODULE MC_term ----
\* Schedule for the snapshot-load term decrease.
\* raft_begin_load_snapshot writes current_term = last_included_term
\* (raft_server.c:1383). Protocol actions are the MC wrappers unchanged.
\* The two LoseMessage steps drop RequestVotes this schedule never delivers,
\* so each later code-only send sits alone on its TCP channel.
EXTENDS MC

CONSTANTS s1, s2, s3, v1
VARIABLE step

TraceInit ==
    /\ MCInit
    /\ step = 0

AeOnly(src, dst) ==
    \A m \in BagToSet(messages') :
        (m.mtype = AppendEntriesRequest /\ m.msource = src) => m.mdest = dst

TraceNext ==
    \/ /\ step = 0
       /\ MCTimeout(s2)
       /\ step' = 1
    \/ /\ step = 1
       /\ \E m \in BagToSet(messages) :
            /\ m.mtype = RequestVoteRequest
            /\ m.msource = s2 /\ m.mdest = s3
            /\ MCHandleRequestVoteRequest(m.mdest, m.msource, m)
            /\ votedFor'[s3] = s2
       /\ step' = 2
    \/ /\ step = 2
       /\ \E m \in BagToSet(messages) :
            /\ m.mtype = RequestVoteRequest
            /\ m.msource = s2 /\ m.mdest = s1
            /\ MCLoseMessage(m)
       /\ step' = 3
    \/ /\ step = 3
       /\ \E m \in BagToSet(messages) :
            /\ m.mtype = RequestVoteResponse
            /\ m.msource = s3 /\ m.mdest = s2
            /\ m.mvoteGranted = TRUE
            /\ MCHandleRequestVoteResponse(m.mdest, m.msource, m)
            /\ state'[s2] = Leader
       /\ step' = 4
    \/ /\ step = 4
       /\ MCClientRequest(s2, v1)
       /\ step' = 5
    \/ /\ step = 5
       /\ MCClientRequest(s2, v1)
       /\ Len(log'[s2]) = 2
       /\ step' = 6
    \/ /\ step = 6
       /\ MCBroadcastAppendEntries(s2)
       /\ AeOnly(s2, s3)
       /\ step' = 7
    \/ /\ step = 7
       /\ \E m \in BagToSet(messages) :
            /\ m.mtype = AppendEntriesRequest
            /\ m.msource = s2 /\ m.mdest = s3
            /\ MCHandleAppendEntriesRequest(m.mdest, m.msource, m)
            /\ Len(log'[s3]) = 2
       /\ step' = 8
    \/ /\ step = 8
       /\ \E m \in BagToSet(messages) :
            /\ m.mtype = AppendEntriesResponse
            /\ m.msource = s3 /\ m.mdest = s2
            /\ m.msuccess = TRUE
            /\ MCHandleAppendEntriesResponse(m.mdest, m.msource, m)
            /\ commitIndex'[s2] = 2
       /\ step' = 9
    \/ /\ step = 9
       /\ MCBroadcastAppendEntries(s2)
       /\ AeOnly(s2, s3)
       /\ step' = 10
    \/ /\ step = 10
       /\ \E m \in BagToSet(messages) :
            /\ m.mtype = AppendEntriesRequest
            /\ m.msource = s2 /\ m.mdest = s3
            /\ MCHandleAppendEntriesRequest(m.mdest, m.msource, m)
            /\ commitIndex'[s3] = 2
       /\ step' = 11
    \/ /\ step = 11
       /\ \E m \in BagToSet(messages) :
            /\ m.mtype = AppendEntriesResponse
            /\ m.msource = s3 /\ m.mdest = s2
            /\ MCHandleAppendEntriesResponse(m.mdest, m.msource, m)
       /\ step' = 12
    \/ /\ step = 12
       /\ MCTakeSnapshot(s3)
       /\ snapshotLastIdx'[s3] = 2
       /\ snapshotLastTerm'[s3] = 1
       /\ Len(log'[s3]) = 0
       /\ step' = 13
    \/ /\ step = 13
       /\ MCTimeout(s3)
       /\ currentTerm'[s3] = 2
       /\ step' = 14
    \/ /\ step = 14
       /\ \E m \in BagToSet(messages) :
            /\ m.mtype = RequestVoteRequest
            /\ m.msource = s3 /\ m.mdest = s2
            /\ MCLoseMessage(m)
       /\ step' = 15
    \/ /\ step = 15
       /\ \E m \in BagToSet(messages) :
            /\ m.mtype = RequestVoteRequest
            /\ m.msource = s3 /\ m.mdest = s1
            /\ MCHandleRequestVoteRequest(m.mdest, m.msource, m)
            /\ votedFor'[s1] = s3
            /\ currentTerm'[s1] = 2
       /\ step' = 16
    \/ /\ step = 16
       /\ \E m \in BagToSet(messages) :
            /\ m.mtype = RequestVoteResponse
            /\ m.msource = s1 /\ m.mdest = s3
            /\ m.mvoteGranted = TRUE
            /\ MCHandleRequestVoteResponse(m.mdest, m.msource, m)
            /\ state'[s3] = Leader
       /\ step' = 17
    \/ /\ step = 17
       /\ MCBroadcastAppendEntries(s3)
       /\ AeOnly(s3, s1)
       /\ step' = 18
    \/ /\ step = 18
       /\ \E m \in BagToSet(messages) :
            /\ m.mtype = AppendEntriesRequest
            /\ m.msource = s3 /\ m.mdest = s1
            /\ MCHandleAppendEntriesRequest(m.mdest, m.msource, m)
            /\ \E r \in BagToSet(messages') :
                 /\ r.mtype = AppendEntriesResponse
                 /\ r.msource = s1 /\ r.mdest = s3
                 /\ r.msuccess = FALSE
       /\ step' = 19
    \/ /\ step = 19
       /\ \E m \in BagToSet(messages) :
            /\ m.mtype = AppendEntriesResponse
            /\ m.msource = s1 /\ m.mdest = s3
            /\ m.msuccess = FALSE
            /\ MCHandleAppendEntriesResponse(m.mdest, m.msource, m)
            /\ nextIndex'[s3][s1] = 1
       /\ step' = 20
    \/ /\ step = 20
       /\ MCSendInstallSnapshot(s3, s1)
       /\ step' = 21
    \/ /\ step = 21
       /\ \E m \in BagToSet(messages) :
            /\ m.mtype = InstallSnapshotRequest
            /\ m.msource = s3 /\ m.mdest = s1
            /\ MCHandleInstallSnapshot(m.mdest, m.msource, m)
            /\ currentTerm[s1] = 2
            /\ currentTerm'[s1] = 1
       /\ step' = 22

TraceSpec == TraceInit /\ [][TraceNext]_<<allVars, mcVars, step>>

====
