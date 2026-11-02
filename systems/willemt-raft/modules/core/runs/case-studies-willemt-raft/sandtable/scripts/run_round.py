#!/usr/bin/env python3
"""Sample and replay one SandTable controlled-execution round.

Canonical outputs stay under the Specula run. The SandTable mount receives
only a working copy the controller can read. The SandTable git tree is not
modified.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

RUN = Path("/users/bingzhuo/Specula/case-studies/systems/willemt-raft/modules/core/runs/case-studies-willemt-raft")
MOUNT = Path("/users/bingzhuo/sandtable/build/mount/specula-ce")
CONTAINER_ROOT = "/root/sandtable/specula-ce"
JAR = Path("/users/bingzhuo/sandtable/scripts/tla2tools.jar")
SPEC = RUN / "spec"
ROUND = "controlled-execution-1101-1"
ROUND_DIR = RUN / "controlled-execution-runs" / ROUND

CONFIGS = [
    ("standard", "MC_for_sandtable.cfg", "MC_for_sandtable", 50),
    ("broadcast", "MC_for_sandtable_broadcast.cfg", "MC_for_sandtable", 50),
    ("commit", "MC_for_sandtable_commit.cfg", "MC_for_sandtable", 50),
    ("log", "MC_for_sandtable_log.cfg", "MC_for_sandtable", 50),
    ("snapshot", "MC_for_sandtable_snapshot.cfg", "MC_for_sandtable", 50),
    ("vote", "MC_for_sandtable_vote.cfg", "MC_for_sandtable", 50),
    ("logcap", "MC_for_sandtable_logcap.cfg", "MC_for_sandtable_deep", 120),
]

LINE_RE = re.compile(r"^\s*(#####|\d+\*?):\s*(\d+):")
FILE_SUM_RE = re.compile(
    r"^(?:File '(?P<file>[^']+)'\n)?"
    r"Lines executed:(?P<line_pct>[\d.]+)% of (?P<lines>\d+)\n"
    r"(?:Branches executed:(?P<bexec>[\d.]+)% of (?P<branches>\d+)\n"
    r"Taken at least once:(?P<taken>[\d.]+)% of (?P<branches2>\d+)\n)?",
    re.M,
)
FUNC_RE = re.compile(r"^function\s+(\S+)\s+called\s+(\d+)", re.M)


def trace_name(seed):
    return "t%04d" % seed


def trace_dir(config, seed):
    return ROUND_DIR / config / "traces" / trace_name(seed)


def run(cmd, timeout=None, cwd=None, check=False):
    return subprocess.run(
        cmd, cwd=cwd, timeout=timeout, check=check,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def sync_working_copy():
    MOUNT.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["rsync", "-a", str(RUN / "artifact") + "/", str(MOUNT / "artifact") + "/"],
        check=True,
    )
    subprocess.run(
        ["rsync", "-a", "--exclude", "driver/build",
         str(RUN / "sandtable") + "/", str(MOUNT / "sandtable") + "/"],
        check=True,
    )
    for script in (MOUNT / "sandtable" / "scripts").glob("*.sh"):
        script.chmod(0o755)


def build_driver():
    sync_working_copy()
    cmd = (
        "set -e; cd /root/sandtable/specula-ce/sandtable/driver; "
        "cmake -S . -B build >/tmp/specula-ce-cmake.log; "
        "cmake --build build -j$(nproc) >>/tmp/specula-ce-cmake.log"
    )
    result = run(["sudo", "docker", "exec", "controller", "bash", "-lc", cmd], timeout=180)
    if result.returncode != 0:
        log = run(["sudo", "docker", "exec", "controller", "bash", "-lc",
                   "tail -80 /tmp/specula-ce-cmake.log"])
        raise SystemExit("driver build failed\n" + result.stderr + "\n" + log.stdout)
    binary = MOUNT / "sandtable" / "driver" / "build" / "WRaftDriver"
    if not binary.is_file():
        raise SystemExit("WRaftDriver missing after build")


def tlc_one(config, cfg, module, depth, seed):
    dest = trace_dir(config, seed)
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / "MC.out"
    if out.is_file() and "pc |->" in out.read_text(errors="replace"):
        return config, seed, "cached"
    meta = Path("/tmp") / ("tlc-%s-%d" % (config, seed))
    if meta.exists():
        shutil.rmtree(meta, ignore_errors=True)
    cmd = [
        "java", "-Xmx512m", "-jar", str(JAR),
        "-tool", "-workers", "1", "-simulate",
        "-depth", str(depth), "-seed", str(seed),
        "-metadir", str(meta),
        "-config", cfg, module,
    ]
    result = subprocess.run(
        cmd, cwd=SPEC, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    text = result.stdout
    if "@!" not in text:
        text = result.stdout + "\n" + result.stderr
    out.write_text(text)
    (dest / "tlc.err").write_text(result.stderr)
    (dest / "tlc.status").write_text(str(result.returncode))
    shutil.rmtree(meta, ignore_errors=True)
    if "label" not in text and "pc |->" not in text:
        return config, seed, "no-pc"
    if "Invariant DepthBound is violated" in text or "Invariant DepthBoundDeep is violated" in text:
        kind = "depth"
    elif "is violated" in text:
        kind = "safety"
    else:
        kind = "short"
    return config, seed, kind


def sample(configs, seeds, jobs):
    tasks = []
    for name, cfg, module, depth in CONFIGS:
        if name not in configs:
            continue
        for seed in seeds:
            tasks.append((name, cfg, module, depth, seed))
    print("sampling %d traces" % len(tasks), flush=True)
    done = 0
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(tlc_one, *task) for task in tasks]
        for fut in as_completed(futures):
            config, seed, kind = fut.result()
            done += 1
            if kind not in ("cached", "depth") or done % 25 == 0 or done == len(tasks):
                print("tlc %d/%d %s %s %s" % (done, len(tasks), config, trace_name(seed), kind), flush=True)


def clear_gcda():
    for node in ("n1", "n2", "n3"):
        run(["sudo", "docker", "exec", node, "bash", "-lc",
             "rm -rf /tmp/gcov-%s" % node], timeout=60)
    run(["sudo", "docker", "exec", "controller", "bash", "-lc",
         "find /root/sandtable/specula-ce/sandtable/driver/build -name '*.gcda' -delete"],
        timeout=60)


def replay_one(config, seed):
    src = trace_dir(config, seed) / "MC.out"
    if not src.is_file() or "pc |->" not in src.read_text(errors="replace"):
        raise RuntimeError("missing MC.out for %s %s" % (config, seed))
    host_work = MOUNT / "work" / config / trace_name(seed)
    run(["sudo", "rm", "-rf", str(host_work)], timeout=60)
    host_work.mkdir(parents=True)
    shutil.copy(src, host_work / "MC.out")
    container_mc = "%s/work/%s/%s/MC.out" % (CONTAINER_ROOT, config, trace_name(seed))
    script = CONTAINER_ROOT + "/sandtable/scripts/run_one_testcase.sh"
    started = time.monotonic()
    result = run(
        ["sudo", "docker", "exec", "controller", "bash", script, container_mc, "3"],
        timeout=180,
    )
    elapsed = time.monotonic() - started
    log_host = host_work / "test" / "log.host"
    traces = host_work / "test" / "traces.txt"
    if not log_host.is_file():
        found = list(host_work.rglob("log.host"))
        log_host = found[0] if found else None
    if not traces.is_file():
        found = list(host_work.rglob("traces.txt"))
        traces = found[0] if found else None
    dest = trace_dir(config, seed)
    if traces and traces.is_file():
        shutil.copy(traces, dest / "traces.txt")
    if log_host and Path(log_host).is_file():
        shutil.copy(log_host, dest / "log.host")
    (dest / "replay.status").write_text(
        "exit %s\n%s\n%s" % (result.returncode, result.stdout[-2000:], result.stderr[-2000:])
    )
    run(["sudo", "rm", "-rf", str(host_work)], timeout=60)
    return elapsed, result.returncode


def judge(config, seed):
    path = trace_dir(config, seed) / "log.host"
    if not path.is_file():
        return {"ok": False, "logout": False, "variable_fail": True, "netlen_warn": False, "detail": "no log.host"}
    text = path.read_text(errors="replace")
    variable = re.search(r'Variable "[^"]+" compare failed', text) is not None
    assertion = "Assertion" in text
    netlen = "Net mgs length compare failed" in text
    logout = text.rstrip().endswith("logout")
    ok = logout and not variable and not assertion
    detail = ""
    if variable:
        match = re.search(r'Variable "([^"]+)" compare failed', text)
        detail = match.group(0) if match else "variable"
    elif assertion:
        detail = "Assertion"
    elif not logout:
        detail = "no logout"
    return {"ok": ok, "logout": logout, "variable_fail": variable or assertion,
            "netlen_warn": netlen, "detail": detail}


def collect_gcov(config):
    host_stage = MOUNT / "work" / "gcov-stage" / config
    run(["sudo", "rm", "-rf", str(host_stage)], timeout=60)
    host_stage.mkdir(parents=True)
    for node in ("n1", "n2", "n3"):
        dest = host_stage / node
        copied = run(
            ["sudo", "docker", "cp", "%s:/tmp/gcov-%s" % (node, node), str(dest)],
            timeout=120,
        )
        if copied.returncode != 0:
            raise RuntimeError("docker cp %s failed: %s" % (node, copied.stderr))
    script = r"""
