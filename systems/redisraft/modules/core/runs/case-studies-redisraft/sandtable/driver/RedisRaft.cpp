// RedisRaft driver for one spec action per controller command.
// Persistence uses the library's log and metadata callbacks.
// Crash destroys the server; Recover rebuilds it from that image.

#include <algorithm>
#include <cassert>
#include <cstring>
#include <fstream>
#include <set>
#include <sys/time.h>
#include "Raft.h"
#include "Network.h"
#include "specula_step.h"

extern "C" {
#include "raft.h"
#include "raft_log.h"
#include "raft_private.h"
int raft_send_snapshot(raft_server_t *me, raft_node_t *node);
}

#define DATA_LEN 8

enum {
    MSG_AE,
    MSG_AER,
    MSG_RV,
    MSG_RVR,
    MSG_SNAP
};

struct DiskEntry {
    long term;
    int type;
    int id;
    string data;
};

struct Disk {
    long term = 0;
    int vote = -1;
    long snap_idx = 0;
    long snap_term = 0;
    long log_offset = 0;
    vector<DiskEntry> log;
    set<int> config;
    bool loading = false;
    long pending_idx = 0;
    long pending_term = 0;
    int voting_cfg = 0;
};

static Disk disk;
static bool replaying = false;
static bool server_down = false;
static string snap_hold;
static string state_machine = "init";
/* Shared by n1, n2, n3. Each container has its own /tmp; the SandTable mount is not. */
static const char *kFlags = "/root/sandtable/specula-ce/runtime/read-flags";
static const char *kCommitDir = "/root/sandtable/specula-ce/runtime";

static raft_server_t *me_of() {
    return static_cast<raft_server_t *>(config.get_raft_server());
}

static string node_name_of(int id) {
    return string("n") + to_string(id);
}

static int id_of(const string &name) {
    return stoi(name.substr(1));
}

static string pack_msg(const string &msg, int type) {
    string ret;
    ret.resize(4);
    *(int *) &ret.front() = type;
    ret += msg;
    return ret;
}

static string unpack_msg(const string &msg, int &type) {
    assert(msg.size() > sizeof(int));
    type = *(const int *) &msg.front();
    return msg.substr(sizeof(int));
}

static string bytes_of(const raft_entry_t *ety) {
    if (!ety || ety->data_len == 0 || ety->data == nullptr) {
        return "";
    }
    size_t n = strnlen(ety->data, ety->data_len);
    return string(ety->data, n);
}

static string config_text(const set<int> &ids) {
    string text;
    for (int id : ids) {
        if (!text.empty()) {
            text += ",";
        }
        text += to_string(id);
    }
    return text;
}

static set<int> parse_config(const string &text) {
    set<int> ids;
    string cur;
    for (char ch : text) {
        if (ch == ',') {
            if (!cur.empty()) {
                ids.insert(stoi(cur));
                cur.clear();
            }
        } else if (ch >= '0' && ch <= '9') {
            cur.push_back(ch);
        }
    }
    if (!cur.empty()) {
        ids.insert(stoi(cur));
    }
    return ids;
}

static string format_config(const set<int> &ids) {
    vector<string> names;
    for (int id : ids) {
        names.push_back(node_name_of(id));
    }
    sort(names.begin(), names.end());
    string text = "{";
    for (size_t i = 0; i < names.size(); i++) {
        if (i) {
            text += ",";
        }
        text += names[i];
    }
    text += "}";
    return text;
}

static string format_entries(const vector<DiskEntry> &entries) {
    string res = "[";
    for (size_t i = 0; i < entries.size(); i++) {
        if (i) {
            res += ", ";
        }
        const DiskEntry &ety = entries[i];
        res += "(" + to_string(ety.term) + ",";
        if (ety.type == RAFT_LOGTYPE_NO_OP) {
            res += "Noop)";
        } else if (ety.type == RAFT_LOGTYPE_NORMAL) {
            res += "Value)";
        } else if (ety.type == RAFT_LOGTYPE_ADD_NODE || ety.type == RAFT_LOGTYPE_REMOVE_NODE) {
            res += "Config:" + format_config(parse_config(ety.data)) + ")";
        } else {
            res += "UNKNOWN)";
        }
    }
    res += "]";
    return res;
}

static void write_flags(int stale, int noop) {
    ofstream out(kFlags, ios::trunc);
    out << stale << " " << noop << "\n";
}

static void read_flags(int &stale, int &noop) {
    ifstream in(kFlags);
    stale = 0;
    noop = 0;
    if (in) {
        in >> stale >> noop;
    }
}

