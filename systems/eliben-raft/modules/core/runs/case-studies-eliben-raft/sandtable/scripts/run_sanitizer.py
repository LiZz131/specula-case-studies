#!/usr/bin/env python3
"""Replay the same MC.out files with an ASan/UBSan C++ driver.

The Go library is not instrumented. Its counters are not written: GOCOVERDIR
is unset, and nothing here updates lcov.info or coverage.json.
A Sanitizer report or a missing logout is a crash. The first crash stops
the round so it can be read before continuing.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

RUN = Path("/users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft")
ROUND = RUN / "controlled-execution-runs" / "controlled-execution-1031-1"
MOUNT = Path("/users/bingzhuo/sandtable/build/mount/specula-ce")
CONTAINER = "/root/sandtable/specula-ce"
sys.path.append(str(RUN / "sandtable/scripts"))
from run_round import CONFIGS, judge, trace_dir, trace_name  # noqa: E402


def run(cmd, timeout=180):
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)


def replay_one(config, seed):
    src = trace_dir(config, seed) / "MC.out"
    host_work = MOUNT / "work-san" / config / trace_name(seed)
    run(["sudo", "rm", "-rf", str(host_work)])
    host_work.mkdir(parents=True)
    shutil.copy(src, host_work / "MC.out")
    container_mc = "%s/work-san/%s/%s/MC.out" % (CONTAINER, config, trace_name(seed))
    script = CONTAINER + "/sandtable/scripts/run_one_testcase.sh"
    starter = CONTAINER + "/sandtable/scripts/start_docker_sanitizer.sh"
    try:
        result = run(
            ["sudo", "docker", "exec", "-e", "SPECULA_START_DOCKER=" + starter,
             "controller", "bash", "-lc",
             "export SPECULA_START_DOCKER=%s; bash %s %s 3" % (starter, script, container_mc)],
            timeout=180,
        )
        code = result.returncode
        extra = ((result.stdout or "") + "\n" + (result.stderr or ""))[-2500:]
    except subprocess.TimeoutExpired:
        code = 124
        extra = "timeout"
    dest = ROUND / "sanitizer" / config / trace_name(seed)
    dest.mkdir(parents=True, exist_ok=True)
    found = list(host_work.rglob("log.host"))
    if found:
        subprocess.check_call(["sudo", "cp", str(found[0]), str(dest / "log.host")])
        subprocess.check_call(["sudo", "chown", "%d:%d" % (os.getuid(), os.getgid()), str(dest / "log.host")])
    (dest / "replay.status").write_text("exit %s\n%s\n" % (code, extra))
    run(["sudo", "rm", "-rf", str(host_work)])
    return code


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    for name, _cfg in CONFIGS:
        for seed in range(1, limit + 1):
            if not (trace_dir(name, seed) / "MC.out").is_file():
                continue
            print("san %s %s" % (name, trace_name(seed)), flush=True)
            code = replay_one(name, seed)
            # judge reads log.host from the coverage trace dir. Point it at the sanitizer copy.
            saved = trace_dir(name, seed) / "log.host"
            san_log = ROUND / "sanitizer" / config_log(name, seed)
            # judge() looks at trace_dir. Read the sanitizer log directly.
            text = san_log.read_text(errors="replace") if san_log.is_file() else ""
            bad = ("Sanitizer" in text) or ("stack smashing" in text) or ("logout" not in text) or code not in (0, None)
            print("  exit %s bad %s" % (code, bad), flush=True)
            if bad:
                print("SAN_FAIL %s %s" % (name, trace_name(seed)), flush=True)
                return
    print("SAN_DONE", flush=True)


def config_log(name, seed):
    return ROUND / "sanitizer" / name / trace_name(seed) / "log.host"


if __name__ == "__main__":
    main()
