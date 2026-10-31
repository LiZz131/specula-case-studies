---------------------------- MODULE base_for_sandtable ----------------------------
\* TLA+ specification of RedisRaft consensus protocol.
\*
\* Models the RedisLabs/redisraft implementation with extensions for:
\*   1. Snapshot loading crash window: multi-step load with gap detection (Bug Family 1)
\*   2. Stale read / linearizability: non-quorum reads on stale leaders (Bug Family 2)
\*   3. Membership change safety: single-server changes + split brain (Bug Family 3)
\*   4. Log persistence: crash between truncate and append (Bug Family 4)
\*
\* Based on: deps/raft/src/raft_server.c (core), src/snapshot.c, src/redisraft.c

EXTENDS Naturals, FiniteSets, Sequences, Bags, TLC

----
\* Constants
----

CONSTANT Server              \* Set of server IDs
CONSTANTS s1, s2, s3         \* Named servers. Replay maps sN to nN.

CONSTANTS Follower,          \* Server states
          Candidate,
          Leader

CONSTANT Nil                 \* Null value

CONSTANTS ValueEntry,        \* Log entry types
          ConfigEntry,
          NoopEntry

CONSTANTS RequestVoteRequest,        \* Message types
          RequestVoteResponse,
          AppendEntriesRequest,
          AppendEntriesResponse,
          InstallSnapshotRequest

----
\* Variables
----

\* Per-server persistent state (survives restart)
\* Reference: raft_private.h:32-40
VARIABLE currentTerm         \* [Server -> Nat]
VARIABLE votedFor            \* [Server -> Server \cup {Nil}]
VARIABLE log                 \* [Server -> Seq(Entry)]

\* Per-server volatile state
\* Reference: raft_private.h:45-54
VARIABLE state               \* [Server -> {Follower, Candidate, Leader}]
VARIABLE commitIndex         \* [Server -> Nat]

\* Leader volatile state
\* Reference: raft_node.h:next_idx, match_idx
VARIABLE nextIndex           \* [Server -> [Server -> Nat]]
VARIABLE matchIndex          \* [Server -> [Server -> Nat]]

\* Candidate state
VARIABLE votesGranted        \* [Server -> SUBSET Server]

\* Network
VARIABLE messages            \* Bag of message records

\* Extension 1: Snapshot state (Bug Family 1)
\* Models the multi-step snapshot install with crash windows.
\* Key insight: raft_begin_load_snapshot() resets the log (persistent)
\* but snapshot_last_idx is only updated in raft_end_load_snapshot().
\* Crash between these steps leaves a gap.
\* Reference: raft_server.c:1904-1975, snapshot.c:473-548
VARIABLE snapshotLastIdx     \* [Server -> Nat] — persistent metadata
VARIABLE snapshotLastTerm    \* [Server -> Nat] — persistent metadata
VARIABLE logOffset           \* [Server -> Nat] — persistent, physical log start - 1
                             \* Normally = snapshotLastIdx; diverges during load
VARIABLE loadingSnapshot     \* [Server -> BOOLEAN] — volatile
VARIABLE pendingSnapshotIdx  \* [Server -> Nat] — volatile, set during begin_load
VARIABLE pendingSnapshotTerm \* [Server -> Nat] — volatile

\* Extension 2: Read safety detection (Bug Family 2)
\* Non-quorum reads on stale leaders violate linearizability.
\* Reference: redisraft.c:750-753 (non-quorum path)
VARIABLE staleReadDetected   \* BOOLEAN — latches TRUE on stale read
VARIABLE noopReadDetected    \* BOOLEAN — latches TRUE on read before noop committed

\* Extension 3: Membership change tracking (Bug Family 3)
\* Single-server membership changes with single-change-at-a-time guard.
\* Reference: raft_server.c:1151-1199, 1223-1303
VARIABLE clusterConfig       \* [Server -> SUBSET Server] — persistent committed config
VARIABLE votingCfgChangeIdx  \* [Server -> Nat] — volatile, 0 = no pending change

\* Replay record. Protocol actions above do not read it.
\* pc is the command tuple. nSent is how many send syscalls have been stamped.
VARIABLE scr

----
\* Variable groups
----

serverVars    == <<currentTerm, votedFor, state>>
logVars       == <<log, commitIndex, logOffset>>
leaderVars    == <<nextIndex, matchIndex>>
candidateVars == <<votesGranted>>
snapshotVars  == <<snapshotLastIdx, snapshotLastTerm, loadingSnapshot,
                   pendingSnapshotIdx, pendingSnapshotTerm>>
readVars      == <<staleReadDetected, noopReadDetected>>
configVars    == <<clusterConfig, votingCfgChangeIdx>>

vars == <<serverVars, logVars, leaderVars, candidateVars, messages,
          snapshotVars, readVars, configVars>>
allVars == vars

----
\* Helpers
----

Min(a, b) == IF a <= b THEN a ELSE b
Max(a, b) == IF a >= b THEN a ELSE b

SetMax(S) == CHOOSE x \in S : \A y \in S : x >= y

\* Log helpers — log[i] is indexed 1..Len(log[i]), representing
\* logical indices logOffset[i]+1 .. logOffset[i]+Len(log[i]).
\* Reference: log entries start after the snapshot offset.
LastLogIndex(i) == logOffset[i] + Len(log[i])

LastLogTerm(i) ==
    IF Len(log[i]) > 0 THEN log[i][Len(log[i])].term
    ELSE IF logOffset[i] > 0 THEN snapshotLastTerm[i]
    ELSE 0

LogTerm(i, idx) ==
    IF idx = 0 THEN 0
    ELSE IF idx <= snapshotLastIdx[i] THEN
        \* Entry is in the snapshot; only the boundary term is known
        IF idx = snapshotLastIdx[i] THEN snapshotLastTerm[i] ELSE 0
    ELSE IF idx > logOffset[i] /\ idx <= LastLogIndex(i) THEN
        log[i][idx - logOffset[i]].term
    ELSE 0  \* Gap between snapshotLastIdx and logOffset (Bug Family 1)

LogEntry(i, idx) == log[i][idx - logOffset[i]]

\* Effective config: latest config entry in log (committed or not).
\* Takes effect on APPEND per raft_handle_append_cfg_change (raft_server.c:263-309).
\* Used for quorum checks and message routing.
EffectiveConfig(i) ==
    LET cfgEntries == {k \in 1..Len(log[i]) : log[i][k].type = ConfigEntry}
    IN IF cfgEntries = {} THEN clusterConfig[i]
       ELSE log[i][SetMax(cfgEntries)].config

\* Quorum check: majority of voters
\* Reference: raft_server.c:1087-1088 (raft_votes_is_majority)
IsQuorum(S, voters) == Cardinality(S) * 2 > Cardinality(voters)

\* Log up-to-date comparison for elections
\* Reference: raft_server.c:1042-1048
LogUpToDate(cLastTerm, cLastIdx, vLastTerm, vLastIdx) ==
    \/ cLastTerm > vLastTerm
    \/ (cLastTerm = vLastTerm /\ cLastIdx >= vLastIdx)

\* Check if leader i has committed a current-term entry (the noop).
\* Reference: raft_server.c:443-450 (noop append in become_leader)
HasCurrentTermCommitted(i) ==
    \E k \in 1..Min(Len(log[i]), commitIndex[i] - logOffset[i]) :
        log[i][k].term = currentTerm[i]

\* Compute committed config from log.
\* Scans committed entries for the latest ConfigEntry.
CommittedConfigFromLog(logSeq, logOff, cIdx) ==
    LET commitLen == Max(0, Min(Len(logSeq), cIdx - logOff))
        cfgEntries == {k \in 1..commitLen : logSeq[k].type = ConfigEntry}
    IN IF cfgEntries = {} THEN Nil
       ELSE logSeq[SetMax(cfgEntries)].config

\* Message bag helpers
Send(m) == messages' = messages (+) SetToBag({m})
Discard(m) == messages' = messages (-) SetToBag({m})
Reply(resp, req) ==
    messages' = (messages (-) SetToBag({req})) (+) SetToBag({resp})
SendAll(ms) == messages' = messages (+) SetToBag(ms)

----
\* Init
----