static void publish_commit(raft_server_t *me) {
    if (!me) {
        return;
    }
    Node self = config.get_self_node();
    ofstream out(string(kCommitDir) + "/commit-" + self.name, ios::trunc);
    out << me->commit_idx << "\n";
}

static long published_commit(int id) {
    ifstream in(string(kCommitDir) + "/commit-" + node_name_of(id));
    long value = 0;
    if (in) {
        in >> value;
    }
    return value;
}

static int on_offer(raft_server_t *, void *, raft_entry_t *entry, raft_index_t) {
    if (replaying || !entry) {
        return 0;
    }
    DiskEntry copy;
    copy.term = entry->term;
    copy.type = entry->type;
    copy.id = entry->id;
    copy.data = bytes_of(entry);
    disk.log.push_back(copy);
    return 0;
}

static int on_poll(raft_server_t *, void *, raft_entry_t *, raft_index_t) {
    if (replaying) {
        return 0;
    }
    if (!disk.log.empty()) {
        disk.log.erase(disk.log.begin());
    }
    disk.log_offset++;
    return 0;
}

static int on_pop(raft_server_t *, void *, raft_entry_t *, raft_index_t) {
    if (replaying) {
        return 0;
    }
    if (!disk.log.empty()) {
        disk.log.pop_back();
    }
    return 0;
}

static int on_clear(raft_server_t *, void *, raft_entry_t *, raft_index_t) {
    if (replaying) {
        return 0;
    }
    disk.log.clear();
    return 0;
}

static raft_log_cbs_t log_cbs = {
    on_offer,
    on_poll,
    on_pop,
    on_clear
};

static void attach_log(raft_server_t *me) {
    raft_log_set_callbacks(static_cast<raft_log_t *>(raft_get_log(me)), &log_cbs, me);
}

static void arm_step() {
    specula_step = 1;
}

static int recompute_voting(raft_server_t *me) {
    auto *log = static_cast<raft_log_t *>(raft_get_log(me));
    raft_index_t base = raft_log_get_base(log);
    raft_index_t count = raft_log_count(log);
    int voting = 0;
    for (raft_index_t i = 1; i <= count; i++) {
        raft_index_t idx = base + i;
        raft_entry_t *ety = raft_log_get_at_idx(log, idx);
        if (!ety) {
            continue;
        }
        if ((ety->type == RAFT_LOGTYPE_ADD_NODE || ety->type == RAFT_LOGTYPE_REMOVE_NODE) &&
            (long) idx > (long) me->commit_idx && (int) idx > voting) {
            voting = (int) idx;
        }
    }
    disk.voting_cfg = voting;
    me->voting_cfg_change_log_idx = voting == 0 ? -1 : voting;
    return voting;
}

static void note_commits(raft_server_t *me, raft_index_t old_commit) {
    if (me->commit_idx > old_commit) {
        auto *log = static_cast<raft_log_t *>(raft_get_log(me));
        raft_index_t base = raft_log_get_base(log);
        for (raft_index_t idx = old_commit + 1; idx <= me->commit_idx; idx++) {
            if (idx <= base) {
                continue;
            }
            raft_entry_t *ety = raft_log_get_at_idx(log, idx);
            if (!ety) {
                continue;
            }
            if (ety->type == RAFT_LOGTYPE_ADD_NODE || ety->type == RAFT_LOGTYPE_REMOVE_NODE) {
                disk.config = parse_config(bytes_of(ety));
            }
        }
    }
    recompute_voting(me);
    publish_commit(me);
}

static set<int> effective_config(raft_server_t *me) {
    auto *log = static_cast<raft_log_t *>(raft_get_log(me));
    raft_index_t base = raft_log_get_base(log);
    raft_index_t count = raft_log_count(log);
    bool found = false;
    set<int> cfg = disk.config;
    for (raft_index_t i = 1; i <= count; i++) {
        raft_entry_t *ety = raft_log_get_at_idx(log, base + i);
        if (!ety) {
            continue;
        }
        if (ety->type == RAFT_LOGTYPE_ADD_NODE || ety->type == RAFT_LOGTYPE_REMOVE_NODE) {
            cfg = parse_config(bytes_of(ety));
            found = true;
        }
    }
    if (!found) {
        return disk.config;
    }
    return cfg;
}

static raft_term_t term_at(raft_server_t *me, raft_index_t idx) {
    if (idx == 0) {
        return 0;
    }
    if ((long) idx == (long) me->snapshot_last_idx) {
        return me->snapshot_last_term;
    }
    raft_entry_t *ety = raft_get_entry_from_idx(me, idx);
    if (!ety) {
        return 0;
    }
    raft_term_t term = ety->term;
    raft_entry_release(ety);
    return term;
}

