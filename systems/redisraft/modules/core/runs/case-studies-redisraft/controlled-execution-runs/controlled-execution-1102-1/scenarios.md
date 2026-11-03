# 交给 spec_generation 的场景

本轮 500 条轨迹都在下面两条公式差上停住。后面的已有动作（AppendEntries、提交、快照、成员变更、非法定人数读）没有在库上执行。这些动作的赋值已经在 `spec/base.tla` 里，对得上库里的函数。要先改这两条公式，再回到 `sandtable-replay`。本轮不改 `spec/base.tla`。

## BecomeLeader 不要给自己写 nextIndex

`BecomeLeader`（`spec/base.tla` 339–340 行）在 `j = i` 时把 `nextIndex[i][i]` 写成 `newLastIdx + 1`。`raft_become_leader`（`system/src/raft_server.c` 497–506 行）遇到自己就 `continue`，自己的 `next_idx` 留在初始的 1。跟随者写成当前最后下标，和公式的 `ELSE newLastIdx` 一致。

领导者不给自己发 AppendEntries。协议不要求维护一条指向自己的 nextIndex。482 条轨迹的代码值在行动者自己那一项上是 1，模型值是 `newLastIdx + 1`，其余节点相等。记录在 `potential-bugs/nextindex-self/`。

要改的公式：`BecomeLeader` 不给 `nextIndex[i][i]` 赋 `newLastIdx + 1`，自己的项保持不变。

## HandleRequestVoteResponse 的非候选人分支要带上任期

`HandleRequestVoteResponse`（`spec/base.tla` 302–305 行）在 `state[i] /= Candidate` 时丢弃响应并且任期不变。更高任期的那条（293–300 行）同时可以成立。TLC 选了任期不变的那条。

`raft_recv_requestvote_response`（`system/src/raft_server.c` 1152–1159 行）先看 `resp->term > current_term`，改任期并转成 Follower，然后返回。协议要求 RPC 响应里的更高任期更新 `currentTerm`。18 条轨迹的步前消息 `mterm` 等于代码后来的 `currentTerm`，大于模型留下的任期。接收者当时不是 Candidate。记录在 `potential-bugs/vote-response-term/`。

要改的公式：不是候选人就丢弃的那条加上 `m.mterm <= currentTerm[i]`。

## 现有动作执行不到

上面两条改完之前，下面这些已经写在规格里的赋值执行不到。行分类里它们是 A，下一步指回这里，不是再加本轮的 30 步种子。

- `HandleAppendEntriesRequest` / `HandleAppendEntriesResponse` / `AppendEntries`：日志、提交点、`nextIndex`、`matchIndex`。
- `AdvanceCommitIndex`：`raft_update_commit_idx` 按投票节点 `matchIndex` 的中位数抬高 `commitIndex`。
- `TakeSnapshot` 的结束、`HandleInstallSnapshotRequest`、`EndLoadSnapshot`：`snapshotLastIdx`、`snapshotLastTerm`、`logOffset`。
- `ClientRequest`、`ProposeAddServer`、`ProposeRemoveServer`：追加日志，并在配置条目上改投票权和 `votingCfgChangeIdx`。

## 规格里没有的路径

这些行不改写现有规格变量，或者写入的角色不在 `{Follower, Candidate, Leader}` 里。

**PreVote。** `raft_become_precandidate` 清掉 `votesGranted` 并把角色写成预候选人。`raft_election_start` 在 `skip_precandidate = 0` 时走进去。`raft_send_requestvote` 把预投票的消息任期写成 `currentTerm + 1`。驱动的 Timeout 调用 `raft_election_start(me, 1)`。规格的 Timeout 也没有预投票。要覆盖这些行，需要一条 PreVote 动作：不增加 `currentTerm`，角色离开 Follower / Candidate / Leader 这三种，向其他投票节点发任期为 `currentTerm + 1` 的投票请求。

**周期函数。** `raft_periodic` 不在规格的 `Next` 里。单节点分支把 `currentTerm` 加一并调用 `raft_become_leader`。三个投票节点时这条为假。规格的 Timeout 走 `raft_election_start`，单节点不会在这一步当选。另开一个投票节点之前，先决定周期函数算不算一条动作。

**读队列。** `raft_recv_read_request`、`raft_process_read_queue` 用 `msg_id` 把读请求放进库内队列。规格的 `ClientNonQuorumRead` 只改 `staleReadDetected` 和 `noopReadDetected`，没有这个队列。`staleread` 的 98 条在 TLC 里违反 `NoReadBeforeNoOp`，回放在当选后的 `nextIndex` 比较处已经停下，库的读函数没有执行。

**领导权转移。** `raft_transfer_leader`、`raft_timeout_now` 和 `node_transferring_leader_to`。规格没有 TimeoutNow，也没有转移目标。

**msg_id。** `quorum_msg_id`、节点上的 match / next / max_seen msgid。规格的消息和提交点不用 msg_id。

**成员标志。** 无投票权加入、`addition_committed`、`voting_committed`、`sufficient_logs`、`inactive`、快照字节偏移。规格的配置是 `clusterConfig` 和 `votingCfgChangeIdx`，快照是下标和任期。
