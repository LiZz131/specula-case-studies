---- MODULE MC_for_sandtable_witness ----
\* Same actions as MC_for_sandtable. The invariant is the pre-fix
\* LeaderCompleteness from spec/MC_witness.tla. It does not change any action.
EXTENDS MC_for_sandtable

StaleLeaderWitness ==
    \A i \in Server :
        state[i] = Leader =>
        \A j \in Server :
            \A idx \in 1..commitIndex[j] :
                idx > snapshotLastIdx[i] /\ idx > snapshotLastIdx[j] =>
                (idx <= LastLogIndex(i) /\
                 LogTermAt(i, idx) = LogTermAt(j, idx))

====