static bool current_term_committed(raft_server_t *me) {
    auto *log = static_cast<raft_log_t *>(raft_get_log(me));
    raft_index_t base = raft_log_get_base(log);
    raft_index_t count = raft_log_count(log);
    raft_index_t limit = me->commit_idx > base ? me->commit_idx - base : 0;
    if (limit > count) {
        limit = count;
    }
    for (raft_index_t k = 1; k <= limit; k++) {
        raft_entry_t *ety = raft_log_get_at_idx(log, base + k);
        if (ety && ety->term == me->current_term) {
            return true;
        }
    }
    return false;
}

static string serialization_ae(raft_appendentries_req_t *msg) {
    string data;
    data.resize(sizeof(*msg) + msg->n_entries * (DATA_LEN + sizeof(raft_entry_req_t)));
    *(raft_appendentries_req_t *) &data.front() = *msg;
    for (long i = 0; i < msg->n_entries; i++) {
        auto *p = (raft_entry_req_t *) ((char *) &data.front() + sizeof(*msg) +
                                        (sizeof(raft_entry_req_t) + DATA_LEN) * i);
        *p = *(msg->entries[i]);
        if (msg->entries[i]->data_len > 0) {
            size_t n = msg->entries[i]->data_len;
        if (n > DATA_LEN) {
            n = DATA_LEN;
        }
        memcpy(p->data, msg->entries[i]->data, n);
        }
    }
    return data;
}

static raft_appendentries_req_t *deserialization_ae(string &data) {
    auto *msg = static_cast<raft_appendentries_req_t *>(raft_calloc(1, sizeof(raft_appendentries_req_t)));
    *msg = *(raft_appendentries_req_t *) &data.front();
    msg->entries = static_cast<raft_entry_req_t **>(raft_calloc(msg->n_entries, sizeof(raft_entry_req_t *)));
    for (long i = 0; i < msg->n_entries; i++) {
        msg->entries[i] = raft_entry_new(DATA_LEN);
        auto *p = (raft_entry_req_t *) ((char *) &data.front() + sizeof(*msg) +
                                        (sizeof(raft_entry_req_t) + DATA_LEN) * i);
        int type = p->type;
        int id = p->id;
        raft_term_t term = p->term;
        *(msg->entries[i]) = *p;
        msg->entries[i]->type = type;
        msg->entries[i]->id = id;
        msg->entries[i]->term = term;
        memcpy(msg->entries[i]->data, p->data, DATA_LEN);
    }
    return msg;
}

static void free_deserialization_ae(raft_appendentries_req_t *msg) {
    raft_entry_release_list(msg->entries, msg->n_entries);
    raft_free(msg);
}

static int on_send_requestvote(raft_server_t *, void *, raft_node_t *node, raft_requestvote_req_t *msg) {
    string data;
    data.resize(sizeof(*msg));
    *(raft_requestvote_req_t *) &data.front() = *msg;
    data = pack_msg(data, MSG_RV);
    return net->send_to(raft_node_get_id(node), data) == (ssize_t) data.size() ? 0 : -1;
}

static int on_send_appendentries(raft_server_t *, void *, raft_node_t *node, raft_appendentries_req_t *msg) {
    string data = pack_msg(serialization_ae(msg), MSG_AE);
    return net->send_to(raft_node_get_id(node), data) == (ssize_t) data.size() ? 0 : -1;
}

struct SnapWire {
    raft_term_t term;
    raft_node_id_t leader;
    raft_index_t snap_idx;
    raft_term_t snap_term;
    char config[8];
};

static int on_send_snapshot(raft_server_t *, void *, raft_node_t *node, raft_snapshot_req_t *msg) {
    SnapWire wire{};
    wire.term = msg->term;
    wire.leader = msg->leader_id;
    wire.snap_idx = msg->snapshot_index;
    wire.snap_term = msg->snapshot_term;
    if (msg->chunk.data && msg->chunk.len > 0) {
        size_t n = min((size_t) msg->chunk.len, sizeof(wire.config) - 1);
        memcpy(wire.config, msg->chunk.data, n);
    }
    string data;
    data.resize(sizeof(wire));
    *(SnapWire *) &data.front() = wire;
    data = pack_msg(data, MSG_SNAP);
    return net->send_to(raft_node_get_id(node), data) == (ssize_t) data.size() ? 0 : -1;
}

