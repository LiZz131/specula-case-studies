#!/usr/bin/env python3
"""Sample and replay controlled-execution-1031-1.

Coverage comes from go tool cover counters dumped at exit, not gcov.
Go has no branch coverage; branch_taken_pct stays null.
A passing replay whose model states contain two leaders in one term,
or a term that decreases, is recorded as a bug and the walk continues.
A variable mismatch or a crash stops the round.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

RUN = Path("/users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft")
ROUND = RUN / "controlled-execution-runs" / "controlled-execution-1031-1"
SPEC = RUN / "spec"
MOUNT = Path("/users/bingzhuo/sandtable/build/mount/specula-ce")
CONTAINER = "/root/sandtable/specula-ce"
JAR = "/users/bingzhuo/sandtable/scripts/tla2tools.jar"
sys.path.append("/users/bingzhuo/sandtable/scripts")
from trace_reader import TraceReader  # noqa: E402

CONFIGS = [
    ("standard", "MC_for_sandtable.cfg"),
    ("f1a", "MC_for_sandtable_f1a.cfg"),
    ("f1b", "MC_for_sandtable_f1b.cfg"),
    ("f1c", "MC_for_sandtable_f1c.cfg"),
    ("f2a", "MC_for_sandtable_f2a.cfg"),
    ("diverge", "MC_for_sandtable_diverge.cfg"),
]
SOURCE_FILES = ("raft.go", "server.go", "storage.go", "controlled.go")
ARTIFACT = RUN / "artifact/raft/part3/raft"


def run(cmd, timeout=180):
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)


def trace_name(seed):
    return "t%04d" % seed


def trace_dir(config, seed):
    return ROUND / config / "traces" / trace_name(seed)


def sample_one(config, cfg, seed):
    dest = trace_dir(config, seed)
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / "MC.out"
    if out.is_file() and "pc |->" in out.read_text(errors="replace"):
        return config, seed, "skip"
    meta = "/tmp/tlc-%s-%d" % (config, seed)
    shutil.rmtree(meta, ignore_errors=True)
    cmd = [
        "java", "-Xmx1g", "-jar", JAR, "-tool", "-workers", "1", "-simulate",
        "-depth", "50", "-seed", str(seed), "-metadir", meta,
        "-config", str(SPEC / cfg), "MC_for_sandtable",
    ]
    result = subprocess.run(cmd, cwd=SPEC, text=True, capture_output=True, timeout=180)
    shutil.rmtree(meta, ignore_errors=True)
    text = result.stdout
    if "pc |->" not in text:
        (dest / "tlc.err").write_text(result.stdout[-2000:] + "\n" + result.stderr[-2000:])
        raise RuntimeError("no pc in %s seed %d exit %d" % (config, seed, result.returncode))
    out.write_text(text)
    violated = re.findall(r"Invariant (\S+) is violated", text)
    (dest / "tlc.status").write_text("exit %d\n%s\n" % (result.returncode, "\n".join(violated)))
    return config, seed, "ok"


def sample(configs, seeds, jobs):
    tasks = []
    for name, cfg in CONFIGS:
        if name not in configs:
            continue
        for seed in seeds:
            tasks.append((name, cfg, seed))
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(sample_one, name, cfg, seed) for name, cfg, seed in tasks]
        for future in as_completed(futures):
            name, seed, status = future.result()
            print("sample %s %s %s" % (name, trace_name(seed), status), flush=True)


def sync_mount():
    MOUNT.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(["rsync", "-a", "--delete", str(RUN / "artifact") + "/", str(MOUNT / "artifact") + "/"])
    subprocess.check_call([
        "rsync", "-a", "--delete", "--exclude", "driver/build",
        str(RUN / "sandtable") + "/", str(MOUNT / "sandtable") + "/",
    ])
    so = RUN / "sandtable/driver/libeliben.so"
    subprocess.check_call(["sudo", "cp", "-f", str(so), str(MOUNT / "sandtable/driver/build/libeliben.so")])


def clear_cover():
    for node in ("n1", "n2", "n3"):
        run(["sudo", "docker", "exec", node, "rm", "-rf", "/tmp/gocov-%s" % node])


def replay_one(config, seed):
    src = trace_dir(config, seed) / "MC.out"
    host_work = MOUNT / "work" / config / trace_name(seed)
    run(["sudo", "rm", "-rf", str(host_work)])
    host_work.mkdir(parents=True)
    shutil.copy(src, host_work / "MC.out")
    container_mc = "%s/work/%s/%s/MC.out" % (CONTAINER, config, trace_name(seed))
    script = CONTAINER + "/sandtable/scripts/run_one_testcase.sh"
    started = time.monotonic()
    try:
        result = run(["sudo", "docker", "exec", "controller", "bash", script, container_mc, "3"], timeout=180)
        elapsed = time.monotonic() - started
        code = result.returncode
        extra = (result.stdout or "")[-1500:] + "\n" + (result.stderr or "")[-1500:]
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - started
        code = 124
        extra = "timeout"
    dest = trace_dir(config, seed)
    for name in ("traces.txt", "log.host"):
        found = list(host_work.rglob(name))
        if found:
            subprocess.check_call(["sudo", "cp", str(found[0]), str(dest / name)])
            subprocess.check_call(["sudo", "chown", "%d:%d" % (os.getuid(), os.getgid()), str(dest / name)])
    cover_dir = dest / "cover"
    if cover_dir.exists():
        shutil.rmtree(cover_dir)
    cover_dir.mkdir()
    for node in ("n1", "n2", "n3"):
        copied = run(["sudo", "docker", "cp", "%s:/tmp/gocov-%s" % (node, node), str(cover_dir / node)])
        if copied.returncode != 0:
            extra += "\ndocker cp %s failed" % node
    run(["sudo", "chmod", "-R", "a+rX", str(cover_dir)])
    (dest / "replay.status").write_text("exit %s\n%s\n" % (code, extra))
    run(["sudo", "rm", "-rf", str(host_work)])
    return elapsed, code


def judge(config, seed, exit_code):
    path = trace_dir(config, seed) / "log.host"
    if not path.is_file():
        return {"ok": False, "logout": False, "kind": "crash", "variable": "",
                "code_value": "", "model_value": "", "detail": "no log.host", "pc": ""}
    text = path.read_text(errors="replace")
    variable = re.search(r'Variable "([^"]+)" compare failed', text)
    logout = "logout" in text
    sanitizer = ("Sanitizer" in text) or ("stack smashing" in text)
    library_assert = ("Assertion" in text) and not variable
    code_value = model_value = ""
    pc = ""
    if variable:
        window = text[variable.start():variable.start() + 600]
        code_m = re.search(r"Code \(([^)]*)\): (.*)", window)
        model_m = re.search(r"Model\(([^)]*)\): (.*)", window)
        if code_m:
            code_value = code_m.group(0)
        if model_m:
            model_value = model_m.group(0)
        traces = trace_dir(config, seed) / "traces.txt"
        if traces.is_file():
            comments = [line[2:] for line in traces.read_text(errors="replace").splitlines() if line.startswith("# [")]
            step = re.search(r"# \[(\d+)\]", text[max(0, variable.start() - 500):variable.start()])
            if step and comments:
                index = int(step.group(1))
                if index < len(comments):
                    pc = comments[index]
    if variable:
        kind, ok, detail = "variable", False, variable.group(0)
    elif sanitizer or library_assert or exit_code not in (0, None) or not logout:
        kind, ok = "crash", False
        detail = "sanitizer" if sanitizer else ("assert" if library_assert else "exit %s" % exit_code)
    else:
        kind, ok, detail = "pass", True, ""
    return {
        "ok": ok, "logout": logout, "kind": kind, "variable": variable.group(1) if variable else "",
        "code_value": code_value, "model_value": model_value, "detail": detail, "pc": pc,
    }


def deviations(mc_path):
    reader = TraceReader(True)
    found = set()
    previous = {}
    try:
        states = list(reader.trace_reader(str(mc_path)))
    except Exception as exc:
        return ["scan-error:%s" % exc]
    for state in states:
        leaders = {}
        for server, role in state["state"].items():
            term = int(state["currentTerm"][server])
            if server in previous and term < previous[server]:
                found.add("f2a-term-regression")
            previous[server] = term
            if role == "Leader":
                leaders.setdefault(term, []).append(server)
        if any(len(servers) > 1 for servers in leaders.values()):
            found.add("election-safety")
    return sorted(found)


def append_failure(config, seed, exit_code, verdict, klass):
    path = ROUND / "failures.tsv"
    if not path.is_file():
        path.write_text("配置\t轨迹\t种子\t归类\t退出码\tlogout\t变量\t代码值\t模型值\tpc\t记录目录\n")
    row = "\t".join([
        config, trace_name(seed), str(seed), klass, str(exit_code),
        "yes" if verdict["logout"] else "no",
        verdict["variable"], verdict["code_value"].replace("\t", " ").replace("\n", " "),
        verdict["model_value"].replace("\t", " ").replace("\n", " "), verdict["pc"],
        str(trace_dir(config, seed).relative_to(RUN)),
    ])
    with path.open("a") as handle:
        handle.write(row + "\n")


def copy_bug(config, seed, kind):
    dest = ROUND / "potential-bugs" / kind / trace_name(seed)
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("MC.out", "traces.txt", "log.host"):
        src = trace_dir(config, seed) / name
        if src.is_file():
            shutil.copy(src, dest / name)
    note = dest / "where.txt"
    note.write_text("%s %s\n" % (config, trace_name(seed)))


def parse_cover_dir(path):
    """Sum block counts from every node's tsv."""
    blocks = {}
    if not path.is_dir():
        return blocks
    for tsv in path.rglob("cover.*.tsv"):
        for line in tsv.read_text(errors="replace").splitlines():
            file, start, end, stmts, count = line.split("\t")
            key = (file, int(start), int(end), int(stmts))
            blocks[key] = blocks.get(key, 0) + int(count)
    return blocks


