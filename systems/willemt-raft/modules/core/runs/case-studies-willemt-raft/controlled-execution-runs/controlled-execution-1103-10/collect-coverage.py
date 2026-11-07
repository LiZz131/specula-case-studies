#!/usr/bin/env python3
"""Replay this round's traces once per config and record the line-coverage curve.

gcda stays for the traces of one config and is cleared before the next config.
The notes embedded in the binary point at the build that produced it. Those
sources match this round's system tree byte for byte. lcov paths are rewritten
to this round's system sources.
"""

import json
import os
import re
import subprocess
import time

CE = os.path.dirname(os.path.abspath(__file__))
HOST = "/users/bingzhuo/sandtable/build/mount/specula-wraft-1103-10"
NOTE = (
    "/root/sandtable/specula-wraft-1103-2/sandtable/cmake-build-debug/"
    "drivers/CMakeFiles/WRaftDriver.dir/root/sandtable/specula-wraft-1103-2/system/src"
)
SYSTEM = os.path.join(CE, "system", "src")
CONFIGS = [
    "standard",
    "hunt_broadcast",
    "hunt_commit",
    "hunt_commit_witness",
    "hunt_log",
    "hunt_snapshot",
    "hunt_vote",
]
SOURCES = [
    "raft_log.c",
    "raft_node.c",
    "raft_server.c",
    "raft_server_properties.c",
]
LINE_RE = re.compile(r"^ *(-|#####|\d+): *(\d+):")
BRANCH_RE = re.compile(r"^branch +\d+ (never executed|taken (\d+)%)")
FUNC_RE = re.compile(r"^function (\S+) called (\d+) ")


def run(cmd, timeout=300, check=True):
    proc = subprocess.run(
        cmd, shell=True, text=True, capture_output=True, timeout=timeout
    )
    if check and proc.returncode != 0:
        tail = (proc.stdout + "\n" + proc.stderr)[-4000:]
        raise RuntimeError("command failed (%s): %s\n%s" % (proc.returncode, cmd, tail))
    return proc


def verdict(path):
    if not os.path.isfile(path):
        return "no-log"
    text = open(path, errors="replace").read()
    if re.search(r'Variable ".*" compare failed', text):
        return "variable"
    if "Net mgs length compare failed" in text:
        return "net-len"
    if re.search(r"Sanitizer|Assertion|Aborted|stack smashing", text):
        return "abort"
    if "logout" not in text:
        return "no-logout"
    return "pass"


def clear_gcda():
    for node in ("n1", "n2", "n3"):
        run("sudo docker exec %s rm -rf /tmp/gcov-%s" % (node, node))


def replay(config, trace):
    work = "%s/work/cov-%s-%s" % (HOST, config, trace)
    mc = os.path.join(CE, config, "traces", trace, "MC.out")
    run("sudo rm -rf '%s' && sudo mkdir -p '%s' && sudo cp '%s' '%s/MC.out'" % (work, work, mc, work))
    for node in ("n1", "n2", "n3"):
        run("sudo docker exec %s rm -f /tmp/wraft-persist-%s" % (node, node))
    started = time.time()
    proc = run(
        "timeout 240 sudo docker exec controller bash -lc '"
        "cd /root/sandtable/specula-wraft-1103-10/sandtable/systems/WRaft-series/SpeculaWRaft/scripts && "
        "bash ./run_one_testcase.sh /root/sandtable/specula-wraft-1103-10/work/cov-%s-%s/MC.out 3'"
        % (config, trace),
        timeout=260,
        check=False,
    )
    elapsed = int(round(time.time() - started))
    log = "/tmp/wraft-cov-%s-%s.host" % (config, trace)
    run("sudo cp '%s/test/log.host' '%s' && sudo chmod a+r '%s'" % (work, log, log), check=False)
    run("sudo rm -rf '%s'" % work, check=False)
    return elapsed, verdict(log), proc.returncode


