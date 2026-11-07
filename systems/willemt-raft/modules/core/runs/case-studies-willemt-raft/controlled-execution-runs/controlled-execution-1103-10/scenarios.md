# 交回 Specula 的场景

现有模型的服务器都投票，日志条目是 `(term, value)`，快照由 `TakeSnapshot` 一次做完。下面这些行因此走不到。

## 成员变更

库在日志类型为添加节点、添加非投票节点、降级、移除时改节点数组、投票资格、`VOTING_COMMITTED`、`ADDITION_COMMITTED`、`HAS_SUFFICIENT_LOG` 和 `voting_cfg_change_log_idx`。撤掉这些条目时做逆操作。`offer_log` 和 `raft_pop_log` 的配置变更分支也在这里。

现有 `Value` 只有普通客户端值，没有配置变更条目。现有动作不添加、移除或降级服务器。守卫是条目类型属于上述四种。相关行在 `raft_server.c` 的 `raft_offer_log`、`raft_pop_log`、`raft_apply_entry`、`raft_add_non_voting_node`、`raft_remove_node`，以及 `raft_node.c` 的投票资格标志。

## 取消快照

`raft_cancel_snapshot`（`raft_server.c` 1301–1302 行）把 `snapshotLastIdx` 和 `snapshotLastTerm` 写回开始快照之前的值。这是集合 A，现有动作里没有这条赋值。`TakeSnapshot` 调用 `raft_begin_snapshot` 后立刻 `raft_end_snapshot`，没有取消。模型也没有“快照进行中”这个字段，所以 1304 行清掉 `snapshot_in_progress` 放在集合 E。

## 非投票节点拒绝投票

`__should_grant_vote`（`raft_server.c` 539 行）在本机不是投票节点时直接拒绝。模型里 `Server` 的每个元素都投票，这条守卫为假。

## 环形下标和弹出回调

`mod`（`raft_log.c` 43、45 行）按环形缓冲取下标。模型的 `log` 是序列，没有 `front`、`back` 和容量。`log_delete` 在弹出时调用 `log_pop` 回调（237–240 行）。模型没有这个回调。日志内容本身的截断仍算集合 A，下一步是加长，不在这里。

## 快照进行中的非阻塞标志

`raft_is_apply_allowed`（`raft_server_properties.c` 240–241 行）在快照进行中时还要看 `RAFT_SNAPSHOT_NONBLOCKING_APPLY`。模型没有这两个字段。一次受控步在返回前已经结束快照，别的动作看不到进行中的快照。
