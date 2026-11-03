# 交回 Specula 的场景

这些行在 `行分类.tsv` 里是 E，或是 A 但现有动作写不出同一条赋值。不在 `Sand*` 里补协议。

## 预投票和周期检查

`raft_become_precandidate`、`raft_periodic`、`raft_periodic_internal`，以及 `raft_election_start` 在 prevote 为 0 时的那一臂。它们会改 `state` 和 `currentTerm`。规格里的 Timeout 直接调用 `raft_election_start(me, 1)`，没有 PreVote，也没有 `raft_periodic`。三个节点时单节点立即当选的那条也不在模型里。

## 恢复时重放日志

`raft_restore_log` 按快照之后的日志重写 `votingCfgChangeIdx` 和成员。规格里的 Crash 把易失状态清掉，不从日志重放这个下标。

## 读请求、转移领导和 msg_id

`raft_recv_read_request`、`raft_process_read_queue`、`pop_read_queue`、`quorum_msg_id`、`raft_transfer_leader`、`raft_timeout_now`、`raft_reset_transfer_leader`。规格没有读队列、msg_id 或转移领导。`ClientNonQuorumRead` 只比较 `staleReadDetected` 和 `noopReadDetected`。

## 非投票成员和原响应路径

`raft_add_non_voting_node`，以及 `raft_recv_appendentries_response` 里 msg_id、足够日志和自动 flush 的分支。`specula_step` 下 AppendEntries 响应走 `specula_recv_appendentries_response`。规格的 `clusterConfig` 只记投票成员。