static int on_get_snapshot_chunk(raft_server_t *, void *, raft_node_t *, raft_size_t offset, raft_snapshot_chunk_t *chunk) {
    snap_hold = config_text(disk.config);
    chunk->offset = offset;
    chunk->data = snap_hold.empty() ? nullptr : &snap_hold.front();
    chunk->len = snap_hold.size();
    chunk->last_chunk = 1;
    return 0;
}

static int on_store_snapshot_chunk(raft_server_t *, void *, raft_index_t, raft_size_t, raft_snapshot_chunk_t *chunk) {
    if (chunk->data && chunk->len > 0) {
        snap_hold.assign(static_cast<char *>(chunk->data), strnlen(static_cast<char *>(chunk->data), chunk->len));
    }
    return 0;
}

static int on_load_snapshot(raft_server_t *raft, void *, raft_term_t snapshot_term, raft_index_t snapshot_index) {
    int e = raft_begin_load_snapshot(raft, snapshot_term, snapshot_index);
    if (e != 0) {
        return e;
    }
    disk.loading = true;
    disk.pending_idx = snapshot_index;
    disk.pending_term = snapshot_term;
    disk.log_offset = raft_log_get_base(static_cast<raft_log_t *>(raft_get_log(raft)));
    disk.voting_cfg = 0;
    raft->voting_cfg_change_log_idx = -1;
    if (!snap_hold.empty()) {
        disk.config = parse_config(snap_hold);
    }
    return 0;
}

static int on_clear_snapshot(raft_server_t *, void *) {
    return 0;
}

static int on_applylog(raft_server_t *, void *, raft_entry_t *entry, raft_index_t) {
    if (entry->type == RAFT_LOGTYPE_NORMAL && entry->data) {
        state_machine += string(" ") + bytes_of(entry);
    }
    return 0;
}

static int on_persist_metadata(raft_server_t *, void *, raft_term_t term, raft_node_id_t vote) {
    if (!replaying) {
        disk.term = term;
        disk.vote = vote;
    }
    return 0;
}

static raft_node_id_t on_get_node_id(raft_server_t *, void *, raft_entry_t *entry, raft_index_t) {
    return entry->id;
}

static int on_sufficient_logs(raft_server_t *, void *, raft_node_t *) {
    return 0;
}

static raft_time_t on_timestamp(raft_server_t *, void *) {
    struct timeval curr;
    if (gettimeofday(&curr, nullptr) == -1) {
        throw_syserror("gettimeofday");
    }
    return curr.tv_sec * 1000000 + curr.tv_usec;
}

static void print_raft_log(raft_server_t *, void *, const char *buf) {
    cerr_detail << buf << endl;
}

static int raft_send_appendentries_resp(const Node &node, const raft_appendentries_resp_t &msg) {
    string data;
    data.resize(sizeof(msg));
    *(raft_appendentries_resp_t *) &data.front() = msg;
    data = pack_msg(data, MSG_AER);
    return net->send_to(node, data) == (ssize_t) data.size() ? 0 : -1;
}

static int raft_send_requestvote_resp(const Node &node, const raft_requestvote_resp_t &msg) {
    string data;
    data.resize(sizeof(msg));
    *(raft_requestvote_resp_t *) &data.front() = msg;
    data = pack_msg(data, MSG_RVR);
    return net->send_to(node, data) == (ssize_t) data.size() ? 0 : -1;
}

static raft_cbs_t raft_cbs = {
    .send_requestvote = on_send_requestvote,
    .send_appendentries = on_send_appendentries,
    .send_snapshot = on_send_snapshot,
    .send_timeoutnow = nullptr,
    .load_snapshot = on_load_snapshot,
    .get_snapshot_chunk = on_get_snapshot_chunk,
    .store_snapshot_chunk = on_store_snapshot_chunk,
    .clear_snapshot = on_clear_snapshot,
    .applylog = on_applylog,
    .persist_metadata = on_persist_metadata,
    .get_node_id = on_get_node_id,
    .node_has_sufficient_logs = on_sufficient_logs,
    .timestamp = on_timestamp,
    .notify_membership_event = nullptr,
    .notify_state_event = nullptr,
    .notify_transfer_event = nullptr,
    .log = print_raft_log,
    .backpressure = nullptr,
    .get_entries_to_send = nullptr
};

static void add_configured_nodes(raft_server_t *me) {
    for (auto &i : config.get_all_nodes()) {
        Node &n = const_cast<Node &>(i);
        int voting = disk.config.count(n.getid()) ? 1 : 0;
        raft_node_t *added = raft_add_node(me, nullptr, n.getid(), n.getid() == config.get_self_node().getid());
        n.set_data(added);
        if (added) {
            raft_node_set_voting(added, voting);
            raft_node_set_active(added, voting);
        }
    }
}

