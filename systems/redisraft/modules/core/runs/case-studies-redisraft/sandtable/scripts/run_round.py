#!/usr/bin/env python3
"""Sample and replay one RedisRaft SandTable controlled-execution round.

Outputs stay under the Specula run. The mount is only a working copy.
The SandTable git tree is not modified.
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

RUN = Path("/users/bingzhuo/Specula/case-studies/systems/redisraft/modules/core/runs/case-studies-redisraft")
MOUNT = Path("/users/bingzhuo/sandtable/build/mount/specula-ce")
CONTAINER_ROOT = "/root/sandtable/specula-ce"
JAR = Path("/users/bingzhuo/sandtable/scripts/tla2tools.jar")
SPEC = RUN / "spec"
ROUND = "controlled-execution-1102-1"
ROUND_DIR = RUN / "controlled-execution-runs" / ROUND
ARTIFACT_SRC = (RUN / "artifact" / "redisraft" / "src").resolve()

CONFIGS = [
    ("standard", "MC_for_sandtable.cfg", "MC_for_sandtable", 50),
    ("crashrecovery", "MC_for_sandtable_crashrecovery.cfg", "MC_for_sandtable", 50),
    ("membership", "MC_for_sandtable_membership.cfg", "MC_for_sandtable", 50),
    ("snapshot", "MC_for_sandtable_snapshot.cfg", "MC_for_sandtable", 50),
    ("staleread", "MC_for_sandtable_staleread.cfg", "MC_for_sandtable", 50),
]

LINE_RE = re.compile(r"^\s*(#####|\d+\*?):\s*(\d+):")
FUNC_RE = re.compile(r"^function\s+(\S+)\s+called\s+(\d+)", re.M)
SOURCE_FILES = (
    "raft_log.c",
    "raft_server.c",
    "raft_node.c",
    "raft_server_properties.c",
)


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
        ["rsync", "-a", "--delete", str(RUN / "artifact") + "/", str(MOUNT / "artifact") + "/"],
        check=True,
    )
    subprocess.run(
        ["rsync", "-a", "--delete", "--exclude", "driver/build",
         str(RUN / "sandtable") + "/", str(MOUNT / "sandtable") + "/"],
        check=True,
    )
    for script in (MOUNT / "sandtable" / "scripts").glob("*.sh"):
        script.chmod(0o755)


def build_driver():
    sync_working_copy()
    cmd = (
        "set -e; cd /root/sandtable/specula-ce/sandtable/driver; "
        "rm -rf build; "
        "cmake -S . -B build >/tmp/specula-ce-cmake.log; "
        "cmake --build build -j$(nproc) >>/tmp/specula-ce-cmake.log"
    )
    result = run(["sudo", "docker", "exec", "controller", "bash", "-lc", cmd], timeout=180)
    if result.returncode != 0:
        log = run(["sudo", "docker", "exec", "controller", "bash", "-lc",
                   "tail -80 /tmp/specula-ce-cmake.log"])
        raise SystemExit("driver build failed\n" + result.stderr + "\n" + log.stdout)
    binary = MOUNT / "sandtable" / "driver" / "build" / "RedisRaftDriver"
    if not binary.is_file():
        raise SystemExit("RedisRaftDriver missing after build")


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
        "java", "-Xmx1g", "-jar", str(JAR),
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
    if "pc |->" not in text:
        return config, seed, "no-pc"
    if "Invariant DepthBound is violated" in text:
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
    try:
        result = run(
            ["sudo", "docker", "exec", "controller", "bash", script, container_mc, "3"],
            timeout=180,
        )
        elapsed = time.monotonic() - started
        code = result.returncode
        extra = result.stdout[-2000:] + "\n" + result.stderr[-2000:]
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        code = 124
        extra = "timeout\n" + (exc.stdout or "")[-1000:]
        result = None
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
    (dest / "replay.status").write_text("exit %s\n%s\n" % (code, extra))
    run(["sudo", "rm", "-rf", str(host_work)], timeout=60)
    return elapsed, code


def judge(config, seed, exit_code):
    path = trace_dir(config, seed) / "log.host"
    if not path.is_file():
        return {
            "ok": False, "logout": False, "kind": "crash",
            "variable": "", "code_value": "", "model_value": "",
            "detail": "no log.host", "netlen_warn": False, "pc": "",
        }
    text = path.read_text(errors="replace")
    variable = re.search(r'Variable "([^"]+)" compare failed', text)
    netlen = "Net mgs length compare failed" in text
    logout = "logout" in text
    sanitizer = ("Sanitizer" in text) or ("stack smashing" in text)
    library_assert = ("Assertion" in text) and not variable
    pc_match = re.findall(r"^# \[(\d+)\] .+$", text, re.M)
    last_pc = ""
    traces = trace_dir(config, seed) / "traces.txt"
    if traces.is_file() and variable:
        comments = [line[2:] for line in traces.read_text(errors="replace").splitlines() if line.startswith("# [")]
        step = re.search(r"# \[(\d+)\]", text[max(0, variable.start() - 400):variable.start()])
        if step and comments:
            index = int(step.group(1))
            if index < len(comments):
                last_pc = comments[index]
    code_value = ""
    model_value = ""
    if variable:
        window = text[variable.start():variable.start() + 800]
        code_m = re.search(r"Code \(([^)]+)\): (.*)", window)
        model_m = re.search(r"Model\(([^)]+)\): (.*)", window)
        if code_m:
            code_value = code_m.group(0)
        if model_m:
            model_value = model_m.group(0)
    if variable:
        kind = "variable"
        ok = False
        detail = variable.group(0)
    elif sanitizer or library_assert or exit_code not in (0, None) or not logout:
        kind = "crash"
        ok = False
        detail = "sanitizer" if sanitizer else ("assert" if library_assert else ("exit %s" % exit_code if exit_code else "no logout"))
    else:
        kind = "pass"
        ok = True
        detail = "net-len" if netlen else ""
    return {
        "ok": ok, "logout": logout, "kind": kind, "variable": variable.group(1) if variable else "",
        "code_value": code_value, "model_value": model_value, "detail": detail,
        "netlen_warn": netlen, "pc": last_pc,
    }


def append_failure(config, seed, exit_code, verdict):
    path = ROUND_DIR / "failures.tsv"
    if not path.is_file():
        path.write_text("配置\t轨迹\t种子\t归类\t退出码\tlogout\t变量\t代码值\t模型值\tpc\t记录目录\n")
    # variable mismatches stay unclassified until a person separates adapter from bug.
    klass = "crash" if verdict["kind"] == "crash" else "unclassified"
    row = "\t".join([
        config, trace_name(seed), str(seed), klass, str(exit_code),
        "yes" if verdict["logout"] else "no",
        verdict["variable"], verdict["code_value"].replace("\t", " "),
        verdict["model_value"].replace("\t", " "), verdict["pc"],
        str(trace_dir(config, seed).relative_to(RUN)),
    ])
    with path.open("a") as handle:
        handle.write(row + "\n")


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
    names = " -o ".join("-name '%s.gcno'" % name for name in SOURCE_FILES)
    script = """