def measure_json():
    stage = "/tmp/wraft-gcov-stage"
    if os.path.isdir(stage):
        run("sudo rm -rf '%s'" % stage)
    os.makedirs(stage, exist_ok=True)
    for node in ("n1", "n2", "n3"):
        proc = run(
            "sudo docker cp %s:/tmp/gcov-%s %s/%s" % (node, node, stage, node),
            check=False,
        )
        if proc.returncode != 0:
            os.makedirs(os.path.join(stage, node), exist_ok=True)
            run("sudo chown -R $(id -u):$(id -g) '%s/%s'" % (stage, node), check=False)
    run("sudo docker exec controller rm -rf /tmp/gcov-merge /tmp/gcov-report")
    run("sudo docker exec controller mkdir -p /tmp/gcov-merge /tmp/gcov-report")
    for node in ("n1", "n2", "n3"):
        run("sudo docker cp %s/%s controller:/tmp/gcov-merge/%s" % (stage, node, node))
    inner = r"""
set -e
if find /tmp/gcov-merge/n1 /tmp/gcov-merge/n2 -name '*.gcda' | grep -q .; then
  gcov-tool merge -o /tmp/gcov-merge/m12 /tmp/gcov-merge/n1 /tmp/gcov-merge/n2
else
  mkdir -p /tmp/gcov-merge/m12
fi
if find /tmp/gcov-merge/m12 /tmp/gcov-merge/n3 -name '*.gcda' | grep -q .; then
  gcov-tool merge -o /tmp/gcov-merge/all /tmp/gcov-merge/m12 /tmp/gcov-merge/n3
else
  mkdir -p /tmp/gcov-merge/all
fi
SRC=$(find /tmp/gcov-merge/all -type d -name src | head -1)
test -n "$SRC"
cp -f "$SRC"/*.gcda "%s"/
cd /tmp/gcov-report
gcov -b %s > /tmp/gcov-report/gcov.out
rm -f "%s"/*.gcda
""" % (
        NOTE,
        " ".join("%s/%s.gcno" % (NOTE, name) for name in SOURCES),
        NOTE,
    )
    proc = subprocess.run(
        ["sudo", "docker", "exec", "-i", "controller", "bash", "-s"],
        input=inner,
        text=True,
        capture_output=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout[-2000:] + "\n" + proc.stderr[-2000:])
    parsed = subprocess.run(
        ["sudo", "docker", "exec", "-i", "controller", "python3", "-"],
        input=PARSE,
        text=True,
        capture_output=True,
        timeout=60,
    )
    if parsed.returncode != 0:
        raise RuntimeError(parsed.stdout[-2000:] + "\n" + parsed.stderr[-2000:])
    line = parsed.stdout.strip().splitlines()[-1]
    return json.loads(line)


PARSE = r"""
import json, re
line_re = re.compile(r"^ *(-|#####|\d+): *(\d+):")
branch_re = re.compile(r"^branch +\d+ (never executed|taken (\d+)%)")
func_re = re.compile(r"^function (\S+) called (\d+) ")
sources = SOURCES_JSON
files = []
funcs = {}
for name in sources:
    lines = open("/tmp/gcov-report/" + name + ".gcov", errors="replace").read().splitlines()
    exec_n = hit = branches = taken = 0
    for line in lines:
        m = line_re.match(line)
        if m:
            mark = m.group(1)
            if mark == "-":
                continue
            exec_n += 1
            if mark != "#####":
                hit += 1
            continue
        b = branch_re.match(line)
        if b:
            branches += 1
            if b.group(2) is not None and int(b.group(2)) > 0:
                taken += 1
            continue
        f = func_re.match(line)
        if f:
            funcs[f.group(1)] = int(f.group(2))
    files.append({
        "name": name,
        "lines": exec_n,
        "lines_hit": hit,
        "branches": branches,
        "branches_taken": taken,
    })
print(json.dumps({"files": files, "functions": funcs}))
""".replace("SOURCES_JSON", json.dumps(SOURCES))


def pct(hit, total):
    if total == 0:
        return 0.0
    return round(100.0 * hit / total, 2)


def summarize(measured):
    files = []
    lines = hit = branches = taken = 0
    for item in measured["files"]:
        lines += item["lines"]
        hit += item["lines_hit"]
        branches += item["branches"]
        taken += item["branches_taken"]
        files.append({
            "name": item["name"],
            "line_pct": pct(item["lines_hit"], item["lines"]),
            "branch_taken_pct": pct(item["branches_taken"], item["branches"]),
            "lines": item["lines"],
            "lines_hit": item["lines_hit"],
            "branches": item["branches"],
            "branches_taken": item["branches_taken"],
        })
    return {
        "line_pct": pct(hit, lines),
        "branch_taken_pct": pct(taken, branches),
        "lines": lines,
        "lines_hit": hit,
        "branches": branches,
        "branches_taken": taken,
        "files": files,
        "functions": measured["functions"],
    }


def load_rows(path):
    if not os.path.isfile(path):
        return []
    return json.load(open(path))