static void reset_volatile(raft_server_t *me) {
    me->commit_idx = 0;
    me->last_applied_idx = 0;
    me->last_applied_term = 0;
    raft_set_state(me, RAFT_STATE_FOLLOWER);
    me->leader_id = RAFT_NODE_ID_NONE;
    me->voting_cfg_change_log_idx = -1;
    disk.voting_cfg = 0;
    disk.loading = false;
    disk.pending_idx = 0;
    disk.pending_term = 0;
    for (int i = 0; i < me->num_nodes; i++) {
        raft_node_set_next_idx(me->nodes[i], 1);
        raft_node_set_match_idx(me->nodes[i], 0);
        raft_node_set_voted_for_me(me->nodes[i], 0);
    }
    publish_commit(me);
}

static bool rebuild_from_disk() {
    arm_step();
    raft_server_t *me = raft_new();
    if (!me) {
        return false;
    }
    raft_set_callbacks(me, &raft_cbs, nullptr);
    raft_config(me, 1, RAFT_CONFIG_AUTO_FLUSH, 0);
    raft_config(me, 1, RAFT_CONFIG_ELECTION_TIMEOUT, 1000000);
    if (disk.snap_idx > 0) {
        raft_log_load_from_snapshot(static_cast<raft_log_t *>(raft_get_log(me)), disk.snap_idx, disk.snap_term);
        if (raft_restore_snapshot(me, disk.snap_term, disk.snap_idx) != 0) {
            raft_destroy(me);
            return false;
        }
    }
    attach_log(me);
    add_configured_nodes(me);
    raft_restore_metadata(me, disk.term, disk.vote);
    replaying = true;
    for (const DiskEntry &saved : disk.log) {
        raft_entry_t *ety = raft_entry_new(DATA_LEN);
        ety->term = saved.term;
        ety->type = saved.type;
        ety->id = saved.id;
        if (!saved.data.empty()) {
            size_t n = saved.data.size();
        if (n > DATA_LEN - 1) {
            n = DATA_LEN - 1;
        }
        memcpy(ety->data, saved.data.c_str(), n);
        }
        int e = raft_append_entry(me, ety);
        raft_entry_release(ety);
        if (e != 0) {
            replaying = false;
            raft_destroy(me);
            return false;
        }
    }
    replaying = false;
    reset_volatile(me);
    config.set_raft_server(me);
    server_down = false;
    return true;
}

bool RaftInit() {
    arm_step();
    disk = Disk();
    server_down = false;
    replaying = false;
    for (auto &i : config.get_all_nodes()) {
        disk.config.insert(const_cast<Node &>(i).getid());
    }
    write_flags(0, 0);
    if (!rebuild_from_disk()) {
        return false;
    }
    if (FLAGS_detail) {
        raft_config(me_of(), 1, RAFT_CONFIG_LOG_ENABLED, 1);
    }
    cerr_verbose << "Raft init, self id: " << config.get_self_node().getid() << endl;
    return true;
}

bool RaftRecvMsg(Node node) {
    arm_step();
    if (server_down || !config.get_node(node)) {
        cerr_warning << "RaftRecvMsg cannot find node" << endl;
        return false;
    }
    string data;
    if (net->recv_from(node, data) < 0) {
        return false;
    }
    int type;
    string msg = unpack_msg(data, type);
    raft_server_t *me = me_of();
    raft_index_t old_commit = me->commit_idx;
    auto *raft_node = static_cast<raft_node_t *>(node.get_data());
    int rc = 0;
    switch (type) {
        case MSG_AE: {
            raft_appendentries_req_t *req = deserialization_ae(msg);
            raft_appendentries_resp_t resp{};
            rc = raft_recv_appendentries(me, raft_node, req, &resp);
            free_deserialization_ae(req);
            if (rc == 0) {
                raft_send_appendentries_resp(node, resp);
            }
            break;
        }
        case MSG_AER: {
            rc = raft_recv_appendentries_response(me, raft_node,
                                                  reinterpret_cast<raft_appendentries_resp_t *>(&msg.front()));
            break;
        }
        case MSG_RV: {
            auto *req = reinterpret_cast<raft_requestvote_req_t *>(&msg.front());
            raft_requestvote_resp_t resp{};
            rc = raft_recv_requestvote(me, raft_node, req, &resp);
            if (rc == 0) {
                raft_send_requestvote_resp(node, resp);
            }
            break;
        }
        case MSG_RVR: {
            rc = raft_recv_requestvote_response(me, raft_node,
                                                reinterpret_cast<raft_requestvote_resp_t *>(&msg.front()));
            break;
        }
        case MSG_SNAP: {
            SnapWire wire = *(SnapWire *) &msg.front();
            raft_snapshot_req_t req{};
            req.term = wire.term;
            req.leader_id = wire.leader;
            req.snapshot_index = wire.snap_idx;
            req.snapshot_term = wire.snap_term;
            req.chunk.last_chunk = 1;
            req.chunk.offset = 0;
            snap_hold = wire.config;
            req.chunk.data = snap_hold.empty() ? nullptr : &snap_hold.front();
            req.chunk.len = snap_hold.size();
            raft_snapshot_resp_t resp{};
            rc = raft_recv_snapshot(me, raft_node, &req, &resp);
            break;
        }
        default:
            return false;
    }
    if (rc != 0) {
        cerr_warning << "RaftRecvMsg library error " << rc << endl;
        return false;
    }
    note_commits(me, old_commit);
    return true;
}

