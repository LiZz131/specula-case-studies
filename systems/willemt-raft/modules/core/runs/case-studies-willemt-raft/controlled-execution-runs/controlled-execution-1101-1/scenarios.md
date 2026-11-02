# 交回 spec_generation 的场景

本轮是 `controlled-execution-1101-1`。下面的场景来自并集覆盖里对不上现有动作的 A，以及全部 E。不在 `Sand*` 里补协议。`spec/base.tla` 和 `spec/MC.tla` 保持不动。

## 成员变更

123 行，集合 E。

库在四类日志上改节点表：`ADD_NODE`、`ADD_NONVOTING_NODE`、`DEMOTE_NODE`、`REMOVE_NODE`。相关字段是节点是否有投票权、`VOTING_COMMITTED`、`ADDITION_COMMITTED`、`HAS_SUFFICIENT_LOG`，以及 `voting_cfg_change_log_idx`。写入发生在 `raft_offer_log`、`raft_pop_log`、`raft_apply_entry` 的配置分支、`raft_add_node_internal`、`raft_add_non_voting_node`、`raft_remove_node`。

守卫是：日志条目的类型是上面四种之一；或者已经有一次成员变更还没结束时，再来一条客户端请求。

`base.tla` 的 `Value` 只有普通值 `v1`。`ClientRequest` 只追加普通日志，没有配置变更条目，也没有节点表。现有动作产生不了这些行。

## Apply

20 行集合 A，外加 `raft_periodic` 里调用 apply 的那一行。

`raft_apply_entry` 在 `lastApplied < commitIndex` 且没有进行中的快照时，把 `lastApplied` 加 1，并对那条日志调用 `applylog`。`raft_apply_all` 一直循环到两者相等。`raft_periodic` 在同守卫下会调用它。

`base.tla` 没有 Apply。`TakeSnapshot` 保持 `lastApplied` 不变。本轮为了和这条公式一致，`raft_begin_snapshot` 不再调用 `raft_apply_all`。这 702 条轨迹里，`Timeout` 发生时提交点还没有超过 `lastApplied`，所以 periodic 里的 apply 也没执行。

要覆盖这些行，规格需要一条把 `lastApplied` 推进到 `commitIndex` 的动作。普通条目不改任期、投票和日志。

## 单节点直接当选并提交

`raft_server.c:232` 在投票节点数等于 1 且自己不是领导者时调用 `raft_become_leader`，把 `state` 写成 Leader。`Timeout` 的赋值是变成 Candidate 并发出 RequestVote，不是这一条。

`raft_server.c:769` 在投票节点数等于 1 时，把刚追加的客户端条目的 `commitIndex` 写成当前日志末尾。三节点上的 `ClientRequest` 不提交。

当前每个配置都是 `Server = {s1,s2,s3}`，这两条守卫为假。另开 `|Server| = 1` 才能走到。走到之后还要有上面这两条赋值，现有动作里没有。

## 取消快照

`raft_cancel_snapshot` 在快照进行中时，把 `snapshotLastIdx` 和 `snapshotLastTerm` 恢复成进入快照之前保存的值，并清掉进行中标志。`TakeSnapshot` 只把快照点向前写，没有取消。

## 失败响应后的重发

`raft_recv_appendentries_response` 在失败分支末尾调用 `raft_send_appendentries`。`HandleAppendEntriesResponse` 的失败分支是 `Discard`，不重发。这两行不改 spec 变量，分类是 B。规格若要和库一致，失败响应之后还要有一次发送；若保持 `Discard`，回放必须继续把这次发送压掉。