Init ==
    /\ currentTerm       = [s \in Server |-> 0]
    /\ votedFor           = [s \in Server |-> Nil]
    /\ log                = [s \in Server |-> <<>>]
    /\ logOffset          = [s \in Server |-> 0]
    /\ state              = [s \in Server |-> Follower]
    /\ commitIndex        = [s \in Server |-> 0]
    /\ nextIndex          = [s \in Server |-> [t \in Server |-> 1]]
    /\ matchIndex         = [s \in Server |-> [t \in Server |-> 0]]
    /\ votesGranted       = [s \in Server |-> {}]
    /\ messages           = EmptyBag
    /\ snapshotLastIdx    = [s \in Server |-> 0]
    /\ snapshotLastTerm   = [s \in Server |-> 0]
    /\ loadingSnapshot    = [s \in Server |-> FALSE]
    /\ pendingSnapshotIdx = [s \in Server |-> 0]
    /\ pendingSnapshotTerm = [s \in Server |-> 0]
    /\ staleReadDetected  = FALSE
    /\ noopReadDetected   = FALSE
    /\ clusterConfig      = [s \in Server |-> Server]
    /\ votingCfgChangeIdx = [s \in Server |-> 0]

----
\* Election Actions
----

\* Server i times out and starts an election.
\* Increments term, votes for self, sends RequestVote to all config members.
\* Reference: raft_server.c:523-559 (raft_become_candidate)
\* Note: PreVote is not modeled per modeling brief recommendation.
Timeout(i) ==
    /\ state[i] \in {Follower, Candidate}
    /\ i \in EffectiveConfig(i)
    /\ ~loadingSnapshot[i]
    \* Increment term and vote for self (raft_server.c:525, 535-539)
    /\ currentTerm' = [currentTerm EXCEPT ![i] = @ + 1]
    /\ votedFor' = [votedFor EXCEPT ![i] = i]
    /\ state' = [state EXCEPT ![i] = Candidate]
    \* Clear votes, add self-vote (raft_server.c:530-532, 535)
    /\ votesGranted' = [votesGranted EXCEPT ![i] = {i}]
    \* Send RequestVote to all config members (raft_server.c:544-550)
    /\ SendAll({[mtype         |-> RequestVoteRequest,
                 mterm         |-> currentTerm[i] + 1,
                 mlastLogTerm  |-> LastLogTerm(i),
                 mlastLogIndex |-> LastLogIndex(i),
                 msource       |-> i,
                 mdest         |-> j] : j \in EffectiveConfig(i) \ {i}})
    /\ UNCHANGED <<log, commitIndex, logOffset, leaderVars,
                   snapshotVars, readVars, configVars>>

\* Server i handles a RequestVote request m.
\* Checks term, vote status, and log recency.
\* Reference: raft_server.c:990-1081 (raft_recv_requestvote)
HandleRequestVoteRequest(i, m) ==
    /\ m.mtype = RequestVoteRequest
    /\ m.mdest = i
    /\ LET mterm     == m.mterm
           logOk     == LogUpToDate(m.mlastLogTerm, m.mlastLogIndex,
                                    LastLogTerm(i), LastLogIndex(i))
           canGrant  == /\ \/ votedFor[i] = Nil
                           \/ votedFor[i] = m.msource
                        /\ logOk
       IN
       \/ \* Reject: stale term (raft_server.c:1029-1031)
          /\ mterm < currentTerm[i]
          /\ Reply([mtype        |-> RequestVoteResponse,
                    mterm        |-> currentTerm[i],
                    mvoteGranted |-> FALSE,
                    msource      |-> i,
                    mdest        |-> m.msource], m)
          /\ UNCHANGED <<serverVars, logVars, leaderVars, candidateVars,
                         snapshotVars, readVars, configVars>>

       \/ \* Higher term: step down, then decide (raft_server.c:1020-1027)
          /\ mterm > currentTerm[i]
          /\ currentTerm' = [currentTerm EXCEPT ![i] = mterm]
          /\ state' = [state EXCEPT ![i] = Follower]
          /\ LET newCanGrant == logOk  \* voted_for cleared by term change
             IN
             /\ votedFor' = [votedFor EXCEPT ![i] =
                    IF newCanGrant THEN m.msource ELSE Nil]
             /\ Reply([mtype        |-> RequestVoteResponse,
                       mterm        |-> mterm,
                       mvoteGranted |-> newCanGrant,
                       msource      |-> i,
                       mdest        |-> m.msource], m)
          /\ UNCHANGED <<log, commitIndex, logOffset, leaderVars, candidateVars,
                         snapshotVars, readVars, configVars>>

       \/ \* Same term: grant if eligible (raft_server.c:1033-1064)
          /\ mterm = currentTerm[i]
          /\ \/ \* Grant vote (raft_server.c:1050-1064)
                /\ canGrant
                /\ votedFor' = [votedFor EXCEPT ![i] = m.msource]
                /\ Reply([mtype        |-> RequestVoteResponse,
                          mterm        |-> currentTerm[i],
                          mvoteGranted |-> TRUE,
                          msource      |-> i,
                          mdest        |-> m.msource], m)
             \/ \* Deny vote (raft_server.c:1033-1048)
                /\ ~canGrant
                /\ Reply([mtype        |-> RequestVoteResponse,
                          mterm        |-> currentTerm[i],
                          mvoteGranted |-> FALSE,
                          msource      |-> i,
                          mdest        |-> m.msource], m)
                /\ UNCHANGED votedFor
          /\ UNCHANGED <<currentTerm, state, log, commitIndex, logOffset,
                         leaderVars, candidateVars,
                         snapshotVars, readVars, configVars>>

\* Server i handles a RequestVote response m.
\* Counts votes; BecomeLeader is a separate action.
\* Reference: raft_server.c:1091-1149 (raft_recv_requestvote_response)
HandleRequestVoteResponse(i, m) ==
    /\ m.mtype = RequestVoteResponse
    /\ m.mdest = i
    /\ \/ \* Higher term: step down (raft_server.c:1108-1115)
          /\ m.mterm > currentTerm[i]
          /\ currentTerm' = [currentTerm EXCEPT ![i] = m.mterm]
          /\ votedFor' = [votedFor EXCEPT ![i] = Nil]
          /\ state' = [state EXCEPT ![i] = Follower]
          /\ Discard(m)
          /\ UNCHANGED <<log, commitIndex, logOffset, leaderVars, candidateVars,
                         snapshotVars, readVars, configVars>>

       \/ \* Not a candidate: ignore (raft_server.c:1124-1129)
          /\ state[i] /= Candidate
          /\ Discard(m)
          /\ UNCHANGED <<serverVars, logVars, leaderVars, candidateVars,
                         snapshotVars, readVars, configVars>>

       \/ \* Candidate, vote granted: record (raft_server.c:1131-1137)
          /\ state[i] = Candidate
          /\ m.mterm = currentTerm[i]
          /\ m.mvoteGranted
          /\ votesGranted' = [votesGranted EXCEPT ![i] = @ \cup {m.msource}]
          /\ Discard(m)
          /\ UNCHANGED <<serverVars, logVars, leaderVars,
                         snapshotVars, readVars, configVars>>

       \/ \* Candidate, vote denied: discard (raft_server.c:1131)
          /\ state[i] = Candidate
          /\ m.mterm <= currentTerm[i]
          /\ ~m.mvoteGranted
          /\ Discard(m)
          /\ UNCHANGED <<serverVars, logVars, leaderVars, candidateVars,
                         snapshotVars, readVars, configVars>>

\* Candidate i has majority votes and becomes leader.
\* Appends a no-op entry and initializes follower tracking.
\* Reference: raft_server.c:443-496 (raft_become_leader)
BecomeLeader(i) ==
    /\ state[i] = Candidate
    /\ IsQuorum(votesGranted[i], EffectiveConfig(i))
    \* Append no-op entry (raft_server.c:445-455)
    /\ LET noopEntry == [term |-> currentTerm[i], type |-> NoopEntry, config |-> {}]
           newLog    == Append(log[i], noopEntry)
           newLastIdx == logOffset[i] + Len(newLog)
       IN
       /\ log' = [log EXCEPT ![i] = newLog]
       /\ state' = [state EXCEPT ![i] = Leader]
       \* Initialize follower tracking (raft_server.c:476-487)
       /\ nextIndex' = [nextIndex EXCEPT ![i] =
              [j \in Server |-> IF j = i THEN newLastIdx + 1 ELSE newLastIdx]]
       /\ matchIndex' = [matchIndex EXCEPT ![i] =
              [j \in Server |-> IF j = i THEN newLastIdx ELSE 0]]
    /\ UNCHANGED <<currentTerm, votedFor, commitIndex, logOffset, candidateVars,
                   messages, snapshotVars, readVars, configVars>>

