#!/usr/bin/env python3
"""Turn a RedisRaft TLC trace with scr.pc into SandTable controller commands.

States without scr.pc are refused. The legacy state-diff path is for traces
that predate scr; this run always samples MC_for_sandtable, which records pc.
"""

import argparse
import os
import shutil
import sys


def set_path():
    candidates = []
    env = os.environ.get("SANDTABLE_SCRIPTS")
    if env:
        candidates.append(env)
    name = os.path.dirname(os.path.realpath(__file__))
    for _ in range(8):
        candidates.append(os.path.join(name, "scripts"))
        name = os.path.dirname(name)
    candidates.append("/root/sandtable/scripts")
    candidates.append("/users/bingzhuo/sandtable/scripts")
    for path in candidates:
        if os.path.isfile(os.path.join(path, "trace_reader.py")):
            sys.path.append(path)
            return
    raise SystemExit("trace_reader.py not found")


set_path()
from trace_reader import TraceReader  # noqa: E402


class NotControllable(Exception):
    pass


# raft.h: RAFT_STATE_FOLLOWER=1, CANDIDATE=3, LEADER=4. PreCandidate is 2
# and is not a modeled state.
STATE_CODE = {"Follower": "1", "Candidate": "3", "Leader": "4"}
ELECTION_TIMEOUT_MS = 2000
REQUEST_TIMEOUT_MS = 200


def node_name(server):
    text = str(server)
    if text.startswith("s") and text[1:].isdigit():
        return "n" + text[1:]
    raise NotControllable("cannot map server %s" % server)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("trace_file")
    parser.add_argument("-c", dest="config", required=True)
    parser.add_argument("-o", dest="output", default="traces.txt")
    parser.add_argument("-i", dest="in_place", action="store_true")
    parser.add_argument("-I", dest="in_dir", default="")
    parser.add_argument("-f", dest="conn_fd", default="126")
    parser.add_argument("-n", dest="node_port", default="9000")
    parser.add_argument("-d", dest="debug", action="store_true")
    args = parser.parse_args()
    if not args.in_place:
        args.trace_file = os.path.realpath(args.trace_file)
        args.config = os.path.realpath(args.config)
        if args.in_dir:
            directory = os.path.join(os.path.dirname(args.trace_file), args.in_dir)
            os.makedirs(directory, mode=0o755, exist_ok=True)
        else:
            directory = os.path.dirname(args.trace_file)
        os.chdir(directory)
        case_dir = os.path.basename(args.trace_file) + ".dir"
        os.makedirs(case_dir, mode=0o755, exist_ok=True)
        os.chdir(case_dir)
    return args


def copy_config(config_file, in_parent):
    try:
        if in_parent:
            os.symlink(os.path.dirname(config_file), "config")
        else:
            shutil.copy2(config_file, os.path.basename(config_file))
    except OSError:
        pass


def parse_record(reader, key):
    if not isinstance(key, str):
        return key
    text = key.replace("<<", "<").replace(">>", "$")
    return reader._variable_converter(text)


def bag_messages(reader, state):
    messages = state.get("messages")
    if not isinstance(messages, dict):
        return []
    items = []
    for key, count in messages.items():
        message = parse_record(reader, key)
        items.extend([message] * int(count))
    return items


def fmt_entry(entry):
    kind = entry.get("type")
    term = entry.get("term")
    if kind == "NoopEntry":
        body = "Nil"
    elif kind == "ValueEntry":
        body = "v"
    else:
        body = "?UNKNOWN?"
    return "(%s, '%s')" % (term, body)


def fmt_log(entries):
    if not entries:
        return "[]"
    return "[" + ", ".join(fmt_entry(entry) for entry in entries) + "]"


def fmt_index_map(mapping, self_name):
    items = []
    for key, value in sorted(mapping.items(), key=lambda kv: node_name(kv[0])):
        if node_name(key) == self_name:
            continue
        items.append("'%s': %s" % (node_name(key), value))
    return "{" + ", ".join(items) + "}"


