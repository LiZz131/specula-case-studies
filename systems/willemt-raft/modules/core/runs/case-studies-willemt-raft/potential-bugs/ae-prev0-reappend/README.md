# prev_log_idx 为 0 时把已压缩的条目再追加进日志

配置 `snapshot`，种子 104，深轨迹 `t0104`。失败步是日志里的 `# [44] HandleAppendEntriesRequest s3 s1 36`。同一类还有 `snapshot/t0187`（n2 的日志，代码 5 条、模型 2 条）。

不一致的变量是 n3 的 `log`。投递前两边都是 `[(2, 'v1'), (2, 'v1')]`。投递后代码是 5 条 `(2, 'v1')`，模型仍是 2 条。这条 AppendEntries 的 `mprevLogIdx` 是 0，`mentries` 是 3 条。n3 的 `snapshotLastIdx` 是 1，`snapshotLastTerm` 是 2。

库在 `raft_recv_appendentries`（`artifact/raft/src/raft_server.c`）。`prev_log_idx == 0` 时跳过 prev 检查。随后 `log_get_at_idx` 对小于等于快照基址的下标返回 NULL，循环在第一条就停下，把 3 条都 `raft_append_entry` 到日志末尾。

`SandHandleAppendEntriesRequest` 用 `LogTermAt`：下标等于 `snapshotLastIdx` 时任期就是 `snapshotLastTerm`。三条的任期都对得上，`newLog` 保持原来的 2 条。规格描述的是这条接收路径，回放仍得到更长的日志。这是 hunt 配置里的 MC-7。规格和源码都没有为这条记录改过。