def merge_blocks(accum, extra):
    for key, count in extra.items():
        accum[key] = accum.get(key, 0) + count


def line_map(blocks):
    lines = {}
    for (file, start, end, _stmts), count in blocks.items():
        source = Path(file).name
        for number in range(start, end + 1):
            key = (source, number)
            lines[key] = max(lines.get(key, 0), count)
    return lines


def line_pct(blocks):
    lines = line_map(blocks)
    if not lines:
        return 0.0
    hit = sum(1 for count in lines.values() if count > 0)
    return 100.0 * hit / len(lines)


def write_gcov(config, blocks):
    gcov_dir = ROUND / config / "gcov"
    if gcov_dir.exists():
        shutil.rmtree(gcov_dir)
    gcov_dir.mkdir(parents=True)
    lines = line_map(blocks)
    by_file = {}
    for (source, number), count in lines.items():
        by_file.setdefault(source, {})[number] = count
    for source, rows in by_file.items():
        text = ["        -:    0:Source:%s" % (ARTIFACT / source)]
        for number in sorted(rows):
            count = rows[number]
            mark = "#####" if count == 0 else "%8d" % count
            text.append("%s:%5d:" % (mark, number))
        (gcov_dir / (source + ".gcov")).write_text("\n".join(text) + "\n")
    summary = "lines %.4f\n" % line_pct(blocks)
    (gcov_dir / "summary.txt").write_text(summary)


