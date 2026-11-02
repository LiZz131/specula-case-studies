---- MODULE MC_witness ----
\* Same next-state relation as MC_for_sandtable. The invariant is only a
\* stop condition: the first finished snapshot load. SnapshotLimit is
\* raised in the cfg because TakeSnapshot and SendInstallSnapshot share
\* one counter, and a depth-30 walk spends it on TakeSnapshot.
EXTENDS MC_for_sandtable

LoadFinished(i) ==
    /\ pendingSnapshotIdx[i] > 0
    /\ loadingSnapshot[i] = FALSE
    /\ snapshotLastIdx[i] = pendingSnapshotIdx[i]

NoFinishedLoad == \A i \in Server : ~LoadFinished(i)
====