----
\* Log Replication Actions
----

\* Client submits a write to leader i.
\* Reference: raft_server.c:1151-1210 (raft_recv_entry)
ClientRequest(i) ==
    /\ state[i] = Leader
    /\ ~loadingSnapshot[i]
    /\ LET entry == [term |-> currentTerm[i], type |-> ValueEntry, config |-> {}]
           newLog == Append(log[i], entry)
       IN
       /\ log' = [log EXCEPT ![i] = newLog]
       /\ matchIndex' = [matchIndex EXCEPT ![i][i] = logOffset[i] + Len(newLog)]
    /\ UNCHANGED <<currentTerm, votedFor, state, commitIndex, logOffset,
                   nextIndex, candidateVars, messages,
                   snapshotVars, readVars, configVars>>

\* Leader i sends AppendEntries to follower j.
\* Reference: raft_server.c:1593-1651 (raft_send_appendentries)
AppendEntries(i, j) ==
    /\ state[i] = Leader
    /\ j /= i
    /\ j \in EffectiveConfig(i)
    \* Can only send if entries are available (not behind snapshot)
    \* Reference: raft_server.c:1604-1606 — if behind snapshot, send snapshot instead
    /\ nextIndex[i][j] > logOffset[i]
    /\ LET nextIdx  == nextIndex[i][j]
           prevIdx  == nextIdx - 1
           prevTerm == LogTerm(i, prevIdx)
           lastIdx  == LastLogIndex(i)
           \* Send all available entries from nextIdx (raft_server.c:1619-1648)
           entries  == IF nextIdx > logOffset[i] /\ nextIdx <= lastIdx
                       THEN SubSeq(log[i], nextIdx - logOffset[i], Len(log[i]))
                       ELSE <<>>
       IN Send([mtype         |-> AppendEntriesRequest,
                mterm         |-> currentTerm[i],
                mprevLogIndex |-> prevIdx,
                mprevLogTerm  |-> prevTerm,
                mentries      |-> entries,
                mleaderCommit |-> commitIndex[i],
                msource       |-> i,
                mdest         |-> j])
    /\ UNCHANGED <<serverVars, logVars, leaderVars, candidateVars,
                   snapshotVars, readVars, configVars>>

\* Server i handles an AppendEntries request m.
\* Reference: raft_server.c:823-970 (raft_recv_appendentries)
HandleAppendEntriesRequest(i, m) ==
    /\ m.mtype = AppendEntriesRequest
    /\ m.mdest = i
    /\ LET prevIdx      == m.mprevLogIndex
           prevTerm     == m.mprevLogTerm
           entries      == m.mentries
           leaderCommit == m.mleaderCommit
       IN
       \/ \* Reject: stale term (raft_server.c:844-848)
          /\ m.mterm < currentTerm[i]
          /\ Reply([mtype       |-> AppendEntriesResponse,
                    mterm       |-> currentTerm[i],
                    msuccess    |-> FALSE,
                    mmatchIndex |-> 0,
                    msource     |-> i,
                    mdest       |-> m.msource], m)
          /\ UNCHANGED <<serverVars, logVars, leaderVars, candidateVars,
                         snapshotVars, readVars, configVars>>

       \/ \* Accept: term >= currentTerm (raft_server.c:851-969)
          /\ m.mterm >= currentTerm[i]
          \* Step down if higher term (raft_server.c:851-856)
          /\ currentTerm' = [currentTerm EXCEPT ![i] = Max(@, m.mterm)]
          /\ votedFor' = IF m.mterm > currentTerm[i]
                         THEN [votedFor EXCEPT ![i] = Nil]
                         ELSE votedFor
          /\ state' = [state EXCEPT ![i] = Follower]

          /\ \/ \* Log mismatch: reject (raft_server.c:870-900)
                \* Either log too short or term mismatch at prevIdx
                /\ \/ /\ prevIdx > 0
                      /\ prevIdx > LastLogIndex(i)
                   \/ /\ prevIdx > 0
                      /\ prevIdx > logOffset[i]
                      /\ prevIdx <= LastLogIndex(i)
                      /\ LogTerm(i, prevIdx) /= prevTerm
                /\ Reply([mtype       |-> AppendEntriesResponse,
                          mterm       |-> Max(currentTerm[i], m.mterm),
                          msuccess    |-> FALSE,
                          mmatchIndex |-> LastLogIndex(i),
                          msource     |-> i,
                          mdest       |-> m.msource], m)
                /\ UNCHANGED <<log, commitIndex, logOffset,
                               snapshotVars, readVars, configVars>>

             \/ \* Log match: truncate conflicts and append (raft_server.c:902-969)
                /\ \/ prevIdx = 0
                   \/ /\ prevIdx > 0
                      /\ prevIdx <= logOffset[i]  \* covered by snapshot
                   \/ /\ prevIdx > logOffset[i]
                      /\ prevIdx <= LastLogIndex(i)
                      /\ LogTerm(i, prevIdx) = prevTerm
                \* Truncate everything after prevIdx and append new entries.
                \* Reference: raft_server.c:917-955 (conflict detection + append)
                \* Simplification: we overwrite from prevIdx+1; the code scans for
                \* the first conflict then truncates, but the result is equivalent.
                /\ LET baseLen  == Max(0, prevIdx - logOffset[i])
                       newLog   == SubSeq(log[i], 1, baseLen) \o entries
                       newLast  == logOffset[i] + Len(newLog)
                       \* Advance commitIndex (raft_server.c:964-969)
                       newCommit == Max(commitIndex[i],
                                       Min(leaderCommit, newLast))
                       \* Update clusterConfig if newly committed config entries
                       cfgResult == CommittedConfigFromLog(newLog, logOffset[i], newCommit)
                       newConfig == IF cfgResult = Nil
                                    THEN clusterConfig[i]
                                    ELSE cfgResult
                       \* Update votingCfgChangeIdx: find uncommitted config entry
                       \* Reference: raft_server.c:1260 (set on append), 404-405 (clear on truncate)
                       cfgIdxSet == {k \in 1..Len(newLog) :
                                       /\ newLog[k].type = ConfigEntry
                                       /\ logOffset[i] + k > newCommit}
                       newCfgIdx == IF cfgIdxSet = {} THEN 0
                                    ELSE logOffset[i] + SetMax(cfgIdxSet)
                   IN
                   /\ log' = [log EXCEPT ![i] = newLog]
                   /\ commitIndex' = [commitIndex EXCEPT ![i] = newCommit]
                   /\ clusterConfig' = [clusterConfig EXCEPT ![i] = newConfig]
                   /\ votingCfgChangeIdx' = [votingCfgChangeIdx EXCEPT ![i] = newCfgIdx]
                /\ Reply([mtype       |-> AppendEntriesResponse,
                          mterm       |-> Max(currentTerm[i], m.mterm),
                          msuccess    |-> TRUE,
                          mmatchIndex |-> logOffset[i] + Len(
                              SubSeq(log[i], 1, Max(0, prevIdx - logOffset[i])) \o entries),
                          msource     |-> i,
                          mdest       |-> m.msource], m)
                /\ UNCHANGED <<logOffset, snapshotVars, readVars>>

          /\ UNCHANGED <<leaderVars, candidateVars>>

\* Leader i handles an AppendEntries response m.
\* Reference: raft_server.c:725-821 (raft_recv_appendentries_response)
HandleAppendEntriesResponse(i, m) ==
    /\ m.mtype = AppendEntriesResponse
    /\ m.mdest = i
    /\ \/ \* Higher term: step down (raft_server.c:751-758)
          /\ m.mterm > currentTerm[i]
          /\ currentTerm' = [currentTerm EXCEPT ![i] = m.mterm]
          /\ votedFor' = [votedFor EXCEPT ![i] = Nil]
          /\ state' = [state EXCEPT ![i] = Follower]
          /\ Discard(m)
          /\ UNCHANGED <<log, commitIndex, logOffset, leaderVars, candidateVars,
                         snapshotVars, readVars, configVars>>

       \/ \* Not leader or stale: ignore
          /\ m.mterm <= currentTerm[i]
          /\ \/ state[i] /= Leader
             \/ m.mterm < currentTerm[i]
          /\ Discard(m)
          /\ UNCHANGED <<serverVars, logVars, leaderVars, candidateVars,
                         snapshotVars, readVars, configVars>>

       \/ \* Leader, failure: backtrack nextIndex (raft_server.c:761-775)
          /\ m.mterm = currentTerm[i]
          /\ state[i] = Leader
          /\ ~m.msuccess
          \* Decrement nextIndex, bounded by logOffset+1 (raft_server.c:767-771)
          /\ nextIndex' = [nextIndex EXCEPT ![i][m.msource] =
                Max(logOffset[i] + 1, Min(m.mmatchIndex + 1, @))]
          /\ Discard(m)
          /\ UNCHANGED <<serverVars, log, commitIndex, logOffset, matchIndex,
                         candidateVars, snapshotVars, readVars, configVars>>

       \/ \* Leader, success: advance matchIndex (raft_server.c:804-814)
          /\ m.mterm = currentTerm[i]
          /\ state[i] = Leader
          /\ m.msuccess
          /\ matchIndex' = [matchIndex EXCEPT ![i][m.msource] =
                Max(@, m.mmatchIndex)]
          /\ nextIndex' = [nextIndex EXCEPT ![i][m.msource] =
                Max(@, m.mmatchIndex + 1)]
          /\ Discard(m)
          /\ UNCHANGED <<serverVars, log, commitIndex, logOffset,
                         candidateVars, snapshotVars, readVars, configVars>>