set -e
stage=/root/sandtable/specula-ce/work/gcov-stage/CONFIG
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
out=/root/sandtable/specula-ce/work/gcov-stage/CONFIG/gcov
rm -rf "$out"
mkdir -p "$out"
cd "$out"
find /root/sandtable/specula-ce/sandtable/driver/build -path '*RedisRaft.dir*' \\( NAMES \\) | xargs gcov -b >/tmp/gcov-summary.txt
cp /tmp/gcov-summary.txt "$out/summary.txt"
""".replace("CONFIG", config).replace("NAMES", names)
    result = run(["sudo", "docker", "exec", "controller", "bash", "-lc", script], timeout=180)
    if result.returncode != 0:
        raise RuntimeError("gcov failed: %s\n%s" % (result.stderr, result.stdout))
    gcov_dir = ROUND_DIR / config / "gcov"
    if gcov_dir.exists():
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
        if source not in SOURCE_FILES and not source.endswith(".c"):
            continue
        if source not in SOURCE_FILES:
            continue
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
    stopped = False
    for name, _cfg, _module, _depth in CONFIGS:
        if name not in configs or stopped:
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
            elapsed, code = replay_one(name, seed)
            verdict = judge(name, seed, code)
            cov = parse_coverage(collect_gcov(name))
            doc["traces"].append({
                "trace": label,
                "seed": seed,
                "replay_s": round(elapsed, 3),
                "ok": verdict["ok"],
                "logout": verdict["logout"],
                "kind": verdict["kind"],
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
            if not verdict["ok"]:
                append_failure(name, seed, code, verdict)
                print("FAIL %s %s %s %s" % (name, label, verdict["kind"], verdict["detail"]), flush=True)
                stopped = True
                break
        save_coverage(name, doc)
    return stopped


def line_counts(gcov_dir):
    rows = {}
    for path in gcov_dir.glob("*.gcov"):
        text = path.read_text(errors="replace")
        source = path.name[:-5]
        header = re.search(r"^[^:]+:\s*0:Source:(.+)$", text, re.M)
        if header:
            source = os.path.basename(header.group(1).strip())
        if source not in SOURCE_FILES:
            continue
        for line in text.splitlines():
            match = LINE_RE.match(line)
            if not match:
                continue
            number = int(match.group(2))
            raw = match.group(1)
            count = 0 if raw == "#####" else int(raw.rstrip("*"))
            key = (source, number)
            rows[key] = max(rows.get(key, 0), count)
    return rows


def write_union(configs):
    merged = {}
    called = {}
    for name in configs:
        gcov_dir = ROUND_DIR / name / "gcov"
        if not gcov_dir.is_dir():
            continue
        for key, count in line_counts(gcov_dir).items():
            merged[key] = max(merged.get(key, 0), count)
        text = "\n".join(path.read_text(errors="replace") for path in gcov_dir.glob("*.gcov"))
        for func, count in FUNC_RE.findall(text):
            called[func] = called.get(func, 0) + int(count)
    records = []
    for source in SOURCE_FILES:
        path = ARTIFACT_SRC / source
        lines = [(number, count) for (src, number), count in sorted(merged.items()) if src == source]
        if not lines:
            continue
        body = ["SF:%s" % path]
        for number, count in lines:
            body.append("DA:%d,%d" % (number, count))
        body.append("end_of_record")
        records.append("\n".join(body))
    lcov = ROUND_DIR / "lcov.info"
    lcov.write_text("\n".join(records) + "\n")
    uncovered = ["%s:%d" % (source, number) for (source, number), count in sorted(merged.items()) if count == 0]
    watched = (
        "raft_become_leader",
        "raft_become_candidate",
        "raft_recv_entry",
        "raft_begin_snapshot",
        "raft_end_snapshot",
        "raft_recv_snapshot",
    )
    notes = ["# called 0 %s" % func for func in watched if called.get(func, 0) == 0]
    (ROUND_DIR / "uncovered.txt").write_text("\n".join(uncovered + notes) + ("\n" if uncovered or notes else ""))
    hit = sum(1 for count in merged.values() if count > 0)
    print("union lines %d hit %d uncovered %d" % (len(merged), hit, len(uncovered)), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("sample", "replay", "uncovered", "all"), default="all")
    parser.add_argument("--configs", default=",".join(name for name, *_ in CONFIGS))
    parser.add_argument("--seed-from", type=int, default=1)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--fresh", action="store_true")
    args = parser.parse_args()
    configs = [item for item in args.configs.split(",") if item]
    seeds = list(range(args.seed_from, args.seed_from + args.count))
    ROUND_DIR.mkdir(parents=True, exist_ok=True)
    if args.phase in ("sample", "all"):
        sample(configs, seeds, args.jobs)
    if args.phase in ("replay", "all"):
        build_driver()
        stopped = replay(configs, seeds, args.fresh)
        if stopped:
            print("REPLAY_STOPPED", flush=True)
            return
    if args.phase in ("uncovered", "all"):
        write_union(configs)
    print("ROUND_DONE", flush=True)


if __name__ == "__main__":
    main()