static bool RaftElection() {
    arm_step();
    raft_server_t *me = me_of();
    int e = raft_election_start(me, 1);
    if (e != 0) {
        return false;
    }
    raft_node_set_voted_for_me(raft_get_my_node(me), 1);
    publish_commit(me);
    return true;
}

static bool RaftBecomeLeader() {
    arm_step();
    raft_server_t *me = me_of();
    int e = raft_become_leader(me);
    if (e != 0) {
        return false;
    }
    raft_node_set_next_idx(raft_get_my_node(me), raft_get_current_idx(me) + 1);
    publish_commit(me);
    return true;
}

static bool RaftAppendTo(const string &peer) {
    arm_step();
    Node node(peer);
    if (!config.get_node(node) || !node.get_data()) {
        return false;
    }
    return raft_send_appendentries(me_of(), static_cast<raft_node_t *>(node.get_data())) == 0;
}

static bool RaftClient(const string &data) {
    arm_step();
    raft_server_t *me = me_of();
    raft_entry_t *ety = raft_entry_new(DATA_LEN);
    ety->type = RAFT_LOGTYPE_NORMAL;
    string payload = data.empty() ? "v" : data;
    if (payload.size() > DATA_LEN - 1) {
        payload.resize(DATA_LEN - 1);
    }
    memcpy(ety->data, payload.c_str(), payload.size());
    raft_entry_resp_t resp{};
    int e = raft_recv_entry(me, ety, &resp);
    raft_entry_release(ety);
    if (e != 0) {
        return false;
    }
    raft_node_set_match_idx(raft_get_my_node(me), raft_get_current_idx(me));
    recompute_voting(me);
    publish_commit(me);
    return true;
}

static bool RaftConfigChange(bool add, int target) {
    arm_step();
    raft_server_t *me = me_of();
    set<int> cfg = effective_config(me);
    if (add) {
        cfg.insert(target);
    } else {
        cfg.erase(target);
    }
    string text = config_text(cfg);
    raft_entry_t *ety = raft_entry_new(DATA_LEN);
    ety->type = add ? RAFT_LOGTYPE_ADD_NODE : RAFT_LOGTYPE_REMOVE_NODE;
    ety->id = target;
    size_t n = text.size();
    if (n > DATA_LEN - 1) {
        n = DATA_LEN - 1;
    }
    memcpy(ety->data, text.c_str(), n);
    raft_entry_resp_t resp{};
    int e = raft_recv_entry(me, ety, &resp);
    raft_entry_release(ety);
    if (e != 0) {
        cerr_warning << "config change failed " << e << endl;
        return false;
    }
    raft_node_set_match_idx(raft_get_my_node(me), raft_get_current_idx(me));
    recompute_voting(me);
    publish_commit(me);
    return true;
}

static bool RaftAdvance() {
    arm_step();
    raft_server_t *me = me_of();
    if (!raft_is_leader(me)) {
        return false;
    }
    set<int> cfg = effective_config(me);
    if (cfg.empty()) {
        return false;
    }
    raft_index_t last = raft_get_current_idx(me);
    raft_index_t best = me->commit_idx;
    for (raft_index_t n = me->commit_idx + 1; n <= last; n++) {
        if (term_at(me, n) != me->current_term) {
            continue;
        }
        int agree = 0;
        for (int id : cfg) {
            raft_node_t *node = raft_get_node(me, id);
            if (node && raft_node_get_match_idx(node) >= n) {
                agree++;
            }
        }
        if (agree * 2 > (int) cfg.size()) {
            best = n;
        }
    }
    if (best == me->commit_idx) {
        return false;
    }
    raft_index_t old = me->commit_idx;
    raft_set_commit_idx(me, best);
    note_commits(me, old);
    return true;
}