\* Leader i advances commitIndex based on matchIndex quorum.
\* Reference: raft_server.c commit logic — find largest N s.t. majority
\* has matchIndex >= N and log[N].term = currentTerm (Raft §5.4.2).
AdvanceCommitIndex(i) ==
    /\ state[i] = Leader
    /\ \E n \in (commitIndex[i]+1)..LastLogIndex(i) :
        /\ LogTerm(i, n) = currentTerm[i]
        /\ LET agreeSet == {j \in EffectiveConfig(i) : matchIndex[i][j] >= n}
           IN IsQuorum(agreeSet, EffectiveConfig(i))
        /\ commitIndex' = [commitIndex EXCEPT ![i] = n]
        \* Update clusterConfig if config entry committed (raft_server.c:345-373)
        /\ LET cfgResult == CommittedConfigFromLog(log[i], logOffset[i], n)
               newConfig == IF cfgResult = Nil
                            THEN clusterConfig[i]
                            ELSE cfgResult
           IN clusterConfig' = [clusterConfig EXCEPT ![i] = newConfig]
        \* Clear votingCfgChangeIdx if committed (raft_server.c:1301)
        /\ votingCfgChangeIdx' = [votingCfgChangeIdx EXCEPT ![i] =
              IF @ > 0 /\ @ <= n THEN 0 ELSE @]
    /\ UNCHANGED <<currentTerm, votedFor, state, log, logOffset,
                   leaderVars, candidateVars, messages,
                   snapshotVars, readVars>>

----
\* Snapshot Actions (Bug Family 1)
\*
\* Models the multi-step snapshot lifecycle with crash windows.
\* Key historical bugs: 1c421cd, d052699, ea178c4, fd76599.
----

\* Server i takes a local snapshot, compacting committed entries.
\* Reference: raft_server.c:1825-1902 (raft_begin_snapshot + raft_end_snapshot)
TakeSnapshot(i) ==
    /\ commitIndex[i] > snapshotLastIdx[i]
    /\ ~loadingSnapshot[i]
    /\ LET snapIdx  == commitIndex[i]
           snapTerm == LogTerm(i, snapIdx)
           \* Remove compacted entries (raft_server.c:1865-1871)
           newLog   == SubSeq(log[i], snapIdx - logOffset[i] + 1, Len(log[i]))
       IN
       /\ snapshotLastIdx' = [snapshotLastIdx EXCEPT ![i] = snapIdx]
       /\ snapshotLastTerm' = [snapshotLastTerm EXCEPT ![i] = snapTerm]
       /\ log' = [log EXCEPT ![i] = newLog]
       /\ logOffset' = [logOffset EXCEPT ![i] = snapIdx]
    /\ UNCHANGED <<currentTerm, votedFor, state, commitIndex,
                   nextIndex, matchIndex, candidateVars, messages,
                   loadingSnapshot, pendingSnapshotIdx, pendingSnapshotTerm,
                   readVars, configVars>>

\* Leader i sends snapshot to follower j that is behind.
\* Reference: raft_server.c:1881-1899 (raft_send_snapshot)
SendInstallSnapshot(i, j) ==
    /\ state[i] = Leader
    /\ j /= i
    /\ j \in EffectiveConfig(i)
    \* Follower is behind snapshot (raft_server.c:1604-1606)
    /\ nextIndex[i][j] <= logOffset[i]
    /\ snapshotLastIdx[i] > 0
    /\ Send([mtype       |-> InstallSnapshotRequest,
             mterm       |-> currentTerm[i],
             msnapIdx    |-> snapshotLastIdx[i],
             msnapTerm   |-> snapshotLastTerm[i],
             msnapConfig |-> clusterConfig[i],
             msource     |-> i,
             mdest       |-> j])
    /\ UNCHANGED <<serverVars, logVars, leaderVars, candidateVars,
                   snapshotVars, readVars, configVars>>

\* Server i handles an InstallSnapshot request — begins loading.
\* This is step 1 of the multi-step load. The log is reset (persistent),
\* but snapshot metadata is NOT updated until EndLoadSnapshot.
\* Reference: raft_server.c:1904-1956 (raft_begin_load_snapshot)
\* BUG FAMILY 1: crash between here and EndLoadSnapshot leaves a gap.
HandleInstallSnapshotRequest(i, m) ==
    /\ m.mtype = InstallSnapshotRequest
    /\ m.mdest = i
    /\ ~loadingSnapshot[i]
    \* Validation (raft_server.c:1908-1913)
    /\ m.msnapIdx > snapshotLastIdx[i]
    /\ m.mterm >= currentTerm[i]
    \* Step down if higher term (raft_server.c:1919-1924)
    /\ currentTerm' = [currentTerm EXCEPT ![i] = Max(@, m.mterm)]
    /\ votedFor' = IF m.mterm > currentTerm[i]
                   THEN [votedFor EXCEPT ![i] = Nil]
                   ELSE votedFor
    /\ state' = [state EXCEPT ![i] = Follower]
    \* Reset log — PERSISTENT write (raft_server.c:1926)
    /\ log' = [log EXCEPT ![i] = <<>>]
    /\ logOffset' = [logOffset EXCEPT ![i] = m.msnapIdx]
    \* Update commit index (raft_server.c:1928-1935)
    /\ commitIndex' = [commitIndex EXCEPT ![i] = Max(@, m.msnapIdx)]
    \* Mark loading in progress — volatile
    /\ loadingSnapshot' = [loadingSnapshot EXCEPT ![i] = TRUE]
    /\ pendingSnapshotIdx' = [pendingSnapshotIdx EXCEPT ![i] = m.msnapIdx]
    /\ pendingSnapshotTerm' = [pendingSnapshotTerm EXCEPT ![i] = m.msnapTerm]
    \* Load config from snapshot
    /\ clusterConfig' = [clusterConfig EXCEPT ![i] = m.msnapConfig]
    /\ votingCfgChangeIdx' = [votingCfgChangeIdx EXCEPT ![i] = 0]
    \* NOTE: snapshotLastIdx/Term NOT updated yet — that's EndLoadSnapshot's job
    /\ Discard(m)
    /\ UNCHANGED <<nextIndex, matchIndex, candidateVars,
                   snapshotLastIdx, snapshotLastTerm, readVars>>

\* Server i completes loading a snapshot — updates snapshot metadata.
\* Reference: raft_server.c:1958-1975 (raft_end_load_snapshot)
EndLoadSnapshot(i) ==
    /\ loadingSnapshot[i] = TRUE
    \* Finalize snapshot metadata (raft_server.c:1960-1961)
    /\ snapshotLastIdx' = [snapshotLastIdx EXCEPT ![i] = pendingSnapshotIdx[i]]
    /\ snapshotLastTerm' = [snapshotLastTerm EXCEPT ![i] = pendingSnapshotTerm[i]]
    /\ loadingSnapshot' = [loadingSnapshot EXCEPT ![i] = FALSE]
    /\ UNCHANGED <<currentTerm, votedFor, log, logOffset, state, commitIndex,
                   nextIndex, matchIndex, candidateVars, messages,
                   pendingSnapshotIdx, pendingSnapshotTerm,
                   readVars, configVars>>

----
\* Read Actions (Bug Family 2)
\*
\* Models non-quorum read path that can return stale data.
\* Key historical bugs: Issue #19, 1149155, 2984ef9/Issue #316.
----

