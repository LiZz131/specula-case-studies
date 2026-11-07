#!/bin/bash
# Sample and replay this round. Stop on the first trace that is not a clean variable match.
set -u
CE=/users/bingzhuo/Specula/case-studies/systems/willemt-raft/modules/core/runs/case-studies-willemt-raft/controlled-execution-runs/controlled-execution-1103-9
SPEC=$CE/spec
JAR=/users/bingzhuo/.cursor-server/extensions/alygin.vscode-tlaplus-nightly-2024.8.1506-universal/tools/tla2tools.jar
HOST=/users/bingzhuo/sandtable/build/mount/specula-wraft-1103-9
NAMES=(standard hunt_broadcast hunt_commit hunt_commit_witness hunt_log hunt_snapshot hunt_vote)
CFGS=(
    MC_for_sandtable.cfg
    MC_for_sandtable_hunt_broadcast.cfg
    MC_for_sandtable_hunt_commit.cfg
    MC_for_sandtable_hunt_commit_witness.cfg
    MC_for_sandtable_hunt_log.cfg
    MC_for_sandtable_hunt_snapshot.cfg
    MC_for_sandtable_hunt_vote.cfg
)

judge() {
    local log=$1
    if [ ! -f "$log" ]; then
        echo "no-log"
        return
    fi
    if grep -q 'Variable ".*" compare failed' "$log"; then
        echo "variable"
        return
    fi
    if grep -q 'Net mgs length compare failed' "$log"; then
        echo "net-len"
        return
    fi
    if grep -Eq 'Sanitizer|Assertion|Aborted|stack smashing' "$log"; then
        echo "abort"
        return
    fi
    if ! grep -q 'logout' "$log"; then
        echo "no-logout"
        return
    fi
    echo "pass"
}

for i in "${!NAMES[@]}"; do
    name=${NAMES[$i]}
    cfg=${CFGS[$i]}
    for seed in $(seq 1 100); do
        id=$(printf 't%04d' "$seed")
        dest=$CE/$name/traces/$id
        if [ -f "$dest/replay.status" ]; then
            continue
        fi
        mkdir -p "$dest"
        meta=/tmp/tlc-wraft9-$name-$seed
        rm -rf "$meta"
        start=$(date +%s)
        set +e
        java -Xmx512m -XX:+UseParallelGC -jar "$JAR" -tool -workers 1 -simulate \
            -depth 50 -seed "$seed" -metadir "$meta" \
            -config "$SPEC/$cfg" "$SPEC/MC_for_sandtable" > "$dest/MC.out" 2>&1
        tlc=$?
        set -e
        rm -rf "$meta"
        if grep -q 'Parse Error\|Semantic processing of module base_for_sandtable' "$dest/MC.out" && ! grep -q 'Finished' "$dest/MC.out"; then
            echo "FAIL $name $id tlc-parse"
            exit 2
        fi
        inv=$(grep -o 'Invariant .* is violated' "$dest/MC.out" | head -1 || true)
        if [ -n "$inv" ] && [ "$inv" != "Invariant DepthBound is violated" ]; then
            printf '%s\n' "tlc-invariant" "$inv" "exit $tlc" > "$dest/replay.status"
            echo "FAIL $name $id $inv"
            exit 2
        fi
        if ! grep -q 'pc |->' "$dest/MC.out"; then
            printf '%s\n' "tlc-no-pc" "exit $tlc" > "$dest/replay.status"
            echo "FAIL $name $id tlc-no-pc exit $tlc"
            exit 2
        fi
        work=$HOST/work/$name-$id
        sudo rm -rf "$work"
        sudo mkdir -p "$work"
        sudo cp "$dest/MC.out" "$work/MC.out"
        sudo docker exec n1 bash -lc 'rm -f /tmp/wraft-persist-n1'
        sudo docker exec n2 bash -lc 'rm -f /tmp/wraft-persist-n2'
        sudo docker exec n3 bash -lc 'rm -f /tmp/wraft-persist-n3'
        set +e
        timeout 240 sudo docker exec controller bash -lc "
            cd /root/sandtable/specula-wraft-1103-9/sandtable/systems/WRaft-series/SpeculaWRaft/scripts
            bash ./run_one_testcase.sh /root/sandtable/specula-wraft-1103-9/work/$name-$id/MC.out 3
        " > "$dest/replay.out" 2>&1
        replay=$?
        set -e
        if [ -f "$work/test/traces.txt" ]; then
            sudo cp "$work/test/traces.txt" "$dest/traces.txt"
            sudo chown --reference="$dest/MC.out" "$dest/traces.txt"
        fi
        if [ -f "$work/test/log.host" ]; then
            sudo cp "$work/test/log.host" "$dest/log.host"
            sudo chown --reference="$dest/MC.out" "$dest/log.host"
        fi
        end=$(date +%s)
        verdict=$(judge "$dest/log.host")
        printf '%s\n' "$verdict" "exit $replay" "seconds $((end - start))" > "$dest/replay.status"
        if [ "$verdict" != "pass" ]; then
            echo "FAIL $name $id $verdict exit $replay"
            exit 2
        fi
        echo "OK $name $id ${tlc} $((end - start))s"
    done
done
echo ALL_PASS