def save_rows(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w") as handle:
        json.dump(rows, handle, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def copy_gcov(config):
    dest = os.path.join(CE, config, "gcov")
    os.makedirs(dest, exist_ok=True)
    run("sudo docker cp controller:/tmp/gcov-report/. %s/" % dest)
    run("sudo chown -R $(id -u):$(id -g) '%s'" % dest)


def one_config(config):
    dest = os.path.join(CE, config, "coverage.json")
    rows = load_rows(dest)
    if len(rows) >= 100:
        print("CFG %s already-complete %d" % (config, len(rows)), flush=True)
        return rows
    if not rows:
        clear_gcda()
    start = len(rows) + 1
    for seed in range(start, 101):
        trace = "t%04d" % seed
        status = os.path.join(CE, config, "traces", trace, "replay.status")
        original = open(status).readline().strip() if os.path.isfile(status) else ""
        elapsed, found, code = replay(config, trace)
        if original == "pass" and found != "pass":
            print(
                "COV_FAIL %s %s coverage-replay %s exit %s" % (config, trace, found, code),
                flush=True,
            )
            raise SystemExit(2)
        measured = summarize(measure_json())
        row = {
            "trace": trace,
            "replay_s": elapsed,
            "ok": original == "pass",
        }
        row.update(measured)
        rows.append(row)
        save_rows(dest, rows)
        print(
            "COV %s %s line %s hit %s branch %s ok %s %ss"
            % (
                config,
                trace,
                row["line_pct"],
                row["lines_hit"],
                row["branch_taken_pct"],
                row["ok"],
                elapsed,
            ),
            flush=True,
        )
    copy_gcov(config)
    plateau = 1
    last = rows[0]["lines_hit"]
    for index, row in enumerate(rows, start=1):
        if row["lines_hit"] > last:
            plateau = index
            last = row["lines_hit"]
    rising = "STILL_RISING" if plateau == len(rows) else "plateau %s" % rows[plateau - 1]["trace"]
    print(
        "CFG %s traces=%d lines_hit=%d %s" % (config, len(rows), rows[-1]["lines_hit"], rising),
        flush=True,
    )
    return rows


ACTIONS = {
    "Timeout": ["raft_periodic"],
    "Broadcast": ["raft_periodic"],
    "ClientRequest": ["raft_recv_entry"],
    "HandleAppendEntriesRequest": ["raft_recv_appendentries"],
    "HandleAppendEntriesResponse": ["raft_recv_appendentries_response"],
    "HandleRequestVoteRequest": ["raft_recv_requestvote"],
    "HandleRequestVoteResponse": ["raft_recv_requestvote_response"],
    "HandleInstallSnapshot": ["raft_recv_installsnapshot"],
    "TakeSnapshot": ["raft_begin_snapshot", "raft_end_snapshot"],
    "SendAppendEntries": ["raft_send_appendentries"],
}


def actions_seen():
    seen = set()
    for config in CONFIGS:
        root = os.path.join(CE, config, "traces")
        for dirpath, _, filenames in os.walk(root):
            if "MC.out" not in filenames:
                continue
            text = open(os.path.join(dirpath, "MC.out"), errors="replace").read()
            for action in ACTIONS:
                if ('<<"%s"' % action) in text:
                    seen.add(action)
    return seen


def build_union():
    counts = {name: {} for name in SOURCES}
    functions = {}
    for config in CONFIGS:
        for name in SOURCES:
            path = os.path.join(CE, config, "gcov", name + ".gcov")
            for line in open(path, errors="replace"):
                match = LINE_RE.match(line)
                if not match or match.group(1) == "-":
                    continue
                lineno = int(match.group(2))
                count = 0 if match.group(1) == "#####" else int(match.group(1))
                previous = counts[name].get(lineno, 0)
                if count > previous:
                    counts[name][lineno] = count
                elif lineno not in counts[name]:
                    counts[name][lineno] = 0
            for line in open(path, errors="replace"):
                func = FUNC_RE.match(line)
                if func:
                    functions[func.group(1)] = max(
                        functions.get(func.group(1), 0), int(func.group(2))
                    )
    lcov_path = os.path.join(CE, "lcov.info")
    uncovered_path = os.path.join(CE, "uncovered.txt")
    uncovered = []
    with open(lcov_path, "w") as handle:
        for name in SOURCES:
            source = os.path.join(SYSTEM, name)
            handle.write("SF:%s\n" % source)
            hit = 0
            for lineno in sorted(counts[name]):
                count = counts[name][lineno]
                handle.write("DA:%d,%d\n" % (lineno, count))
                if count > 0:
                    hit += 1
                else:
                    uncovered.append("%s:%d" % (name, lineno))
            handle.write("LH:%d\n" % hit)
            handle.write("LF:%d\n" % len(counts[name]))
            handle.write("end_of_record\n")
    seen = actions_seen()
    called0 = []
    for action in sorted(seen):
        for func in ACTIONS[action]:
            if functions.get(func, 0) == 0 and func not in called0:
                called0.append(func)
    with open(uncovered_path, "w") as handle:
        for item in uncovered:
            handle.write(item + "\n")
        for func in called0:
            handle.write("# called 0 %s\n" % func)
    with open(os.path.join(CE, "functions.json"), "w") as handle:
        json.dump(functions, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        "COV_DONE lines %d uncovered %d called0 %d"
        % (
            sum(len(item) for item in counts.values()),
            len(uncovered),
            sum(1 for value in functions.values() if value == 0),
        ),
        flush=True,
    )


def main():
    try:
        for config in CONFIGS:
            one_config(config)
        build_union()
    except SystemExit:
        raise
    except Exception as exc:
        print("COV_FAIL %s" % exc, flush=True)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