\* Leader i serves a non-quorum read.
\* BUG FAMILY 2: no quorum confirmation, no noop-committed check.
\* Reference: redisraft.c:750-753 (immediate execution without quorum check)
ClientNonQuorumRead(i) ==
    /\ state[i] = Leader
    \* Detect stale read: another server has higher committed state
    \* This means the read may return data missing committed entries.
    /\ staleReadDetected' = (staleReadDetected \/
        (\E j \in Server :
            /\ j /= i
            /\ commitIndex[j] > commitIndex[i]))
    \* Detect read before noop: leader hasn't committed a current-term entry
    \* Reference: redisraft.c:750-753 — no check for noop committed
    /\ noopReadDetected' = (noopReadDetected \/ ~HasCurrentTermCommitted(i))
    /\ UNCHANGED <<serverVars, logVars, leaderVars, candidateVars, messages,
                   snapshotVars, configVars>>

----
\* Membership Change Actions (Bug Family 3)
\*
\* Models single-server membership changes with safety guard.
\* Key historical bugs: Issues #17, #28, #44, #52; commits d3a7f75, 27e9595.
----

\* Leader i adds a server to the cluster.
\* Reference: raft_server.c:1151-1199 (raft_recv_entry, config change admission)
ProposeAddServer(i, target) ==
    /\ state[i] = Leader
    /\ target \notin EffectiveConfig(i)
    /\ target \in Server  \* must be a known server ID
    \* Single-change-at-a-time guard (raft_server.c:1159-1177)
    /\ votingCfgChangeIdx[i] = 0
    \* No config change during snapshot (raft_server.c:1175-1176)
    /\ ~loadingSnapshot[i]
    /\ LET newCfg == EffectiveConfig(i) \cup {target}
           entry  == [term |-> currentTerm[i], type |-> ConfigEntry, config |-> newCfg]
           newLog == Append(log[i], entry)
       IN
       /\ log' = [log EXCEPT ![i] = newLog]
       /\ votingCfgChangeIdx' = [votingCfgChangeIdx EXCEPT
              ![i] = logOffset[i] + Len(newLog)]
       /\ matchIndex' = [matchIndex EXCEPT ![i][i] = logOffset[i] + Len(newLog)]
    /\ UNCHANGED <<currentTerm, votedFor, state, commitIndex, logOffset,
                   nextIndex, candidateVars, messages,
                   snapshotVars, readVars, clusterConfig>>

\* Leader i removes a server from the cluster.
\* Reference: raft_server.c:1151-1199 (raft_recv_entry, config change admission)
ProposeRemoveServer(i, target) ==
    /\ state[i] = Leader
    /\ target \in EffectiveConfig(i)
    /\ Cardinality(EffectiveConfig(i)) > 1
    \* Single-change-at-a-time guard (raft_server.c:1159-1177)
    /\ votingCfgChangeIdx[i] = 0
    \* No config change during snapshot (raft_server.c:1175-1176)
    /\ ~loadingSnapshot[i]
    /\ LET newCfg == EffectiveConfig(i) \ {target}
           entry  == [term |-> currentTerm[i], type |-> ConfigEntry, config |-> newCfg]
           newLog == Append(log[i], entry)
       IN
       /\ log' = [log EXCEPT ![i] = newLog]
       /\ votingCfgChangeIdx' = [votingCfgChangeIdx EXCEPT
              ![i] = logOffset[i] + Len(newLog)]
       /\ matchIndex' = [matchIndex EXCEPT ![i][i] = logOffset[i] + Len(newLog)]
    /\ UNCHANGED <<currentTerm, votedFor, state, commitIndex, logOffset,
                   nextIndex, candidateVars, messages,
                   snapshotVars, readVars, clusterConfig>>

----
\* Crash and Recovery (Bug Families 1, 4)
\*
\* Models server crash with immediate recovery from persistent state.
\* Persistent: currentTerm, votedFor, log, logOffset, snapshotLastIdx/Term, clusterConfig.
\* Volatile: everything else resets.
\* Reference: raft_private.h (persistent vs volatile fields)
----

Crash(i) ==
    \* Persistent state preserved: currentTerm, votedFor, log, logOffset,
    \* snapshotLastIdx, snapshotLastTerm, clusterConfig
    \* Volatile state reset:
    /\ state' = [state EXCEPT ![i] = Follower]
    /\ commitIndex' = [commitIndex EXCEPT ![i] = 0]
    /\ nextIndex' = [nextIndex EXCEPT ![i] = [j \in Server |-> 1]]
    /\ matchIndex' = [matchIndex EXCEPT ![i] = [j \in Server |-> 0]]
    /\ votesGranted' = [votesGranted EXCEPT ![i] = {}]
    \* Snapshot loading interrupted (Bug Family 1 crash window)
    /\ loadingSnapshot' = [loadingSnapshot EXCEPT ![i] = FALSE]
    /\ pendingSnapshotIdx' = [pendingSnapshotIdx EXCEPT ![i] = 0]
    /\ pendingSnapshotTerm' = [pendingSnapshotTerm EXCEPT ![i] = 0]
    \* votingCfgChangeIdx is volatile (reset to 0; re-derived on next leader)
    /\ votingCfgChangeIdx' = [votingCfgChangeIdx EXCEPT ![i] = 0]
    /\ UNCHANGED <<currentTerm, votedFor, log, logOffset,
                   snapshotLastIdx, snapshotLastTerm, messages,
                   readVars, clusterConfig>>

----
\* Network Actions
----

\* Drop a message from the network (simulates network partition/loss).
LoseMessage(m) ==
    /\ Discard(m)
    /\ UNCHANGED <<serverVars, logVars, leaderVars, candidateVars,
                   snapshotVars, readVars, configVars>>

\* Discard a message with a stale term (optimization to prune state space).
DropStaleMessage(m) ==
    /\ m.mtype \in {AppendEntriesRequest, AppendEntriesResponse,
                     RequestVoteRequest, RequestVoteResponse,
                     InstallSnapshotRequest}
    /\ m.mterm < currentTerm[m.mdest]
    /\ Discard(m)
    /\ UNCHANGED <<serverVars, logVars, leaderVars, candidateVars,
                   snapshotVars, readVars, configVars>>

----
\* Next State Relation
----

Next ==
    \/ \E i \in Server :
        \* Election
        \/ Timeout(i)
        \/ BecomeLeader(i)
        \* Client operations
        \/ ClientRequest(i)
        \/ ClientNonQuorumRead(i)
        \* Commit advancement
        \/ AdvanceCommitIndex(i)
        \* Snapshot (Bug Family 1)
        \/ TakeSnapshot(i)
        \/ EndLoadSnapshot(i)
        \/ \E j \in Server : AppendEntries(i, j)
        \/ \E j \in Server : SendInstallSnapshot(i, j)
        \* Membership (Bug Family 3)
        \/ \E target \in Server : ProposeAddServer(i, target)
        \/ \E target \in Server : ProposeRemoveServer(i, target)
        \* Crash (Bug Families 1, 4)
        \/ Crash(i)
    \/ \E m \in DOMAIN messages :
        \/ HandleRequestVoteRequest(m.mdest, m)
        \/ HandleRequestVoteResponse(m.mdest, m)
        \/ HandleAppendEntriesRequest(m.mdest, m)
        \/ HandleAppendEntriesResponse(m.mdest, m)
        \/ HandleInstallSnapshotRequest(m.mdest, m)
        \/ LoseMessage(m)
        \/ DropStaleMessage(m)

Spec == Init /\ [][Next]_vars

----
\* Invariants
----

\* --- Standard Raft Safety ---

\* At most one leader per term.
\* Reference: Raft paper, Figure 3 (Election Safety)
ElectionSafety ==
    \A i, j \in Server :
        (state[i] = Leader /\ state[j] = Leader /\ currentTerm[i] = currentTerm[j])
            => i = j

\* If two log entries have the same index and term, the logs are identical
\* up to that point. Only checked for entries still in the log (not compacted).
\* Reference: Raft paper, Figure 3 (Log Matching)
LogMatching ==
    \A i, j \in Server :
        \A idx \in 1..Min(LastLogIndex(i), LastLogIndex(j)) :
            (/\ idx > logOffset[i]
             /\ idx > logOffset[j]
             /\ LogTerm(i, idx) = LogTerm(j, idx)
             /\ LogTerm(i, idx) > 0) =>
                LogEntry(i, idx) = LogEntry(j, idx)

