# 规格对齐

## hunt_snapshot / t0031 / 种子 31 / 步 29

- 变量 `commitIdx`，节点 `n2`
- 代码值空（进程已退出），模型值 `2`
- `pc`：`HandleAppendEntriesRequest s2 s3 23`

公式里的 seq 23 是 `mleaderCommit = 3`、两条日志。库实际发出的是 56 字节、没有条目。`n3` 的快照下标是 1，`n2` 的 `next_idx` 也是 1。

`log_get_from_idx`（`raft_log.c` 177–180 行）在下标不大于日志基址时返回 0 条。原 `SubLog` 在 `fromIdx <= snapshotLastIdx` 时返回快照之后的整段 `log`。

改后的 `SubLog`：下标已经越过本机最后一条，或下标不大于快照基址时，结果是空序列。

这条空报文还会让空日志的跟随者在 `raft_set_commit_idx` 断言处退出。那是协议问题，不在这次公式修改里改掉。记录在 `potential-bugs/empty-ae-commit-assert/t0031`。