class Builder:
    def __init__(self, reader, states):
        self.reader = reader
        self.states = states
        self.servers = sorted(states[0]["state"].keys(), key=node_name)
        self.lines = []

    def emit(self, *words):
        self.lines.append(" ".join(str(word) for word in words))

    def comment(self, text):
        self.lines.append("# " + text)

    def compare_node(self, state, server):
        name = node_name(server)
        self.emit("execute", name, "get commitIdx")
        self.comment("variable commitIdx %s %s" % (name, state["commitIndex"][server]))
        self.emit("compare", "variable")
        self.emit("execute", name, "get currentTerm")
        self.comment("variable currentTerm %s %s" % (name, state["currentTerm"][server]))
        self.emit("compare", "variable")
        self.emit("execute", name, "get log")
        self.comment("variable log %s %s" % (name, fmt_log(state["log"][server])))
        self.emit("compare", "variable")
        self.emit("execute", name, "get state")
        role = state["state"][server]
        if role not in STATE_CODE:
            raise NotControllable("unmapped state %s" % role)
        self.comment("variable state %s %s" % (name, STATE_CODE[role]))
        self.emit("compare", "variable")
        if role == "Leader":
            self.emit("execute", name, "get nextIdx")
            self.comment("variable nextIdx %s %s" % (name, fmt_index_map(state["nextIndex"][server], name)))
            self.emit("compare", "variable")
            self.emit("execute", name, "get matchIdx")
            self.comment("variable matchIdx %s %s" % (name, fmt_index_map(state["matchIndex"][server], name)))
            self.emit("compare", "variable")

    def compare_all(self, state):
        for server in self.servers:
            self.compare_node(state, server)
        self.comment("net-len %d" % len(bag_messages(self.reader, state)))
        self.emit("compare", "net-len")


def build_from_pc(reader, states):
    builder = Builder(reader, states)
    for index, state in enumerate(states):
        scr = state.get("scr") or {}
        pc = scr.get("pc")
        if not isinstance(pc, list) or not pc:
            raise NotControllable("state %d has no scr.pc" % index)
        cmd = pc[0]
        builder.comment("[%d] %s" % (index, " ".join(str(part) for part in pc)))
        if cmd == "Init":
            builder.emit("init", len(builder.servers))
            for server in builder.servers:
                name = node_name(server)
                builder.emit("execute", name, "net connectall")
                builder.emit("execute", name, "raft init")
            builder.emit("wait-init", len(builder.servers))
            for server in builder.servers:
                builder.emit("loop", "execute", node_name(server), "net isallconnected")
            for server in builder.servers:
                builder.emit("execute", node_name(server), "raft periodic")
        elif cmd == "Timeout":
            name = node_name(pc[1])
            builder.emit("intercept", name, "inc_time_ms", str(ELECTION_TIMEOUT_MS))
            builder.emit("execute", name, "raft periodic %d" % ELECTION_TIMEOUT_MS)
        elif cmd == "ClientRequest":
            builder.emit("execute", node_name(pc[1]), "raft cli v")
        elif cmd == "AppendEntriesAll":
            builder.emit("execute", node_name(pc[1]), "raft periodic %d" % REQUEST_TIMEOUT_MS)
        elif cmd == "LoseMessage":
            builder.emit("clear", node_name(pc[1]), node_name(pc[2]))
        elif str(cmd).startswith("Handle"):
            dest, src, seq = pc[1], pc[2], pc[3]
            builder.emit("deliver-unordered", node_name(src), node_name(dest), seq)
            builder.emit("loop", "intercept", node_name(dest), "check_has_recv_queue", node_name(src))
            builder.emit("execute", node_name(dest), "raft recvfrom " + node_name(src))
        else:
            raise NotControllable("no stock command for pc %s" % pc)
        builder.compare_all(state)
    for server in builder.servers:
        builder.emit("execute", node_name(server), "raft statemachine")
    return builder


def main():
    args = parse_args()
    copy_config(args.config, not args.in_place)
    try:
        os.symlink(args.trace_file, "tlc_trace.txt")
    except OSError:
        pass
    reader = TraceReader(True)
    states = list(reader.trace_reader(args.trace_file))
    if len(states) < 1:
        raise SystemExit("no states in " + args.trace_file)
    if "scr" not in states[0]:
        raise SystemExit("not controllable: trace has no scr; redisraft replay requires scr.pc")
    try:
        builder = build_from_pc(reader, states)
    except NotControllable as exc:
        raise SystemExit("not controllable: " + str(exc))
    with open(args.output, "w") as handle:
        handle.write("\n".join(builder.lines) + "\n")


if __name__ == "__main__":
    main()