\* A leader's log contains all committed entries from all servers.
\* Reference: Raft paper, Figure 3 (Leader Completeness)
LeaderCompleteness ==
    \A leader, other \in Server :
        (state[leader] = Leader /\ commitIndex[other] > 0) =>
            \A idx \in 1..commitIndex[other] :
                (/\ idx > logOffset[leader]
                 /\ idx > logOffset[other]) =>
                    /\ idx <= LastLogIndex(leader)
                    /\ LogEntry(leader, idx) = LogEntry(other, idx)

\* --- Structural Invariants ---

\* Commit index never exceeds log length.
CommitIndexBound ==
    \A i \in Server : commitIndex[i] <= LastLogIndex(i)

\* Leaders always have a positive term.
LeaderTermPositive ==
    \A i \in Server : state[i] = Leader => currentTerm[i] > 0

\* Candidates always voted for themselves.
CandidateVotedForSelf ==
    \A i \in Server : state[i] = Candidate => votedFor[i] = i

\* Config is always a non-empty subset of Server.
ConfigValid ==
    \A i \in Server :
        /\ clusterConfig[i] /= {}
        /\ clusterConfig[i] \subseteq Server

\* Log offset is consistent with snapshot or pending load.
LogOffsetValid ==
    \A i \in Server : logOffset[i] >= snapshotLastIdx[i]

\* --- Extension Invariants (Bug Family Targets) ---

\* Bug Family 1: After snapshot load completes (not loading), log offset
\* must equal snapshot last index. Violation means crash during load left a gap.
\* Reference: snapshot.c:527-540 (begin → end crash window)
SnapshotLogConsistency ==
    \A i \in Server :
        ~loadingSnapshot[i] => logOffset[i] = snapshotLastIdx[i]

\* Bug Family 2: Non-quorum read never returns stale data.
\* Violated when a stale leader serves a read.
\* Reference: redisraft.c:750-753, Issue #19
NoStaleRead == ~staleReadDetected

\* Bug Family 2: Leader must have committed a current-term entry (the no-op)
\* before serving reads. Violated when read is served before no-op committed.
\* Reference: raft_server.c:443-450 (noop), redisraft.c:750-753, Issue #316
NoReadBeforeNoOp == ~noopReadDetected

\* Bug Family 3: At most one uncommitted voting config change at a time.
\* Reference: raft_server.c:1159-1177 (single-change guard)
ConfigChangeSafety ==
    \A i \in Server :
        votingCfgChangeIdx[i] > 0 =>
            LET cfgIdxSet == {k \in 1..Len(log[i]) :
                                /\ log[i][k].type = ConfigEntry
                                /\ logOffset[i] + k > commitIndex[i]}
            IN Cardinality(cfgIdxSet) <= 1

----
\* SandTable executable layer.
\* Protocol updates inside each Sand* action are the formulas above.
\* The library control flow that a single driver command actually takes is
\* folded into that step: become-leader sends, the caught-up client append,
\* the append-entries response retry, and the commit update that precedes
\* the retry. seq is stamped in peer-name order. A handler runs only when
\* its message is the oldest on that TCP channel.
\*
\* Not in MCNext, because the stock driver has no command:
\* Crash, ProposeAddServer, ProposeRemoveServer, ClientNonQuorumRead,
\* SendInstallSnapshot, TakeSnapshot, EndLoadSnapshot. Snapshot callbacks
\* in the stock driver abort. PreVote is not a modeled action; the run
\* driver starts the election with raft_election_start(me, 1).
----

Peers(i) ==
    IF i = s1 THEN <<s2, s3>>
    ELSE IF i = s2 THEN <<s1, s3>>
    ELSE <<s1, s2>>

IsOldest(m) ==
    \A other \in BagToSet(messages) :
        (other.msource = m.msource /\ other.mdest = m.mdest) => other.seq >= m.seq

RECURSIVE MergeLog(_, _, _, _)
MergeLog(lg, off, prev, entries) ==
    IF entries = <<>> THEN lg
    ELSE LET idx == prev + 1
             pos == idx - off
         IN IF pos > Len(lg) THEN lg \o entries
            ELSE IF lg[pos].term = Head(entries).term
                 THEN MergeLog(lg, off, idx, Tail(entries))
                 ELSE IF pos <= 1 THEN entries
                      ELSE SubSeq(lg, 1, pos - 1) \o entries

EntriesFrom(lg, off, nxt) ==
    LET last == off + Len(lg)
    IN IF nxt > last THEN <<>>
       ELSE IF nxt <= off THEN lg
       ELSE SubSeq(lg, nxt - off, Len(lg))

TermAt(lg, off, snapIdx, snapTerm, idx) ==
    IF idx <= 0 THEN 0
    ELSE IF idx = snapIdx THEN snapTerm
    ELSE IF idx > off /\ idx <= off + Len(lg) THEN lg[idx - off].term
    ELSE 0

AERequest(i, j, lg, off, snapIdx, snapTerm, nxt, cmt) ==
    LET prev == nxt - 1
        prevTerm == TermAt(lg, off, snapIdx, snapTerm, prev)
    IN [mtype         |-> AppendEntriesRequest,
        mterm         |-> currentTerm[i],
        mprevLogIndex |-> prev,
        mprevLogTerm  |-> prevTerm,
        mentries      |-> EntriesFrom(lg, off, nxt),
        mleaderCommit |-> cmt,
        msource       |-> i,
        mdest         |-> j]

\* One send advances next by the number of entries in that batch.
\* An empty heartbeat leaves next where it is.
NextAfterSend(off, lg, nxt) == nxt + Len(EntriesFrom(lg, off, nxt))

Median3(a, b, c) ==
    IF a >= b /\ a >= c THEN Max(b, c)
    ELSE IF b >= a /\ b >= c THEN Max(a, c)
    ELSE Max(a, b)

NewCommitFrom(lg, off, snapIdx, snapTerm, oldCommit, term, mSelf, mA, mB) ==
    LET med == Median3(mSelf, mA, mB)
    IN IF med > oldCommit /\ TermAt(lg, off, snapIdx, snapTerm, med) = term
       THEN med ELSE oldCommit

DropAndSend(req, ms, pc) ==
    LET n0 == scr.nSent
        base == messages (-) SetToBag({req})
        extra == IF Len(ms) = 0 THEN EmptyBag
                 ELSE IF Len(ms) = 1 THEN SetToBag({ms[1] @@ ("seq" :> n0 + 1)})
                 ELSE SetToBag({ms[1] @@ ("seq" :> n0 + 1),
                                ms[2] @@ ("seq" :> n0 + 2)})
    IN /\ messages' = base (+) extra
       /\ scr' = [scr EXCEPT !.nSent = n0 + Len(ms), !.pc = pc]

SendOnly(ms, pc) ==
    LET n0 == scr.nSent
        extra == IF Len(ms) = 0 THEN EmptyBag
                 ELSE IF Len(ms) = 1 THEN SetToBag({ms[1] @@ ("seq" :> n0 + 1)})
                 ELSE SetToBag({ms[1] @@ ("seq" :> n0 + 1),
                                ms[2] @@ ("seq" :> n0 + 2)})
    IN /\ messages' = messages (+) extra
       /\ scr' = [scr EXCEPT !.nSent = n0 + Len(ms), !.pc = pc]

ReplySeq(resp, req, pc) == DropAndSend(req, <<resp>>, pc)

SandInit ==
    /\ Init
    /\ scr = [pc |-> <<"Init">>, nSent |-> 0]

SandTimeout(i) ==
    /\ state[i] \in {Follower, Candidate}
    /\ i \in EffectiveConfig(i)
    /\ ~loadingSnapshot[i]
    /\ currentTerm' = [currentTerm EXCEPT ![i] = @ + 1]
    /\ votedFor' = [votedFor EXCEPT ![i] = i]
    /\ state' = [state EXCEPT ![i] = Candidate]
    /\ votesGranted' = [votesGranted EXCEPT ![i] = {i}]
    /\ LET ps == Peers(i)
           rv(d) == [mtype         |-> RequestVoteRequest,
                     mterm         |-> currentTerm[i] + 1,
                     mlastLogTerm  |-> LastLogTerm(i),
                     mlastLogIndex |-> LastLogIndex(i),
                     msource       |-> i,
                     mdest         |-> d]
       IN SendOnly(<<rv(ps[1]), rv(ps[2])>>, <<"Timeout", i>>)
    /\ UNCHANGED <<log, commitIndex, logOffset, leaderVars,
                   snapshotVars, readVars, configVars>>

