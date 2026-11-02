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


def fmt_bool(value):
    if value in (True, "TRUE", "True", 1, "1"):
        return "1"
    return "0"


def fmt_servers(value):
    if value in (None, "Nil", set(), frozenset()):
        return "{}"
    if isinstance(value, str):
        return "{}" if value == "Nil" else "{%s}" % node_name(value)
    names = sorted(node_name(item) for item in value)
    return "{" + ",".join(names) + "}"


def fmt_vote(value):
    if value in (None, "Nil"):
        return "Nil"
    return node_name(value)


def fmt_entry(entry):
    kind = entry.get("type")
    term = entry.get("term")
    if kind == "NoopEntry":
        body = "Noop"
    elif kind == "ValueEntry":
        body = "Value"
    elif kind == "ConfigEntry":
        body = "Config:" + fmt_servers(entry.get("config"))
    else:
        body = "UNKNOWN"
    return "(%s,%s)" % (term, body)


def fmt_log(entries):
    if not entries:
        return "[]"
    return "[" + ", ".join(fmt_entry(entry) for entry in entries) + "]"


def fmt_index_map(mapping):
    items = []
    for key, value in sorted(mapping.items(), key=lambda kv: node_name(kv[0])):
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

    def field(self, name, node, variable, model):
        self.emit("execute", node, "get " + variable)
        self.comment("variable %s %s %s" % (variable, node, model))
        self.emit("compare", "variable")

    def compare_node(self, state, server):
        name = node_name(server)
        role = state["state"][server]
        if role not in STATE_CODE:
            raise NotControllable("unmapped state %s" % role)
        self.field(name, name, "currentTerm", state["currentTerm"][server])
        self.field(name, name, "votedFor", fmt_vote(state["votedFor"][server]))
        self.field(name, name, "state", STATE_CODE[role])
        self.field(name, name, "log", fmt_log(state["log"][server]))
        self.field(name, name, "commitIdx", state["commitIndex"][server])
        self.field(name, name, "logOffset", state["logOffset"][server])
        self.field(name, name, "nextIdx", fmt_index_map(state["nextIndex"][server]))
        self.field(name, name, "matchIdx", fmt_index_map(state["matchIndex"][server]))
        self.field(name, name, "votesGranted", fmt_servers(state["votesGranted"][server]))
        self.field(name, name, "snapshotLastIdx", state["snapshotLastIdx"][server])
        self.field(name, name, "snapshotLastTerm", state["snapshotLastTerm"][server])
        self.field(name, name, "loadingSnapshot", fmt_bool(state["loadingSnapshot"][server]))
        self.field(name, name, "pendingSnapshotIdx", state["pendingSnapshotIdx"][server])
        self.field(name, name, "pendingSnapshotTerm", state["pendingSnapshotTerm"][server])
        self.field(name, name, "clusterConfig", fmt_servers(state["clusterConfig"][server]))
        self.field(name, name, "votingCfgChangeIdx", state["votingCfgChangeIdx"][server])

    def compare_all(self, state, label):
        self.comment(label)
        for server in self.servers:
            self.compare_node(state, server)
        self.field(self.servers[0], node_name(self.servers[0]), "staleRead", fmt_bool(state["staleReadDetected"]))
        self.field(self.servers[0], node_name(self.servers[0]), "noopRead", fmt_bool(state["noopReadDetected"]))
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
        if index > 0:
            builder.compare_all(states[index - 1], "before [%d]" % index)
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
        elif cmd == "Timeout":
            builder.emit("execute", node_name(pc[1]), "raft election")
        elif cmd == "BecomeLeader":
            builder.emit("execute", node_name(pc[1]), "raft become-leader")
        elif cmd == "ClientRequest":
            builder.emit("execute", node_name(pc[1]), "raft cli v")
        elif cmd == "AppendEntries":
            builder.emit("execute", node_name(pc[1]), "raft appendentries " + node_name(pc[2]))
        elif cmd == "AdvanceCommitIndex":
            builder.emit("execute", node_name(pc[1]), "raft advance-commit")
        elif cmd == "TakeSnapshot":
            builder.emit("execute", node_name(pc[1]), "raft snapshot")
        elif cmd == "SendInstallSnapshot":
            builder.emit("execute", node_name(pc[1]), "raft snapshot-send " + node_name(pc[2]))
        elif cmd == "EndLoadSnapshot":
            builder.emit("execute", node_name(pc[1]), "raft end-load")
        elif cmd == "ClientNonQuorumRead":
            builder.emit("execute", node_name(pc[1]), "raft read")
        elif cmd == "ProposeAddServer":
            builder.emit("execute", node_name(pc[1]), "raft add " + node_name(pc[2]))
        elif cmd == "ProposeRemoveServer":
            builder.emit("execute", node_name(pc[1]), "raft remove " + node_name(pc[2]))
        elif cmd == "Crash":
            name = node_name(pc[1])
            builder.emit("execute", name, "raft crash")
            builder.emit("execute", name, "raft recover")
        elif cmd in ("LoseMessage", "DropStaleMessage"):
            builder.emit("drop-unordered", node_name(pc[1]), node_name(pc[2]), pc[3])
        elif str(cmd).startswith("Handle"):
            dest, src, seq = pc[1], pc[2], pc[3]
            builder.emit("deliver-unordered", node_name(src), node_name(dest), seq)
            builder.emit("loop", "intercept", node_name(dest), "check_has_recv_queue", node_name(src))
            builder.emit("execute", node_name(dest), "raft recvfrom " + node_name(src))
        else:
            raise NotControllable("no command for pc %s" % pc)
        builder.compare_all(state, "after [%d]" % index)
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