def load_coverage(config):
    path = ROUND / config / "coverage.json"
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
    doc["summary"] = {
        "traces": len(traces),
        "variable_ok": sum(1 for item in traces if item["ok"]),
        "line_pct": pcts[-1] if pcts else 0,
        "branch_taken_pct": None,
        "branch_note": "Go cover has no branch counters",
        "plateau_trace": last_rise,
        "plateaued": bool(pcts) and last_rise < len(pcts),
    }
    (ROUND / config / "coverage.json").write_text(json.dumps(doc, indent=2) + "\n")


def replay(configs, seeds):
    stopped = False
    for name, _cfg in CONFIGS:
        if name not in configs or stopped:
            continue
        clear_cover()
        doc = load_coverage(name)
        have = {item["trace"] for item in doc["traces"]}
        accum = {}
        # Rebuild the accumulator from traces already judged, in seed order.
        for item in doc["traces"]:
            merge_blocks(accum, parse_cover_dir(ROUND / name / "traces" / item["trace"] / "cover"))
        for seed in seeds:
            label = trace_name(seed)
            if label in have:
                continue
            print("replay %s %s" % (name, label), flush=True)
            clear_cover()
            elapsed, code = replay_one(name, seed)
            verdict = judge(name, seed, code)
            fresh = parse_cover_dir(trace_dir(name, seed) / "cover")
            merge_blocks(accum, fresh)
            bugs = []
            if verdict["ok"]:
                bugs = deviations(trace_dir(name, seed) / "MC.out")
                for kind in bugs:
                    if kind.startswith("scan-error"):
                        print("FAIL %s %s scan %s" % (name, label, kind), flush=True)
                        stopped = True
                        break
                    copy_bug(name, seed, kind)
                    append_failure(name, seed, code, verdict, "bug")
                    print("BUG %s %s %s" % (name, label, kind), flush=True)
            doc["traces"].append({
                "trace": label,
                "seed": seed,
                "replay_s": round(elapsed, 3),
                "ok": verdict["ok"],
                "logout": verdict["logout"],
                "kind": "bug" if bugs and verdict["ok"] else verdict["kind"],
                "bugs": bugs,
                "detail": verdict["detail"],
                "line_pct": round(line_pct(accum), 4),
                "branch_taken_pct": None,
            })
            save_coverage(name, doc)
            write_gcov(name, accum)
            print("  ok=%s bugs=%s line=%.2f %.1fs %s" % (
                verdict["ok"], ",".join(bugs), line_pct(accum), elapsed, verdict["detail"]), flush=True)
            if stopped:
                break
            if not verdict["ok"]:
                append_failure(name, seed, code, verdict, "crash" if verdict["kind"] == "crash" else "adapter")
                print("FAIL %s %s %s %s" % (name, label, verdict["kind"], verdict["detail"]), flush=True)
                stopped = True
                break
        save_coverage(name, doc)
        write_gcov(name, accum)
    return stopped


