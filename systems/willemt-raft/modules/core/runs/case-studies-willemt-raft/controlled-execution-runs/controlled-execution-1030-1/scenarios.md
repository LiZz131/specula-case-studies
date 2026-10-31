# 交回 Specula 的场景

这些行的下一步不是在现有 Sand* 上加样本。不改 `spec/base.tla` 和 `spec/MC.tla`，也不在 `Sand*` 里补协议。

## 成员变更

集合 E。库在 `raft_offer_log`、`raft_pop_log`、`raft_apply_entry` 的配置条目分支里增减节点、升降投票权。`raft_add_non_voting_node` 和 `raft_node_set_voting` 做同样的事。`raft_recv_entry` 会记下 `voting_cfg_change_log_idx`，`raft_recv_appendentries_response` 在非投票节点的日志追上时调用 `node_has_sufficient_logs`。`__should_grant_vote` 对非投票节点直接拒绝。`raft_recv_requestvote` 对已经不在集群里的候选人返回 `UNKNOWN_NODE`。

守卫是条目类型为配置变更，或节点没有投票权。规格里的 `Value` 只有普通值，`Server` 三个都投票，没有加入、退出、降权这些动作。现有的 `ClientRequest` 产生不了配置条目。

## 撤销快照

集合 A，对不上已有动作。`raft_cancel_snapshot`（`raft_server.c:1300-1301`）把 `snapshot_last_idx` 和 `snapshot_last_term` 恢复成开始快照时保存的值，并清掉进行中标记。驱动不调用这个函数。`SandTakeSnapshot` 和装载快照都没有撤销。规格里没有这条赋值。