static bool RaftSnapshot() {
    arm_step();
    raft_server_t *me = me_of();
    if (raft_begin_snapshot(me) != 0) {
        return false;
    }
    if (raft_end_snapshot(me) != 0) {
        return false;
    }
    disk.snap_idx = me->snapshot_last_idx;
    disk.snap_term = me->snapshot_last_term;
    disk.log_offset = raft_log_get_base(static_cast<raft_log_t *>(raft_get_log(me)));
    publish_commit(me);
    return true;
}

static bool RaftSendSnapshot(const string &peer) {
    arm_step();
    Node node(peer);
    if (!config.get_node(node) || !node.get_data()) {
        return false;
    }
    return raft_send_snapshot(me_of(), static_cast<raft_node_t *>(node.get_data())) == 0;
}

static bool RaftEndLoad() {
    arm_step();
    raft_server_t *me = me_of();
    if (raft_end_load_snapshot(me) != 0) {
        return false;
    }
    disk.loading = false;
    disk.snap_idx = me->snapshot_last_idx;
    disk.snap_term = me->snapshot_last_term;
    publish_commit(me);
    return true;
}

static bool RaftRead() {
    arm_step();
    raft_server_t *me = me_of();
    if (!raft_is_leader(me)) {
        return false;
    }
    int stale = 0;
    int noop = 0;
    read_flags(stale, noop);
    for (int id : disk.config) {
        if (id == raft_get_nodeid(me)) {
            continue;
        }
        if (published_commit(id) > (long) me->commit_idx) {
            stale = 1;
        }
    }
    for (auto &i : config.get_all_nodes()) {
        int id = const_cast<Node &>(i).getid();
        if (id != raft_get_nodeid(me) && published_commit(id) > (long) me->commit_idx) {
            stale = 1;
        }
    }
    if (!current_term_committed(me)) {
        noop = 1;
    }
    write_flags(stale, noop);
    return true;
}

static string vote_text(int vote) {
    if (vote < 0) {
        return "Nil";
    }
    return node_name_of(vote);
}

static bool RaftCrash() {
    arm_step();
    raft_server_t *me = me_of();
    if (!me) {
        return false;
    }
    cerr << "PERSIST term=" << disk.term
         << " vote=" << vote_text(disk.vote)
         << " snap=" << disk.snap_idx << ":" << disk.snap_term
         << " offset=" << disk.log_offset
         << " log=" << format_entries(disk.log)
         << " config=" << format_config(disk.config) << endl;
    raft_destroy(me);
    config.set_raft_server(nullptr);
    server_down = true;
    return true;
}

static bool RaftRecover() {
    if (!server_down) {
        return false;
    }
    return rebuild_from_disk();
}

bool RaftRepl(const string &cmd) {
    arm_step();
    auto tokens = tokenize(cmd);
    if (tokens.empty()) {
        return false;
    }
    if (server_down && tokens[0] != "recover") {
        cerr_warning << "server is down" << endl;
        return false;
    }
    if (tokens[0] == "init") {
        return RaftInit();
    } else if (tokens[0] == "recvfrom") {
        return RaftRecvMsg(tokens[1]);
    } else if (tokens[0] == "election") {
        return RaftElection();
    } else if (tokens[0] == "become-leader") {
        return RaftBecomeLeader();
    } else if (tokens[0] == "appendentries") {
        return tokens.size() > 1 && RaftAppendTo(tokens[1]);
    } else if (tokens[0] == "cli") {
        return tokens.size() > 1 && RaftClient(tokens[1]);
    } else if (tokens[0] == "add") {
        return tokens.size() > 1 && RaftConfigChange(true, id_of(tokens[1]));
    } else if (tokens[0] == "remove") {
        return tokens.size() > 1 && RaftConfigChange(false, id_of(tokens[1]));
    } else if (tokens[0] == "advance-commit") {
        return RaftAdvance();
    } else if (tokens[0] == "snapshot") {
        return RaftSnapshot();
    } else if (tokens[0] == "snapshot-send") {
        return tokens.size() > 1 && RaftSendSnapshot(tokens[1]);
    } else if (tokens[0] == "end-load") {
        return RaftEndLoad();
    } else if (tokens[0] == "read") {
        return RaftRead();
    } else if (tokens[0] == "crash") {
        return RaftCrash();
    } else if (tokens[0] == "recover") {
        return RaftRecover();
    } else if (tokens[0] == "statemachine") {
        cerr << state_machine << endl;
        return true;
    }
    return false;
}

