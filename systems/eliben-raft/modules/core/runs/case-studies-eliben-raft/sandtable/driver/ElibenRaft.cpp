#include "Raft.h"
#include "Config.h"
#include "Network.h"

#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

extern "C" {
void ElibenInit(int id, int npeers, int *peers);
int ElibenTimeout(void);
int ElibenHeartbeat(void);
int ElibenSubmit(const char *cmd);
int ElibenDeliver(int from, const char *data, int n);
int ElibenPop(int *dst, char *buf, int cap);
const char *ElibenGet(const char *key);
void ElibenDumpCover(void);
}

extern "C" void wraft_gcov_dump(void) { ElibenDumpCover(); }

static bool flush_sends() {
    char buf[65536];
    int dst = 0;
    while (true) {
        int n = ElibenPop(&dst, buf, static_cast<int>(sizeof(buf)));
        if (n == 0) {
            return true;
        }
        if (n < 0) {
            return false;
        }
        Node peer(dst);
        if (net->send_to(peer, string(buf, buf + n)) <= 0) {
            cerr_warning << "send_to " << peer.name << " failed" << endl;
            return false;
        }
    }
}

bool RaftInit() {
    Node self = config.get_self_node();
    vector<int> peers;
    for (Node node : config.get_all_nodes()) {
        if (node.getid() != self.getid()) {
            peers.push_back(node.getid());
        }
    }
    sort(peers.begin(), peers.end());
    if (peers.empty()) {
        cerr_warning << "RaftInit has no peers" << endl;
        return false;
    }
    ElibenInit(self.id, static_cast<int>(peers.size()), peers.data());
    return true;
}

bool RaftRecvMsg(Node node) {
    if (!config.get_node(node)) {
        cerr_warning << "RaftRecvMsg cannot find node" << endl;
        return false;
    }
    string data;
    if (net->recv_from(node, data) < 0) {
        return false;
    }
    if (ElibenDeliver(node.getid(), data.data(), static_cast<int>(data.size())) < 0) {
        return false;
    }
    return flush_sends();
}

// msec selects the command. eliben's own timers are not consulted:
// 2000 is Timeout, 200 is AppendEntriesAll, and the bare init periodic is a no-op.
bool RaftPeriodic(int msec = -1) {
    if (msec >= 1000) {
        if (ElibenTimeout() < 0) {
            return false;
        }
        return flush_sends();
    }
    if (msec > 0) {
        if (ElibenHeartbeat() < 0) {
            return false;
        }
        return flush_sends();
    }
    return true;
}

bool RaftClientOperation(string data) {
    if (ElibenSubmit(data.c_str()) < 0) {
        return false;
    }
    return flush_sends();
}

bool RaftRepl(const string &cmd) {
    auto tokens = tokenize(cmd);
    if (tokens.empty()) {
        return false;
    }
    if (tokens[0] == "init") {
        return RaftInit();
    } else if (tokens[0] == "recvfrom") {
        if (tokens.size() <= 1) {
            return false;
        }
        return RaftRecvMsg(Node(tokens[1]));
    } else if (tokens[0] == "periodic") {
        if (tokens.size() > 1) {
            return RaftPeriodic(std::stoi(tokens[1]));
        }
        return RaftPeriodic();
    } else if (tokens[0] == "cli") {
        if (tokens.size() <= 1) {
            return false;
        }
        return RaftClientOperation(tokens[1]);
    } else if (tokens[0] == "statemachine") {
        cerr << "init" << endl;
        return true;
    }
    return false;
}

string RaftGet(const string &variable) {
    char *text = const_cast<char *>(ElibenGet(variable.c_str()));
    if (text == nullptr) {
        return "";
    }
    string value(text);
    free(text);
    return value;
}