set -e
stage=/root/sandtable/specula-ce/work/gcov-stage/%s
# docker cp of /tmp/gcov-nN creates stage/nN as that directory.
root_of() {
  if [ -d "$1/gcov-n${2}" ]; then echo "$1/gcov-n${2}"; else echo "$1"; fi
}
rm -rf /tmp/gcov-merge-a /tmp/gcov-merge-b
gcov-tool merge -o /tmp/gcov-merge-a "$(root_of "$stage/n1" 1)" "$(root_of "$stage/n2" 2)"
gcov-tool merge -o /tmp/gcov-merge-b /tmp/gcov-merge-a "$(root_of "$stage/n3" 3)"
find /root/sandtable/specula-ce/sandtable/driver/build -name '*.gcda' -delete
cd /tmp/gcov-merge-b
find . -name '*.gcda' -print0 | while IFS= read -r -d '' f; do
  dest="/${f#./}"
  mkdir -p "$(dirname "$dest")"
  cp "$f" "$dest"
done
out=/root/sandtable/specula-ce/work/gcov-stage/%s/gcov
rm -rf "$out"
mkdir -p "$out"
cd "$out"
find /root/sandtable/specula-ce/sandtable/driver/build -name 'raft_log.c.gcno' -o -name 'raft_server.c.gcno' -o -name 'raft_node.c.gcno' -o -name 'raft_server_properties.c.gcno' | \
  xargs gcov -b >/tmp/gcov-summary.txt
