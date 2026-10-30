---- MODULE MC_witness ----
\* Search wrapper. Protocol actions are exactly MC / base.
\* StaleLeaderWitness is the LeaderCompleteness check from before the
\* term guard was added (bug-report.md). It does not change any action.
EXTENDS MC

StaleLeaderWitness ==
    \A i \in Server :
        state[i] = Leader =>
        \A j \in Server :
            \A idx \in 1..commitIndex[j] :
                idx > snapshotLastIdx[i] /\ idx > snapshotLastIdx[j] =>
                (idx <= LastLogIndex(i) /\
                 LogTermAt(i, idx) = LogTermAt(j, idx))

====
