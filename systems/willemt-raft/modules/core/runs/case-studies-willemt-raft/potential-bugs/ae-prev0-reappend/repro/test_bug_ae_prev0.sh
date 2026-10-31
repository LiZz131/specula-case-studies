#!/bin/sh
# Level 0. Replay the saved TLC trace through the three-node driver.
# Expect: Variable "log" compare failed, n3 has 5 entries and the model has 2.
set -e
ROOT=/root/sandtable/specula-ce
MC=$ROOT/potential-bugs/ae-prev0-reappend/t0104/MC.out
exec bash "$ROOT/sandtable/scripts/run_one_testcase.sh" "$MC" 3
