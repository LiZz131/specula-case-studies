#!/usr/bin/env python3
"""Turn any Specula willemt/raft TLC trace into SandTable controller commands.

Specula's base.tla / MC.tla do not record scr.pc. TLC labels a disjunctive
Next as one action, so the name in MC.out is not the sub-action. This
generator recovers the sub-action by diffing counters and the message bag,
then emits only stock controller and driver commands.

Code sends that the model does not record (become-leader AppendEntries,
the first client append, the failure-handler resend, the install-snapshot
reply) are removed with `clear` when that TCP channel holds nothing the
model still contains. `clear` drops the whole channel; a trace that needs
to drop one message and keep another on the same channel is refused.
"""

import argparse
import json
import os
import shutil
import sys
from collections import Counter


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

STATE_CODE = {"Follower": "1", "Candidate": "2", "Leader": "3"}
REQUEST_TIMEOUT_MS = 200
ELECTION_TIMEOUT_MS = 2000


class NotControllable(Exception):
    """This model step has no stock SandTable command sequence."""


def node_name(server):
    text = str(server)
    if text.startswith("s") and text[1:].isdigit():
        return "n" + text[1:]
    return text


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
    messages = state["messages"]
    if not isinstance(messages, dict):
        return []
    items = []
    for key, count in messages.items():
        message = parse_record(reader, key)
        items.extend([message] * int(count))
    return items


def signature(message):
    return json.dumps(message, sort_keys=True, default=str)


def bag_diff(before, after):
    old = Counter(signature(m) for m in before)
    new = Counter(signature(m) for m in after)
    removed = []
    added = []
    for sig, count in (old - new).items():
        removed.extend([json.loads(sig)] * count)
    for sig, count in (new - old).items():
        added.extend([json.loads(sig)] * count)
    return removed, added


def counter_delta(before, after, name):
    old = before.get("counters") or {}
    new = after.get("counters") or {}
    if not isinstance(old, dict) or not isinstance(new, dict):
        return 0
    return int(new.get(name, 0)) - int(old.get(name, 0))


def last_log_index(state, server):
    return int(state["snapshotLastIdx"][server]) + len(state["log"][server] or [])


def needs_snapshot(state, leader, peer):
    snap = int(state["snapshotLastIdx"][leader])
    return snap > 0 and int(state["nextIndex"][leader][peer]) < snap


def fmt_log(entries):
    if not entries:
        return "[]"
    parts = ["(%s, '%s')" % (entry["term"], entry["value"]) for entry in entries]
    return "[" + ", ".join(parts) + "]"


def fmt_name_set(values):
    if isinstance(values, str):
        text = values.strip("{}")
        values = [part.strip() for part in text.split(",") if part.strip()]
    names = sorted(node_name(value) for value in values)
    return "{" + ", ".join(names) + "}"


def fmt_index_map(mapping, self_name):
    items = []
    for key, value in sorted(mapping.items(), key=lambda kv: node_name(kv[0])):
        if node_name(key) == self_name:
            continue
        items.append("'%s': %s" % (node_name(key), value))
    return "{" + ", ".join(items) + "}"


def endpoint(message):
    return node_name(message["msource"]), node_name(message["mdest"]), message["mtype"]