SandHandleRequestVoteRequest(i, j, m) ==
    /\ IsOldest(m)
    /\ m.mtype = RequestVoteRequest
    /\ m.mdest = i
    /\ m.msource = j
    /\ LET logOk == LogUpToDate(m.mlastLogTerm, m.mlastLogIndex,
                                LastLogTerm(i), LastLogIndex(i))
           pc == <<"HandleRequestVoteRequest", i, j, m.seq>>
       IN \/ /\ m.mterm < currentTerm[i]
             /\ ReplySeq([mtype        |-> RequestVoteResponse,
                          mterm        |-> currentTerm[i],
                          mvoteGranted |-> FALSE,
                          msource      |-> i,
                          mdest        |-> j], m, pc)
             /\ UNCHANGED <<serverVars, logVars, leaderVars, candidateVars,
                            snapshotVars, readVars, configVars>>
          \/ /\ m.mterm > currentTerm[i]
             /\ currentTerm' = [currentTerm EXCEPT ![i] = m.mterm]
             /\ state' = [state EXCEPT ![i] = Follower]
             /\ votedFor' = [votedFor EXCEPT ![i] = IF logOk THEN j ELSE Nil]
             /\ ReplySeq([mtype        |-> RequestVoteResponse,
                          mterm        |-> m.mterm,
                          mvoteGranted |-> logOk,
                          msource      |-> i,
                          mdest        |-> j], m, pc)
             /\ UNCHANGED <<log, commitIndex, logOffset, leaderVars, candidateVars,
                            snapshotVars, readVars, configVars>>
          \/ /\ m.mterm = currentTerm[i]
             /\ LET canGrant == /\ \/ votedFor[i] = Nil
                                   \/ votedFor[i] = j
                                /\ logOk
                IN /\ IF canGrant
                      THEN votedFor' = [votedFor EXCEPT ![i] = j]
                      ELSE UNCHANGED votedFor
                   /\ ReplySeq([mtype        |-> RequestVoteResponse,
                                mterm        |-> currentTerm[i],
                                mvoteGranted |-> canGrant,
                                msource      |-> i,
                                mdest        |-> j], m, pc)
                   /\ UNCHANGED <<currentTerm, state, log, commitIndex, logOffset,
                                  leaderVars, candidateVars,
                                  snapshotVars, readVars, configVars>>

SandHandleRequestVoteResponse(i, j, m) ==
    /\ IsOldest(m)
    /\ m.mtype = RequestVoteResponse
    /\ m.mdest = i
    /\ m.msource = j
    /\ LET pc == <<"HandleRequestVoteResponse", i, j, m.seq>>
       IN \/ /\ m.mterm > currentTerm[i]
             /\ currentTerm' = [currentTerm EXCEPT ![i] = m.mterm]
             /\ votedFor' = [votedFor EXCEPT ![i] = Nil]
             /\ state' = [state EXCEPT ![i] = Follower]
             /\ DropAndSend(m, <<>>, pc)
             /\ UNCHANGED <<log, commitIndex, logOffset, leaderVars, candidateVars,
                            snapshotVars, readVars, configVars>>
          \/ /\ m.mterm <= currentTerm[i]
             /\ state[i] /= Candidate
             /\ DropAndSend(m, <<>>, pc)
             /\ UNCHANGED <<serverVars, logVars, leaderVars, candidateVars,
                            snapshotVars, readVars, configVars>>
          \/ /\ state[i] = Candidate
             /\ m.mterm = currentTerm[i]
             /\ m.mvoteGranted
             /\ LET votes == votesGranted[i] \cup {j}
                    won == IsQuorum(votes, EffectiveConfig(i))
                    noop == [term |-> currentTerm[i], type |-> NoopEntry, config |-> {}]
                    newLog == Append(log[i], noop)
                    newLast == logOffset[i] + Len(newLog)
                    ps == Peers(i)
                    ae(d) == AERequest(i, d, newLog, logOffset[i],
                                       snapshotLastIdx[i], snapshotLastTerm[i],
                                       newLast, commitIndex[i])
                IN /\ votesGranted' = [votesGranted EXCEPT ![i] = votes]
                   /\ IF won
                      THEN /\ log' = [log EXCEPT ![i] = newLog]
                           /\ state' = [state EXCEPT ![i] = Leader]
                           /\ nextIndex' = [nextIndex EXCEPT ![i] =
                                  [k \in Server |-> newLast + 1]]
                           /\ matchIndex' = [matchIndex EXCEPT ![i] =
                                  [k \in Server |-> IF k = i THEN newLast ELSE 0]]
                           /\ DropAndSend(m, <<ae(ps[1]), ae(ps[2])>>, pc)
                      ELSE /\ UNCHANGED <<log, state, leaderVars>>
                           /\ DropAndSend(m, <<>>, pc)
                   /\ UNCHANGED <<currentTerm, votedFor, commitIndex, logOffset,
                                  snapshotVars, readVars, configVars>>
          \/ /\ state[i] = Candidate
             /\ m.mterm <= currentTerm[i]
             /\ ~m.mvoteGranted
             /\ DropAndSend(m, <<>>, pc)
             /\ UNCHANGED <<serverVars, logVars, leaderVars, candidateVars,
                            snapshotVars, readVars, configVars>>

SandClientRequest(i) ==
    /\ state[i] = Leader
    /\ ~loadingSnapshot[i]
    /\ LET entry == [term |-> currentTerm[i], type |-> ValueEntry, config |-> {}]
           lg == Append(log[i], entry)
           newLast == logOffset[i] + Len(lg)
           ps == Peers(i)
           selfMatch == newLast
           mA == IF ps[1] = i THEN selfMatch ELSE matchIndex[i][ps[1]]
           mB == IF ps[2] = i THEN selfMatch ELSE matchIndex[i][ps[2]]
           \* Peers are never i. Match of self is selfMatch; the other two stay.
           cmt == NewCommitFrom(lg, logOffset[i], snapshotLastIdx[i], snapshotLastTerm[i],
                                commitIndex[i], currentTerm[i],
                                selfMatch, matchIndex[i][ps[1]], matchIndex[i][ps[2]])
           want(p) == nextIndex[i][p] <= newLast
           msg(p) == AERequest(i, p, lg, logOffset[i],
                               snapshotLastIdx[i], snapshotLastTerm[i],
                               nextIndex[i][p], cmt)
           ms == IF want(ps[1]) /\ want(ps[2]) THEN <<msg(ps[1]), msg(ps[2])>>
                 ELSE IF want(ps[1]) THEN <<msg(ps[1])>>
                 ELSE IF want(ps[2]) THEN <<msg(ps[2])>>
                 ELSE <<>>
           nxt(p) == IF want(p)
                     THEN NextAfterSend(logOffset[i], lg, nextIndex[i][p])
                     ELSE nextIndex[i][p]
       IN /\ log' = [log EXCEPT ![i] = lg]
          /\ matchIndex' = [matchIndex EXCEPT ![i][i] = selfMatch]
          /\ nextIndex' = [nextIndex EXCEPT ![i] =
                 [k \in Server |-> IF k = i THEN nextIndex[i][i] ELSE nxt(k)]]
          /\ commitIndex' = [commitIndex EXCEPT ![i] = cmt]
          /\ SendOnly(ms, <<"ClientRequest", i>>)
    /\ UNCHANGED <<currentTerm, votedFor, state, logOffset, candidateVars,
                   snapshotVars, readVars, configVars>>

SandAppendEntriesAll(i) ==
    /\ state[i] = Leader
    /\ LET ps == Peers(i)
           lg == log[i]
           off == logOffset[i]
           cmt == commitIndex[i]
           nAfter(p) == NextAfterSend(off, lg, nextIndex[i][p])
       IN /\ nextIndex' = [nextIndex EXCEPT ![i] =
                 [k \in Server |-> IF k = i THEN nextIndex[i][i]
                                   ELSE nAfter(k)]]
          /\ SendOnly(<<AERequest(i, ps[1], lg, off, snapshotLastIdx[i], snapshotLastTerm[i],
                                  nextIndex[i][ps[1]], cmt),
                        AERequest(i, ps[2], lg, off, snapshotLastIdx[i], snapshotLastTerm[i],
                                  nextIndex[i][ps[2]], cmt)>>,
                      <<"AppendEntriesAll", i>>)
    /\ UNCHANGED <<serverVars, log, commitIndex, logOffset, matchIndex, candidateVars,
                   snapshotVars, readVars, configVars>>

