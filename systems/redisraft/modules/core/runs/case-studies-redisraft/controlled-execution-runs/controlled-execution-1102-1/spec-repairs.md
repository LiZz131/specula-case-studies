# 规格对齐

发现于 `controlled-execution-1102-1`。`<run>/spec/base.tla` 未改。对齐后的公式在本目录 `spec/base.tla`，回放在 `controlled-execution-1103-1`。对齐时只对照 `system/src/raft_server.c`。驱动没有改。

## BecomeLeader 的 nextIndex

| 项 | 内容 |
|---|---|
| 配置 / 轨迹 / 种子 | standard / t0001 / 1。同一种差共 482 条，见 `potential-bugs/nextindex-self/traces.tsv` |
| 步号 | `# [19] BecomeLeader s3` |
| 变量 | nextIndex |
| 代码值 | `{'n1': 1, 'n2': 1, 'n3': 1}` |
| 模型值 | `{'n1': 1, 'n2': 1, 'n3': 2}` |
| 原公式 | `j = i` 时 `nextIndex[i][j] = newLastIdx + 1`，否则 `newLastIdx`。注释指向 `raft_server.c` 476–487 行 |
| 源码 | `raft_become_leader`，`system/src/raft_server.c` 497–506 行。`me->node == node` 时 `continue`，不写自己的 `next_idx`。其余节点写成 `current_idx`，即新日志最后下标。482 行把自己的 `match_idx` 写成 `current_idx` |
| 改后 | `j = i` 时 `nextIndex[i][j]` 保持不变，否则写成 `newLastIdx`。`matchIndex` 不变 |

## HandleRequestVoteResponse 的任期

| 项 | 内容 |
|---|---|
| 配置 / 轨迹 / 种子 | standard / t0014 / 14。同一种差共 18 条，见 `potential-bugs/vote-response-term/traces.tsv` |
| 步号 | `# [16] HandleRequestVoteResponse s1 s2 12` |
| 变量 | currentTerm |
| 代码值 | 3 |
| 模型值 | 2 |
| 原公式 | `state[i] /= Candidate` 时丢弃响应且任期不变。这条和 `m.mterm > currentTerm[i]` 同时成立 |
| 源码 | `raft_recv_requestvote_response`，`system/src/raft_server.c` 1152–1159 行先在 `resp->term > current_term` 时写入该任期并转成 Follower。1168–1172 行「不是候选人就返回」只在任期没有更高时执行 |
| 改后 | 不是候选人就丢弃的那条加上 `m.mterm <= currentTerm[i]` |