def write_union(configs):
    merged = {}
    for name in configs:
        for key, count in parse_blocks_from_gcov(name).items():
            merged[key] = max(merged.get(key, 0), count)
    records = []
    for source in SOURCE_FILES:
        rows = [(number, count) for (src, number), count in sorted(merged.items()) if src == source]
        if not rows:
            continue
        body = ["SF:%s" % (ARTIFACT / source)]
        for number, count in rows:
            body.append("DA:%d,%d" % (number, count))
        body.append("end_of_record")
        records.append("\n".join(body))
    (ROUND / "lcov.info").write_text("\n".join(records) + "\n")
    uncovered = ["%s:%d" % (source, number) for (source, number), count in sorted(merged.items()) if count == 0]
    (ROUND / "uncovered.txt").write_text("\n".join(uncovered) + ("\n" if uncovered else ""))
    hit = sum(1 for count in merged.values() if count > 0)
    print("union lines %d hit %d uncovered %d" % (len(merged), hit, len(uncovered)), flush=True)


def parse_blocks_from_gcov(config):
    """Recover line counts from the gcov text written for this config."""
    lines = {}
    gcov_dir = ROUND / config / "gcov"
    if not gcov_dir.is_dir():
        return lines
    for path in gcov_dir.glob("*.gcov"):
        source = path.name[:-5]
        for line in path.read_text(errors="replace").splitlines():
            match = re.match(r"\s*(#####|\d+):\s*(\d+):", line)
            if not match or match.group(2) == "0":
                continue
            count = 0 if match.group(1) == "#####" else int(match.group(1))
            lines[(source, int(match.group(2)))] = count
    return lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("sample", "replay", "uncovered", "all"), default="all")
    parser.add_argument("--configs", default=",".join(name for name, _ in CONFIGS))
    parser.add_argument("--seed-from", type=int, default=1)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--jobs", type=int, default=8)
    args = parser.parse_args()
    configs = [item for item in args.configs.split(",") if item]
    seeds = list(range(args.seed_from, args.seed_from + args.count))
    ROUND.mkdir(parents=True, exist_ok=True)
    if args.phase in ("sample", "all"):
        sample(configs, seeds, args.jobs)
    if args.phase in ("replay", "all"):
        subprocess.check_call(["bash", str(RUN / "sandtable/scripts/build_lib.sh")])
        sync_mount()
        stopped = replay(configs, seeds)
        if stopped:
            print("REPLAY_STOPPED", flush=True)
            return
    if args.phase in ("uncovered", "all"):
        write_union([name for name, _ in CONFIGS if name in configs])
    print("ROUND_DONE", flush=True)


if __name__ == "__main__":
    main()
