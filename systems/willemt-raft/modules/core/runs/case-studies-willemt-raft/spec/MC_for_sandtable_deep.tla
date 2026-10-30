---- MODULE MC_for_sandtable_deep ----
\* Same transitions as MC_for_sandtable. The only difference is a later
\* cutoff, so a random walk can deliver an InstallSnapshot that TakeSnapshot
\* emits near the end of a 30-step trace.
EXTENDS MC_for_sandtable

DepthBoundDeep == TLCGet("level") < 81

====
