# 规格对齐

## standard / t0010 / 种子 10 / 步 24

- 变量 `lastApplied`，节点 `n2`（模型 `s2`）
- 代码值 `1`，模型值 `0`
- `pc`：`Timeout s2`

原公式的 `Timeout` 不改变 `lastApplied`。

`<ce>/system/src/raft_server.c` 的 `raft_periodic` 在选举处理之后、返回之前（253–259 行）调用 `raft_apply_all`。`raft_apply_entry`（812–832 行）只应用下一条仍在日志里、且不超过 `commit_idx` 的条目。快照进行中时 `raft_is_apply_allowed` 为假；本轮的快照在一次调用里结束，拨钟时没有这个标志。

改后的公式：`Timeout` 和同样调用 `raft_periodic` 的 `BroadcastAppendEntries` 都把 `lastApplied` 推进到从当前值起、连续存在于日志中、且不超过 `commitIndex` 的最大下标。