class Builder:
    def __init__(self, reader, states):
        self.reader = reader
        self.states = states
        self.servers = sorted(states[0]["state"].keys(), key=node_name)
        self.lines = []
        self.seq = 0
        self.queue = {}
        self.actions = []

    def emit(self, *words):
        self.lines.append(" ".join(str(word) for word in words))

    def comment(self, text):
        self.lines.append("# " + text)

    def peers(self, server):
        return [other for other in self.servers if other != server]

    def capture(self, src, dst, mtype, accounted):
        self.seq += 1
        item = {
            "seq": self.seq,
            "src": node_name(src),
            "dst": node_name(dst),
            "mtype": mtype,
            "accounted": accounted,
            "delivered": False,
            "cleared": False,
        }
        self.queue.setdefault((item["src"], item["dst"]), []).append(item)
        return item

    def outstanding(self, src, dst):
        return [
            item for item in self.queue.get((node_name(src), node_name(dst)), [])
            if not item["delivered"] and not item["cleared"]
        ]

    def deliver(self, message):
        src, dst, mtype = endpoint(message)
        choices = [item for item in self.outstanding(src, dst) if item["mtype"] == mtype and item["accounted"]]
        if len(choices) != 1:
            raise NotControllable(
                "need one queued %s %s -> %s, found %d" % (mtype, src, dst, len(choices))
            )
        item = choices[0]
        self.emit("deliver-unordered", src, dst, item["seq"])
        self.emit("loop", "intercept", dst, "check_has_recv_queue", src)
        self.emit("execute", dst, "raft recvfrom " + src)
        item["delivered"] = True

    def clear_channel(self, src, dst, reason):
        pending = self.outstanding(src, dst)
        if any(item["accounted"] for item in pending):
            raise NotControllable(
                "clear %s -> %s would also drop a message the model still has (%s)"
                % (node_name(src), node_name(dst), reason)
            )
        if not pending:
            raise NotControllable("clear %s -> %s but the channel is empty (%s)" % (src, dst, reason))
        self.comment("clear code-only %s -> %s (%s)" % (node_name(src), node_name(dst), reason))
        self.emit("clear", node_name(src), node_name(dst))
        for item in pending:
            item["cleared"] = True

    def flush_code_only(self, reason):
        for src, dst in sorted(self.queue):
            pending = self.outstanding(src, dst)
            if not pending or all(item["accounted"] for item in pending):
                continue
            self.clear_channel(src, dst, reason)

    def live_counts(self):
        counts = Counter()
        for items in self.queue.values():
            for item in items:
                if item["accounted"] and not item["delivered"] and not item["cleared"]:
                    counts[(item["src"], item["dst"], item["mtype"])] += 1
        return counts

    def assert_matches(self, state):
        model = Counter(endpoint(message) for message in bag_messages(self.reader, state))
        live = self.live_counts()
        if live != model:
            raise NotControllable("predicted queue %s != model bag %s" % (dict(live), dict(model)))

    def send_kind(self, state, leader, peer):
        if needs_snapshot(state, leader, peer):
            return "InstallSnapshotRequest"
        return "AppendEntriesRequest"

    def emit_send_all(self, leader, state, added):
        """raft_send_appendentries_all walks peers in node-name order and stops at the first snapshot."""
        if state["state"][leader] != "Leader":
            raise NotControllable("%s is not leader, periodic %d would not send" % (node_name(leader), REQUEST_TIMEOUT_MS))
        self.emit("execute", node_name(leader), "raft periodic %d" % REQUEST_TIMEOUT_MS)
        need = Counter((node_name(message["mdest"]), message["mtype"]) for message in added)
        for peer in self.peers(leader):
            kind = self.send_kind(state, leader, peer)
            accounted = need[(node_name(peer), kind)] > 0
            if accounted:
                need[(node_name(peer), kind)] -= 1
            self.capture(leader, peer, kind, accounted)
            if kind == "InstallSnapshotRequest":
                break
        missing = {key: count for key, count in need.items() if count}
        if missing:
            raise NotControllable(
                "periodic %d on %s does not emit %s; send_appendentries_all stops at the first snapshot"
                % (REQUEST_TIMEOUT_MS, node_name(leader), missing)
            )

    def emit_leader_sends(self, leader, state, accounted):
        for peer in self.peers(leader):
            self.capture(leader, peer, self.send_kind(state, leader, peer), accounted)

    def compare_node(self, state, server):
        name = node_name(server)
        fields = [
            ("commitIdx", state["commitIndex"][server]),
            ("currentTerm", state["currentTerm"][server]),
            ("log", fmt_log(state["log"][server])),
            ("state", STATE_CODE[state["state"][server]]),
            ("lastApplied", state["lastApplied"][server]),
            ("votedFor", "Nil" if state["votedFor"][server] in ("Nil", None) else node_name(state["votedFor"][server])),
            ("votesGranted", fmt_name_set(state["votesGranted"][server])),
            ("snapshotLastIdx", state["snapshotLastIdx"][server]),
            ("snapshotLastTerm", state["snapshotLastTerm"][server]),
            ("crashed", "TRUE" if state["crashed"][server] in (True, "TRUE", "True") else "FALSE"),
            ("nextIdx", fmt_index_map(state["nextIndex"][server], name)),
            ("matchIdx", fmt_index_map(state["matchIndex"][server], name)),
        ]
        for key, expected in fields:
            self.emit("execute", name, "get " + key)
            self.comment("variable %s %s %s" % (key, name, expected))
            self.emit("compare", "variable")
        for key in ("persistedTerm", "persistedVote", "logOfferCount"):
            self.emit("execute", name, "get " + key)
            self.comment("none")
            self.emit("compare", "none")

    def compare_all(self, state):
        for server in self.servers:
            self.compare_node(state, server)
        self.comment("net-len %d" % len(bag_messages(self.reader, state)))
        self.emit("compare", "net-len")

    def init(self, state):
        self.comment("[0] Init")
        self.actions.append("Init")
        self.emit("init", len(self.servers))
        for server in self.servers:
            name = node_name(server)
            self.emit("execute", name, "net connectall")
            self.emit("execute", name, "raft init")
        self.emit("wait-init", len(self.servers))
        for server in self.servers:
            self.emit("loop", "execute", node_name(server), "net isallconnected")
        for server in self.servers:
            self.emit("execute", node_name(server), "raft periodic")
        self.assert_matches(state)
        self.compare_all(state)

    def finish_step(self, state, reason):
        self.flush_code_only(reason)
        self.assert_matches(state)
        self.compare_all(state)

    def who_changed(self, before, after, field, predicate):
        found = [server for server in self.servers if predicate(server)]
        if len(found) != 1:
            raise NotControllable("%s changed on %s" % (field, found))
        return found[0]

    def infer(self, before, after):
        removed, added = bag_diff(
            bag_messages(self.reader, before), bag_messages(self.reader, after)
        )
        if counter_delta(before, after, "timeout"):
            server = self.who_changed(
                before, after, "term",
                lambda s: after["state"][s] == "Candidate" and int(after["currentTerm"][s]) == int(before["currentTerm"][s]) + 1,
            )
            return ("Timeout", server, removed, added)
        if counter_delta(before, after, "request"):
            server = self.who_changed(
                before, after, "log",
                lambda s: len(after["log"][s] or []) == len(before["log"][s] or []) + 1,
            )
            value = after["log"][server][-1]["value"]
            return ("ClientRequest", server, value, removed, added)
        if counter_delta(before, after, "lose"):
            if len(removed) != 1 or added:
                raise NotControllable("LoseMessage changed the bag by removed=%d added=%d" % (len(removed), len(added)))
            return ("LoseMessage", removed[0], removed, added)
        if counter_delta(before, after, "duplicate"):
            raise NotControllable(
                "DuplicateMessage keeps two copies in the model bag; deliver-unordered consumes the single TCP copy"
            )
        if counter_delta(before, after, "snapshot"):
            server = self.who_changed(
                before, after, "snapshot",
                lambda s: int(after["snapshotLastIdx"][s]) != int(before["snapshotLastIdx"][s]),
            )
            return ("TakeSnapshot", server, removed, added)
        if counter_delta(before, after, "broadcast"):
            if not added or any(message["mtype"] != "AppendEntriesRequest" for message in added):
                raise NotControllable("BroadcastAppendEntries did not only add AppendEntries")
            sources = {message["msource"] for message in added}
            if len(sources) != 1:
                raise NotControllable("broadcast from %s" % sources)
            return ("BroadcastAppendEntries", sources.pop(), removed, added)
        if counter_delta(before, after, "crash"):
            raise NotControllable("Crash has no stock driver command")
        if len(removed) == 1 and not added and removed[0]["mtype"] == "RequestVoteResponse":
            return ("HandleRequestVoteResponse", removed[0], removed, added)
        if len(removed) == 1 and len(added) == 1 and removed[0]["mtype"] == "RequestVoteRequest" and added[0]["mtype"] == "RequestVoteResponse":
            return ("HandleRequestVoteRequest", removed[0], added[0], removed, added)
        if len(removed) == 1 and len(added) == 1 and removed[0]["mtype"] == "AppendEntriesRequest" and added[0]["mtype"] == "AppendEntriesResponse":
            return ("HandleAppendEntriesRequest", removed[0], added[0], removed, added)
        if len(removed) == 1 and not added and removed[0]["mtype"] == "AppendEntriesResponse":
            return ("HandleAppendEntriesResponse", removed[0], removed, added)
        if len(removed) == 1 and not added and removed[0]["mtype"] == "InstallSnapshotRequest":
            return ("HandleInstallSnapshot", removed[0], removed, added)
        if not removed and len(added) == 1 and added[0]["mtype"] == "AppendEntriesRequest":
            return ("SendAppendEntries", added[0]["msource"], removed, added)
        if not removed and len(added) == 1 and added[0]["mtype"] == "InstallSnapshotRequest":
            return ("SendInstallSnapshot", added[0]["msource"], removed, added)
        crashed_before = before.get("crashed") or {}
        crashed_after = after.get("crashed") or {}
        if isinstance(crashed_before, dict):
            recovered = [s for s in self.servers if crashed_before.get(s) and not crashed_after.get(s)]
            if recovered:
                raise NotControllable("Recover has no stock driver command")
        raise NotControllable(
            "unrecognized step, removed %s, added %s"
            % ([endpoint(m) for m in removed], [endpoint(m) for m in added])
        )

    def response_resend(self, before, after, message):
        leader = message["mdest"]
        peer = message["msource"]
        if message["mterm"] > before["currentTerm"][leader]:
            return False
        if message["mterm"] < before["currentTerm"][leader]:
            return False
        if before["state"][leader] != "Leader":
            return False
        if message["msuccess"]:
            if message["mcurrentIdx"] <= before["matchIndex"][leader][peer]:
                return False
            return int(after["nextIndex"][leader][peer]) <= last_log_index(after, leader)
        if message["mcurrentIdx"] < before["matchIndex"][leader][peer]:
            return False
        return True

    def apply(self, index, before, after):
        kind = self.infer(before, after)
        name = kind[0]
        self.actions.append(name)
        label = [name]
        for part in kind[1:3]:
            if isinstance(part, dict) and "mtype" in part:
                label.append("%s %s -> %s" % endpoint(part))
            elif not isinstance(part, (dict, list)):
                label.append(node_name(part) if name != "ClientRequest" or part in self.servers else str(part))
        if name == "ClientRequest":
            label = ["ClientRequest", node_name(kind[1]), str(kind[2])]
        self.comment("[%d] %s" % (index, " ".join(label)))

        if name == "Timeout":
            server = kind[1]
            self.emit("intercept", node_name(server), "inc_time_ms", str(ELECTION_TIMEOUT_MS))
            self.emit("execute", node_name(server), "raft periodic %d" % ELECTION_TIMEOUT_MS)
            for peer in self.peers(server):
                self.capture(server, peer, "RequestVoteRequest", True)
        elif name == "LoseMessage":
            message = kind[1]
            src, dst, _ = endpoint(message)
            pending = self.outstanding(src, dst)
            if len(pending) != 1 or not pending[0]["accounted"] or pending[0]["mtype"] != message["mtype"]:
                raise NotControllable(
                    "LoseMessage %s -> %s is not alone on that TCP channel; clear would drop the rest" % (src, dst)
                )
            pending[0]["accounted"] = False
            self.clear_channel(src, dst, "LoseMessage")
        elif name == "ClientRequest":
            server, value = kind[1], kind[2]
            self.emit("execute", node_name(server), "raft cli %s" % value)
            for peer in self.peers(server):
                if int(after["nextIndex"][server][peer]) == last_log_index(after, server):
                    self.capture(server, peer, "AppendEntriesRequest", False)
        elif name in ("BroadcastAppendEntries", "SendAppendEntries", "SendInstallSnapshot"):
            self.emit_send_all(kind[1], after, kind[-1])
        elif name == "TakeSnapshot":
            self.emit("execute", node_name(kind[1]), "raft snapshot")
        elif name == "HandleRequestVoteRequest":
            self.deliver(kind[1])
            response = kind[2]
            self.capture(response["msource"], response["mdest"], "RequestVoteResponse", True)
        elif name == "HandleRequestVoteResponse":
            message = kind[1]
            self.deliver(message)
            leader = message["mdest"]
            if before["state"][leader] != "Leader" and after["state"][leader] == "Leader":
                self.emit_leader_sends(leader, after, accounted=False)
        elif name == "HandleAppendEntriesRequest":
            self.deliver(kind[1])
            response = kind[2]
            self.capture(response["msource"], response["mdest"], "AppendEntriesResponse", True)
        elif name == "HandleAppendEntriesResponse":
            message = kind[1]
            self.deliver(message)
            if self.response_resend(before, after, message):
                leader, peer = message["mdest"], message["msource"]
                self.capture(leader, peer, self.send_kind(after, leader, peer), False)
        elif name == "HandleInstallSnapshot":
            message = kind[1]
            if int(message["mterm"]) < int(before["currentTerm"][message["mdest"]]):
                raise NotControllable(
                    "driver drops a snapshot whose sender term is below the receiver; the model still loads it"
                )
            self.deliver(message)
            self.capture(message["mdest"], message["msource"], "AppendEntriesResponse", False)
        else:
            raise NotControllable(name)
        self.finish_step(after, name)

    def build(self):
        self.init(self.states[0])
        for index in range(1, len(self.states)):
            try:
                self.apply(index, self.states[index - 1], self.states[index])
            except NotControllable as exc:
                raise NotControllable("step %d: %s" % (index, exc)) from exc
        for server in self.servers:
            self.emit("execute", node_name(server), "raft statemachine")
        return "\n".join(self.lines) + "\n"