static string live_log(raft_server_t *me) {
    auto *log = static_cast<raft_log_t *>(raft_get_log(me));
    raft_index_t base = raft_log_get_base(log);
    raft_index_t count = raft_log_count(log);
    vector<DiskEntry> entries;
    for (raft_index_t i = 1; i <= count; i++) {
        raft_entry_t *ety = raft_log_get_at_idx(log, base + i);
        if (!ety) {
            continue;
        }
        DiskEntry copy;
        copy.term = ety->term;
        copy.type = ety->type;
        copy.id = ety->id;
        copy.data = bytes_of(ety);
        entries.push_back(copy);
    }
    return format_entries(entries);
}

static string index_map(raft_server_t *me, bool next_idx) {
    vector<string> tokens;
    for (auto &i : config.get_all_nodes()) {
        Node node = i;
        if (!config.get_node(node) || !node.get_data()) {
            continue;
        }
        auto *n = static_cast<raft_node_t *>(node.get_data());
        long value = next_idx ? raft_node_get_next_idx(n) : raft_node_get_match_idx(n);
        tokens.push_back("'" + node.name + "': " + to_string(value));
    }
    sort(tokens.begin(), tokens.end());
    return "{" + stringify(tokens, 0, ", ") + "}";
}

static string votes_text(raft_server_t *me) {
    vector<string> names;
    for (int i = 0; i < me->num_nodes; i++) {
        if (raft_node_has_vote_for_me(me->nodes[i])) {
            names.push_back(node_name_of(raft_node_get_id(me->nodes[i])));
        }
    }
    sort(names.begin(), names.end());
    string text = "{";
    for (size_t i = 0; i < names.size(); i++) {
        if (i) {
            text += ",";
        }
        text += names[i];
    }
    text += "}";
    return text;
}

string RaftGet(const string &variable) {
    arm_step();
    if (variable == "staleRead" || variable == "noopRead") {
        int stale = 0;
        int noop = 0;
        read_flags(stale, noop);
        return variable == "staleRead" ? to_string(stale) : to_string(noop);
    }
    raft_server_t *me = me_of();
    if (!me || server_down) {
        return "down";
    }
    if (variable == "commitIdx") {
        publish_commit(me);
        return to_string(me->commit_idx);
    } else if (variable == "currentTerm") {
        return to_string(me->current_term);
    } else if (variable == "votedFor") {
        return vote_text(raft_get_voted_for(me));
    } else if (variable == "log") {
        return live_log(me);
    } else if (variable == "logOffset") {
        return to_string(raft_log_get_base(static_cast<raft_log_t *>(raft_get_log(me))));
    } else if (variable == "state") {
        return to_string(me->state);
    } else if (variable == "nextIdx") {
        return index_map(me, true);
    } else if (variable == "matchIdx") {
        return index_map(me, false);
    } else if (variable == "votesGranted") {
        return votes_text(me);
    } else if (variable == "snapshotLastIdx") {
        return to_string(me->snapshot_last_idx);
    } else if (variable == "snapshotLastTerm") {
        return to_string(me->snapshot_last_term);
    } else if (variable == "loadingSnapshot") {
        return disk.loading ? "1" : "0";
    } else if (variable == "pendingSnapshotIdx") {
        return to_string(disk.pending_idx);
    } else if (variable == "pendingSnapshotTerm") {
        return to_string(disk.pending_term);
    } else if (variable == "clusterConfig") {
        return format_config(disk.config);
    } else if (variable == "votingCfgChangeIdx") {
        return to_string(disk.voting_cfg);
    }
    return "";
}

/* A weak reference is not enough: Ubuntu's --as-needed drops libgcov, the
 * symbol stays null, and _exit then writes no .gcda. The coverage binary
 * defines SPECULA_COVERAGE and keeps a real reference. The sanitizer binary
 * does not link libgcov, so the call stays a no-op. */
#if defined(SPECULA_COVERAGE)
extern "C" void __gcov_dump(void);
extern "C" void wraft_gcov_dump(void) { __gcov_dump(); }
#else
extern "C" void __gcov_dump(void) __attribute__((weak));
extern "C" void wraft_gcov_dump(void) {
    if (__gcov_dump) {
        __gcov_dump();
    }
}
#endif
