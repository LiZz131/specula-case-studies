# prev_log_idx 为 0 时把已压缩的条目再追加进日志

两条轨迹的 `MC.out`、`traces.txt`、`log.host`、`replay.status`、`tlc.err`、`tlc.status` 都在本目录的子目录里。轮次里的 `traces/` 被 gitignore，GitHub 上以这里为准。

| 子目录 | 复现 |
|---|---|
| `snapshot-t0104/` | `run_one_testcase.sh snapshot-t0104/MC.out 3`。失败步 `# [44] HandleAppendEntriesRequest s3 s1 36`。n3 的 `log`：代码 5 条，模型 2 条。 |
| `snapshot-t0187/` | `run_one_testcase.sh snapshot-t0187/MC.out 3`。n2 的 `log`：代码 5 条，模型 2 条。 |

命令在本目录执行，节点数是 3。`snapshot-t0104` 的种子是 104。

不一致的变量是 n3 的 `log`。投递前两边都是 `[(2, 'v1'), (2, 'v1')]`。投递后代码是 5 条 `(2, 'v1')`，模型仍是 2 条。这条 AppendEntries 的 `mprevLogIdx` 是 0，`mentries` 是 3 条。n3 的 `snapshotLastIdx` 是 1，`snapshotLastTerm` 是 2。

库在 `raft_recv_appendentries`（`artifact/raft/src/raft_server.c`）。`prev_log_idx == 0` 时跳过 prev 检查。随后 `log_get_at_idx` 对小于等于快照基址的下标返回 NULL，循环在第一条就停下，把 3 条都 `raft_append_entry` 到日志末尾。

`SandHandleAppendEntriesRequest` 用 `LogTermAt`：下标等于 `snapshotLastIdx` 时任期就是 `snapshotLastTerm`。三条的任期都对得上，`newLog` 保持原来的 2 条。规格描述的是这条接收路径，回放仍得到更长的日志。这是 hunt 配置里的 MC-7。规格和源码都没有为这条记录改过。