def peer_order(leader):
    name = node_name(leader)
    others = [node for node in ("n1", "n2", "n3") if node != name]
    return others


def as_peers(value):
    if isinstance(value, str):
        text = value.strip("{}")
        return [node_name(part.strip()) for part in text.split(",") if part.strip()]
    return [node_name(part) for part in value]


def build_from_pc(reader, states):
    """Replay label, which names a base.tla action and its witness."""
    b = Builder(reader, states)
    b.actions = []
    for index, state in enumerate(states):
        if index:
            b.comment("[%d] before" % index)
            b.compare_all(states[index - 1])
        pc = state.get("label") or state["scr"]["pc"]
        if not isinstance(pc, list) or not pc:
            raise NotControllable("state %d has no label" % index)
        cmd = pc[0]
        b.actions.append(cmd)
        b.comment("[%d] %s" % (index, " ".join(str(part) for part in pc)))
        try:
            if cmd == "Init":
                b.emit("init", len(b.servers))
                for server in b.servers:
                    name = node_name(server)
                    b.emit("execute", name, "net connectall")
                    b.emit("execute", name, "raft init")
                b.emit("wait-init", len(b.servers))
                for server in b.servers:
                    b.emit("loop", "execute", node_name(server), "net isallconnected")
                for server in b.servers:
                    b.emit("execute", node_name(server), "raft periodic")
            elif cmd == "Timeout":
                name = node_name(pc[1])
                b.emit("intercept", name, "inc_time_ms", str(ELECTION_TIMEOUT_MS))
                b.emit("execute", name, "raft periodic %d" % ELECTION_TIMEOUT_MS)
            elif cmd == "ClientRequest":
                b.emit("execute", node_name(pc[1]), "raft cli %s" % pc[2])
            elif cmd in ("SendAppendEntries", "SendInstallSnapshot"):
                b.emit("execute", node_name(pc[1]), "raft send-peer %s" % node_name(pc[2]))
            elif cmd == "BroadcastAppendEntries":
                chosen = set(as_peers(pc[2]))
                for peer in peer_order(pc[1]):
                    if peer in chosen:
                        b.emit("execute", node_name(pc[1]), "raft send-peer " + peer)
            elif cmd == "TakeSnapshot":
                b.emit("execute", node_name(pc[1]), "raft snapshot")
            elif cmd == "Crash":
                b.emit("execute", node_name(pc[1]), "raft crash")
            elif cmd == "Recover":
                b.emit("execute", node_name(pc[1]), "raft recover")
            elif cmd == "LoseMessage":
                b.emit("drop-unordered", node_name(pc[1]), node_name(pc[2]), pc[3])
            elif cmd == "DuplicateMessage":
                b.emit("duplicate-unordered", node_name(pc[1]), node_name(pc[2]), pc[3])
            elif cmd.startswith("Handle"):
                dest, src, seq = pc[1], pc[2], pc[3]
                if cmd == "HandleRequestVoteRequest":
                    b.emit("execute", node_name(dest), "raft vote-mode " + str(pc[4]))
                b.emit("deliver-unordered", node_name(src), node_name(dest), seq)
                b.emit("loop", "intercept", node_name(dest), "check_has_recv_queue", node_name(src))
                b.emit("execute", node_name(dest), "raft recvfrom " + node_name(src))
            else:
                raise NotControllable("no command for label %s" % pc)
        except NotControllable:
            raise
        except Exception as exc:
            raise NotControllable("step %d label %s: %s" % (index, pc, exc)) from exc
        b.comment("[%d] after" % index)
        b.compare_all(state)
    for server in b.servers:
        b.emit("execute", node_name(server), "raft statemachine")
    return b


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
    try:
        if "label" in states[0] or "scr" in states[0]:
            builder = build_from_pc(reader, states)
            text = "\n".join(builder.lines) + "\n"
        else:
            builder = Builder(reader, states)
            text = builder.build()
    except NotControllable as exc:
        raise SystemExit("not controllable: " + str(exc))
    with open(args.output, "w") as handle:
        handle.write(text)
    print("actions:", " ".join(builder.actions), file=sys.stderr)
    print("wrote", os.path.abspath(args.output), "states", len(states), file=sys.stderr)


if __name__ == "__main__":
    main()