cp /tmp/gcov-summary.txt "$out/summary.txt"
""" % (config, config)
    result = run(["sudo", "docker", "exec", "controller", "bash", "-lc", script], timeout=180)
    if result.returncode != 0:
        raise RuntimeError("gcov failed: %s\n%s" % (result.stderr, result.stdout))
    gcov_dir = ROUND_DIR / config / "gcov"
    run(["sudo", "rm", "-rf", str(gcov_dir)], timeout=60)
    gcov_dir.mkdir(parents=True)
    src = host_stage / "gcov"
    for item in src.iterdir():
        if item.suffix == ".gcov" or item.name == "summary.txt":
            shutil.copy(item, gcov_dir / item.name)
    return gcov_dir


def parse_coverage(gcov_dir):
    files = {}
    called = {}
    for path in sorted(gcov_dir.glob("*.gcov")):
        text = path.read_text(errors="replace")
        source = path.name[:-5]
        header = re.search(r"^[^:]+:\s*0:Source:(.+)$", text, re.M)
        if header:
            source = os.path.basename(header.group(1).strip())
        executed = 0
        total = 0
        for line in text.splitlines():
            match = LINE_RE.match(line)
            if not match:
                continue
            total += 1
            if match.group(1) != "#####":
                executed += 1
        branches = 0
        taken = 0
        for line in text.splitlines():
            if not line.startswith("branch "):
                continue
            branches += 1
            if "taken" in line and "taken 0%" not in line:
                taken += 1
        files[source] = {
            "line_pct": (100.0 * executed / total) if total else 0.0,
            "branch_taken_pct": (100.0 * taken / branches) if branches else 0.0,
            "lines": total,
            "lines_hit": executed,
            "branches": branches,
            "branches_taken": taken,
        }
        for name, count in FUNC_RE.findall(text):
            called[name] = called.get(name, 0) + int(count)
    lines = sum(item["lines"] for item in files.values())
    hit = sum(item["lines_hit"] for item in files.values())
    branches = sum(item["branches"] for item in files.values())
    taken = sum(item["branches_taken"] for item in files.values())
    return {
        "line_pct": (100.0 * hit / lines) if lines else 0.0,
        "branch_taken_pct": (100.0 * taken / branches) if branches else 0.0,
        "files": files,
        "called": called,
    }


def load_coverage(config):
    path = ROUND_DIR / config / "coverage.json"
    if not path.is_file():
        return {"config": config, "traces": []}
    return json.loads(path.read_text())


def save_coverage(config, doc):
    traces = doc["traces"]
    pcts = [item["line_pct"] for item in traces]
    last_rise = 0
    for index, pct in enumerate(pcts, start=1):
        if index == 1 or pct > pcts[index - 2] + 1e-9:
            last_rise = index
    oks = [item for item in traces if item["ok"]]
    times = [item["replay_s"] for item in traces]
    doc["summary"] = {
        "traces": len(traces),
        "variable_ok": len(oks),
        "replay_s_sum": sum(times),
        "replay_s_avg": (sum(times) / len(times)) if times else 0,
        "replay_s_min": min(times) if times else 0,
        "replay_s_max": max(times) if times else 0,
        "line_pct": pcts[-1] if pcts else 0,
        "branch_taken_pct": traces[-1]["branch_taken_pct"] if traces else 0,
        "plateau_trace": last_rise,
        "plateaued": bool(pcts) and last_rise < len(pcts),
    }
    path = ROUND_DIR / config / "coverage.json"
    path.write_text(json.dumps(doc, indent=2) + "\n")


def replay(configs, seeds, fresh):
    for name, _cfg, _module, _depth in CONFIGS:
        if name not in configs:
            continue
        if fresh:
            clear_gcda()
            doc = {"config": name, "traces": []}
        else:
            doc = load_coverage(name)
            if not doc.get("traces"):
                clear_gcda()
        have = {item["trace"] for item in doc["traces"]}
        for seed in seeds:
            label = trace_name(seed)
            if label in have:
                continue
            print("replay %s %s" % (name, label), flush=True)
            elapsed, _code = replay_one(name, seed)
            verdict = judge(name, seed)
            cov = parse_coverage(collect_gcov(name))
            doc["traces"].append({
                "trace": label,
                "seed": seed,
                "replay_s": round(elapsed, 3),
                "ok": verdict["ok"],
                "logout": verdict["logout"],
                "variable_fail": verdict["variable_fail"],
                "netlen_warn": verdict["netlen_warn"],
                "detail": verdict["detail"],
                "line_pct": round(cov["line_pct"], 4),
                "branch_taken_pct": round(cov["branch_taken_pct"], 4),
                "files": {
                    fname: {
                        "line_pct": round(info["line_pct"], 4),
                        "branch_taken_pct": round(info["branch_taken_pct"], 4),
                        "lines": info["lines"],
                        "branches": info["branches"],
                    }
                    for fname, info in sorted(cov["files"].items())
                },
            })
            save_coverage(name, doc)
            print("  ok=%s line=%.2f branch=%.2f %.1fs %s" % (
                verdict["ok"], cov["line_pct"], cov["branch_taken_pct"], elapsed, verdict["detail"]),
                flush=True)
        save_coverage(name, doc)


def uncovered_lines(gcov_dir):
    rows = {}
    for path in gcov_dir.glob("*.gcov"):
        text = path.read_text(errors="replace")
        source = path.name[:-5]
        header = re.search(r"^[^:]+:\s*0:Source:(.+)$", text, re.M)
        if header:
            source = os.path.basename(header.group(1).strip())
        for line in text.splitlines():
            match = LINE_RE.match(line)
            if not match:
                continue
            number = int(match.group(2))
            key = (source, number)
            hit = match.group(1) != "#####"
            rows[key] = rows.get(key, False) or hit
    return rows


def write_uncovered(configs):
    merged = {}
    called = {}
    for name in configs:
        gcov_dir = ROUND_DIR / name / "gcov"
        if not gcov_dir.is_dir():
            continue
        for key, hit in uncovered_lines(gcov_dir).items():
            merged[key] = merged.get(key, False) or hit
        text = "\n".join(path.read_text(errors="replace") for path in gcov_dir.glob("*.gcov"))
        for func, count in FUNC_RE.findall(text):
            called[func] = called.get(func, 0) + int(count)
    lines = ["%s:%d" % (source, number) for (source, number), hit in sorted(merged.items()) if not hit]
    notes = []
    watched = {
        "raft_begin_snapshot": "TakeSnapshot",
        "raft_end_snapshot": "TakeSnapshot",
        "raft_begin_load_snapshot": "HandleInstallSnapshot",
        "raft_end_load_snapshot": "HandleInstallSnapshot",
    }
    for func, action in watched.items():
        if called.get(func, 0) == 0:
            notes.append("# called 0 %s" % func)
    path = ROUND_DIR / "uncovered.txt"
    path.write_text("\n".join(lines + notes) + "\n")
    print("uncovered %d" % len(lines), flush=True)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("sample", "replay", "uncovered", "all"), default="all")
    parser.add_argument("--configs", default=",".join(name for name, *_ in CONFIGS))
    parser.add_argument("--seed-from", type=int, default=1)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--jobs", type=int, default=16)
    parser.add_argument("--fresh", action="store_true")
    args = parser.parse_args()
    configs = [item for item in args.configs.split(",") if item]
    seeds = list(range(args.seed_from, args.seed_from + args.count))
    if args.phase in ("sample", "all"):
        sample(configs, seeds, args.jobs)
    if args.phase in ("replay", "all"):
        build_driver()
        replay(configs, seeds, args.fresh)
    if args.phase in ("uncovered", "all"):
        write_uncovered(configs)


if __name__ == "__main__":
    main()
