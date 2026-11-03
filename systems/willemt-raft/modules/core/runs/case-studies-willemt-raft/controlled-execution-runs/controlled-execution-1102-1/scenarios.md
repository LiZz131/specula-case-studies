# 交回 spec_generation 的场景

这些行在八个配置、每份 100 条轨迹之后仍然是 0。现有 `base.tla` 动作对不上，或者模型里没有这些字段。

## 应用已提交日志

`raft_apply_entry` 和 `raft_apply_all` 在 `last_applied_idx < commit_idx` 时把 `lastApplied` 往前推进，并按条目类型改节点标志。`raft_periodic` 在选举超时处理之后调用它们。

`Timeout` 只作用于 Follower 和 Candidate，并且不改 `lastApplied`。`lastApplied` 只在 `HandleInstallSnapshot` 和 `Recover` 里被赋值。没有动作描述「提交点已经向前，下一次时钟把日志应用到状态机」。

要覆盖这 41 行，需要新的动作，而不是把 `DepthBound` 加大。`called 0 raft_apply_all`。

## 取消进行中的快照

`raft_cancel_snapshot` 在 `snapshot_in_progress` 为真时把 `snapshotLastIdx` 和 `snapshotLastTerm` 恢复成进入快照之前的值。规格只有 `TakeSnapshot`，没有取消。

## 领导者心跳

`raft_periodic` 在 `state = Leader` 且流逝时间达到 `request_timeout`（200 毫秒）时调用 `raft_send_appendentries_all`。`Timeout` 的守卫是非领导者。模型里的 AppendEntries 只来自 `SendAppendEntries` 和 `BroadcastAppendEntries`。

`called 0 raft_send_appendentries_all`。

## 成员变更

`raft_add_non_voting_node`、`raft_remove_node`、`raft_offer_log`、`raft_pop_log`，以及 `RAFT_LOGTYPE_ADD_NODE`、`ADD_NONVOTING_NODE`、`DEMOTE_NODE`、`REMOVE_NODE` 分支。

规格的 `Value` 只有 `v1` 这种普通条目，`Server` 固定是 `{s1, s2, s3}`。没有加入、退出或降级的动作，也没有非投票成员。这些行不能靠放宽 `MaxLogLength` 或 `DepthBound` 走到。
