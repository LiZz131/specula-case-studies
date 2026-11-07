# sublog-at-snapshot

规格问题。`next_idx` 落在快照基址上时，`log_get_from_idx` 返回 0 条。公式把快照之后的整段日志都放进 AppendEntries。这条轨迹里库发出 56 字节的空报文，公式里的 seq 23 带了两条日志。

| 配置 | 轨迹 | 种子 | 步 | 变量 | 代码值 | 模型值 |
|---|---|---|---|---|---|---|
| hunt_snapshot | t0031 | 31 | 29 | commitIdx / n2 | 空（进程已退出） | 2 |

位置：`raft_log.c` 177–180 行。`n3` 的快照下标是 1，发给 `n2` 的 `next_idx` 也是 1。

同一条报文还让空日志的跟随者在 `raft_set_commit_idx` 断言处退出。那是协议问题，记在 `potential-bugs/empty-ae-commit-assert/`。这里只改公式少发的那部分：下标不大于快照基址时，`SubLog` 为空。

修改记在 `controlled-execution-runs/controlled-execution-1103-9/spec-repairs.md`。重新插桩后的轮次是 `controlled-execution-1103-10`。

复现：`run_one_testcase.sh potential-bugs/sublog-at-snapshot/t0031/MC.out 3`。失败步是 `# [29] HandleAppendEntriesRequest s2 s3 23`。按源码，seq 23 不应带上快照之后的日志。
