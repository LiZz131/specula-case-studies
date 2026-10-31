#!/usr/bin/env python3
"""Replay the coverage round's MC.out under AddressSanitizer and UBSan.

Does not resample. Does not write gcda into the coverage round's lcov.info.
ASAN_OPTIONS=detect_leaks=0. A sanitizer report is crash even when the
process exits 0.
"""

import re
import shutil
import subprocess
import time
from pathlib import Path

RUN = Path("/users/bingzhuo/Specula/case-studies/systems/redisraft/modules/core/runs/case-studies-redisraft")
MOUNT = Path("/users/bingzhuo/sandtable/build/mount/specula-ce")
CONTAINER_ROOT = "/root/sandtable/specula-ce"
COVERAGE = RUN / "controlled-execution-runs" / "controlled-execution-1030-1"
ROUND = "controlled-execution-1030-1-sanitizer"
ROUND_DIR = RUN / "controlled-execution-runs" / ROUND
CONFIGS = ["standard", "crashrecovery", "membership", "snapshot", "staleread"]
START = CONTAINER_ROOT + "/sandtable/scripts/start_docker_sanitizer.sh"


def run(cmd, timeout=None):
    return subprocess.run(
        cmd, timeout=timeout, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def sync_and_build():
    MOUNT.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["rsync", "-a", str(RUN / "artifact") + "/", str(MOUNT / "artifact") + "/"],
        check=True,
    )
    subprocess.run(
        ["rsync", "-a", "--exclude", "driver/build", "--exclude", "driver/build-san",
         str(RUN / "sandtable") + "/", str(MOUNT / "sandtable") + "/"],
        check=True,
    )
    for script in (MOUNT / "sandtable" / "scripts").glob("*.sh"):
        script.chmod(0o755)
    cmd = (
        "set -e; cd /root/sandtable/specula-ce/sandtable/driver; "
        "cmake -S . -B build-san -DSPECULA_SANITIZE=ON >/tmp/specula-san-cmake.log; "
        "cmake --build build-san -j$(nproc) >>/tmp/specula-san-cmake.log; "
        "gcc -print-file-name=libasan.so"
    )
    result = run(["sudo", "docker", "exec", "controller", "bash", "-lc", cmd], timeout=240)
    print(result.stdout)
    if result.returncode != 0:
        log = run(["sudo", "docker", "exec", "controller", "bash", "-lc",
                   "tail -60 /tmp/specula-san-cmake.log"])
        raise SystemExit("sanitizer build failed\n" + result.stderr + "\n" + log.stdout)
    binary = MOUNT / "sandtable" / "driver" / "build-san" / "RedisRaftDriver"
    if not binary.is_file():
        raise SystemExit("sanitizer binary missing")
    data = binary.read_bytes()
    if b"AddressSanitizer" not in data and b"libasan" not in data:
        raise SystemExit("build-san binary has no ASan runtime")


def replay_one(config, label, mc_out):
    host_work = MOUNT / "work-san" / config / label
    run(["sudo", "rm", "-rf", str(host_work)], timeout=60)
    host_work.mkdir(parents=True)
    shutil.copy(mc_out, host_work / "MC.out")
    container_mc = "%s/work-san/%s/%s/MC.out" % (CONTAINER_ROOT, config, label)
    script = CONTAINER_ROOT + "/sandtable/scripts/run_one_testcase.sh"
    started = time.monotonic()
    try:
        result = run(
            ["sudo", "docker", "exec", "-e", "SPECULA_START_DOCKER=" + START,
             "controller", "bash", script, container_mc, "3"],
            timeout=180,
        )
        code = result.returncode
        extra = (result.stdout or "")[-2000:] + "\n" + (result.stderr or "")[-2000:]
    except subprocess.TimeoutExpired as exc:
        code = 124
        extra = "timeout\n" + str(exc)[-1000:]
    elapsed = time.monotonic() - started
    dest = ROUND_DIR / config / "traces" / label
    dest.mkdir(parents=True, exist_ok=True)
    test = host_work / "test"
    blobs = []
    if test.is_dir():
        for name in ("log.host", "log.1", "log.2", "log.3", "traces.txt"):
            src = test / name
            if src.is_file():
                shutil.copy(src, dest / name)
                blobs.append(src.read_text(errors="replace"))
    (dest / "replay.status").write_text("exit %s\n%s\n" % (code, extra))
    blobs.append(extra)
    run(["sudo", "rm", "-rf", str(host_work)], timeout=60)
    return elapsed, code, "\n".join(blobs)


def judge(text, code):
    sanitizer = bool(re.search(
        r"AddressSanitizer|UndefinedBehaviorSanitizer|runtime error:|stack smashing|SUMMARY: .*Sanitizer",
        text,
    ))
    variable = re.search(r'Variable "([^"]+)" compare failed', text)
    logout = "logout" in text
    if sanitizer:
        kind = "crash"
        detail = "sanitizer"
        ok = False
    elif variable:
        kind = "variable"
        detail = variable.group(0)
        ok = False
    elif code not in (0, None) or not logout:
        kind = "crash"
        detail = "exit %s" % code if code else "no logout"
        ok = False
    else:
        kind = "pass"
        detail = ""
        ok = True
    return ok, kind, detail, variable.group(1) if variable else ""


def append_failure(config, label, code, kind, detail, variable):
    path = ROUND_DIR / "failures.tsv"
    if not path.is_file():
        path.write_text("配置\t轨迹\t种子\t归类\t退出码\tlogout\t变量\t代码值\t模型值\tpc\t记录目录\n")
    seed = str(int(label[1:]))
    row = "\t".join([
        config, label, seed, "crash" if kind == "crash" else "unclassified",
        str(code), "", variable, detail.replace("\t", " "), "", "",
        str((ROUND_DIR / config / "traces" / label).relative_to(RUN)),
    ])
    with path.open("a") as handle:
        handle.write(row + "\n")


def main():
    ROUND_DIR.mkdir(parents=True, exist_ok=True)
    sync_and_build()
    for config in CONFIGS:
        traces = sorted((COVERAGE / config / "traces").glob("t*/MC.out"))
        for mc_out in traces:
            label = mc_out.parent.name
            dest_status = ROUND_DIR / config / "traces" / label / "replay.status"
            if dest_status.is_file():
                continue
            print("san %s %s" % (config, label), flush=True)
            elapsed, code, text = replay_one(config, label, mc_out)
            ok, kind, detail, variable = judge(text, code)
            print("  ok=%s %s %.1fs %s" % (ok, kind, elapsed, detail), flush=True)
            if not ok:
                append_failure(config, label, code, kind, detail, variable)
                print("FAIL %s %s %s %s" % (config, label, kind, detail), flush=True)
                print("SAN_STOPPED", flush=True)
                return
    print("SAN_DONE", flush=True)


if __name__ == "__main__":
    main()