SandHandleAppendEntriesRequest(i, j, m) ==
    /\ IsOldest(m)
    /\ m.mtype = AppendEntriesRequest
    /\ m.mdest = i
    /\ m.msource = j
    /\ LET prev == m.mprevLogIndex
           entries == m.mentries
           pc == <<"HandleAppendEntriesRequest", i, j, m.seq>>
           stale == m.mterm < currentTerm[i]
           newTerm == Max(currentTerm[i], m.mterm)
           prevIsSnap == prev = snapshotLastIdx[i]
           snapTermOk == snapshotLastTerm[i] = m.mprevLogTerm
           hasPrev == prev > logOffset[i] /\ prev <= LastLogIndex(i)
           prevTermOk == hasPrev /\ LogTerm(i, prev) = m.mprevLogTerm
           prevOk == \/ /\ prevIsSnap /\ snapTermOk
                     \/ prevTermOk
                     \/ prev = 0 /\ snapshotLastIdx[i] = 0
           conflict == hasPrev /\ LogTerm(i, prev) /= m.mprevLogTerm /\ prev > commitIndex[i]
           truncated == IF prev - logOffset[i] <= 1 THEN <<>>
                        ELSE SubSeq(log[i], 1, prev - logOffset[i] - 1)
           newLog == IF stale THEN log[i]
                     ELSE IF conflict THEN truncated
                     ELSE IF prevOk THEN MergeLog(log[i], logOffset[i], prev, entries)
                     ELSE log[i]
           newLast == logOffset[i] + Len(newLog)
           success == ~stale /\ prevOk
           newCommit == IF success
                        THEN Max(commitIndex[i], Min(m.mleaderCommit, newLast))
                        ELSE commitIndex[i]
           respIdx == IF success THEN prev + Len(entries) ELSE newLast
           resp == [mtype       |-> AppendEntriesResponse,
                    mterm       |-> newTerm,
                    msuccess    |-> success,
                    mmatchIndex |-> respIdx,
                    msource     |-> i,
                    mdest       |-> j]
       IN /\ currentTerm' = [currentTerm EXCEPT ![i] = newTerm]
          /\ votedFor' = [votedFor EXCEPT ![i] =
                 IF m.mterm > currentTerm[i] THEN Nil ELSE votedFor[i]]
          /\ state' = [state EXCEPT ![i] = IF stale THEN state[i] ELSE Follower]
          /\ log' = [log EXCEPT ![i] = newLog]
          /\ commitIndex' = [commitIndex EXCEPT ![i] = newCommit]
          /\ ReplySeq(resp, m, pc)
          /\ UNCHANGED <<logOffset, leaderVars, candidateVars,
                         snapshotVars, readVars, configVars>>

SandHandleAppendEntriesResponse(i, j, m) ==
    /\ IsOldest(m)
    /\ m.mtype = AppendEntriesResponse
    /\ m.mdest = i
    /\ m.msource = j
    /\ LET pc == <<"HandleAppendEntriesResponse", i, j, m.seq>>
       IN \/ /\ state[i] /= Leader
             /\ DropAndSend(m, <<>>, pc)
             /\ UNCHANGED <<serverVars, logVars, leaderVars, candidateVars,
                            snapshotVars, readVars, configVars>>
          \/ /\ state[i] = Leader
             /\ m.mterm > currentTerm[i]
             /\ currentTerm' = [currentTerm EXCEPT ![i] = m.mterm]
             /\ votedFor' = [votedFor EXCEPT ![i] = Nil]
             /\ state' = [state EXCEPT ![i] = Follower]
             /\ DropAndSend(m, <<>>, pc)
             /\ UNCHANGED <<log, commitIndex, logOffset, leaderVars, candidateVars,
                            snapshotVars, readVars, configVars>>
          \/ /\ state[i] = Leader
             /\ m.mterm < currentTerm[i]
             /\ DropAndSend(m, <<>>, pc)
             /\ UNCHANGED <<serverVars, logVars, leaderVars, candidateVars,
                            snapshotVars, readVars, configVars>>
          \/ /\ state[i] = Leader
             /\ m.mterm = currentTerm[i]
             /\ ~m.msuccess
             /\ m.mmatchIndex < matchIndex[i][j]
             /\ DropAndSend(m, <<>>, pc)
             /\ UNCHANGED <<serverVars, logVars, leaderVars, candidateVars,
                            snapshotVars, readVars, configVars>>
          \/ /\ state[i] = Leader
             /\ m.mterm = currentTerm[i]
             /\ ~m.msuccess
             /\ m.mmatchIndex >= matchIndex[i][j]
             /\ LET raw == Min(m.mmatchIndex + 1, LastLogIndex(i))
                    backed == IF raw < 1 THEN 1 ELSE raw
                    cmt == commitIndex[i]
                    msg == AERequest(i, j, log[i], logOffset[i],
                                     snapshotLastIdx[i], snapshotLastTerm[i],
                                     backed, cmt)
                    nxt == NextAfterSend(logOffset[i], log[i], backed)
                IN /\ nextIndex' = [nextIndex EXCEPT ![i][j] = nxt]
                   /\ DropAndSend(m, <<msg>>, pc)
                   /\ UNCHANGED <<serverVars, log, commitIndex, logOffset, matchIndex,
                                  candidateVars, snapshotVars, readVars, configVars>>
          \/ /\ state[i] = Leader
             /\ m.mterm = currentTerm[i]
             /\ m.msuccess
             /\ LET newMatch == Max(matchIndex[i][j], m.mmatchIndex)
                    ps == Peers(i)
                    other == IF ps[1] = j THEN ps[2] ELSE ps[1]
                    cmt == NewCommitFrom(log[i], logOffset[i], snapshotLastIdx[i],
                                         snapshotLastTerm[i], commitIndex[i], currentTerm[i],
                                         matchIndex[i][i],
                                         IF ps[1] = j THEN newMatch ELSE matchIndex[i][ps[1]],
                                         IF ps[2] = j THEN newMatch ELSE matchIndex[i][ps[2]])
                    \* raft_flush sends only while next <= current index.
                    send(p, nxt0) == nxt0 <= LastLogIndex(i)
                    msg(p, nxt0) == AERequest(i, p, log[i], logOffset[i],
                                              snapshotLastIdx[i], snapshotLastTerm[i],
                                              nxt0, cmt)
                    nxtOf(p) == IF p = j THEN nextIndex[i][j]
                                ELSE nextIndex[i][p]
                    \* The peer that just replied keeps the next set at send time.
                    \* Other peers are flushed too.
                    ms == IF send(j, nextIndex[i][j]) /\ send(other, nextIndex[i][other])
                          THEN <<msg(ps[1], nextIndex[i][ps[1]]),
                                 msg(ps[2], nextIndex[i][ps[2]])>>
                          ELSE IF send(ps[1], nextIndex[i][ps[1]])
                               THEN <<msg(ps[1], nextIndex[i][ps[1]])>>
                          ELSE IF send(ps[2], nextIndex[i][ps[2]])
                               THEN <<msg(ps[2], nextIndex[i][ps[2]])>>
                          ELSE <<>>
                    advanced(p) == IF send(p, nextIndex[i][p])
                                   THEN NextAfterSend(logOffset[i], log[i], nextIndex[i][p])
                                   ELSE nextIndex[i][p]
                IN /\ matchIndex' = [matchIndex EXCEPT ![i][j] = newMatch]
                   /\ commitIndex' = [commitIndex EXCEPT ![i] = cmt]
                   /\ nextIndex' = [nextIndex EXCEPT ![i] =
                          [k \in Server |-> IF k = i THEN nextIndex[i][i] ELSE advanced(k)]]
                   /\ DropAndSend(m, ms, pc)
                   /\ UNCHANGED <<serverVars, log, logOffset, candidateVars,
                                  snapshotVars, readVars, configVars>>

SoleOnChannel(m) ==
    /\ BagIn(m, messages)
    /\ messages[m] = 1
    /\ \A other \in BagToSet(messages) :
         (other.msource = m.msource /\ other.mdest = m.mdest) => other = m

SandLoseMessage(m) ==
    /\ SoleOnChannel(m)
    /\ Discard(m)
    /\ scr' = [scr EXCEPT !.pc = <<"LoseMessage", m.msource, m.mdest, m.seq>>]
    /\ UNCHANGED <<serverVars, logVars, leaderVars, candidateVars,
                   snapshotVars, readVars, configVars>>

=============================================================================
