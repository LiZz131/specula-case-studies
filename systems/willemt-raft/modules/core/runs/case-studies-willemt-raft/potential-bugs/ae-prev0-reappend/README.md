# prev_log_idx 为 0 时把已压缩的条目再追加进日志

归类 `bug`。规格的 `SandHandleAppendEntriesRequest` 已经描述这条接收路径，回放的可见日志仍然更长。这是 case study 里的 MC-7，也是 willemt/raft PR #118 的 Bug 1，上游未修。2026-10-30 用 `t0104` 的 `MC.out` 再跑了一次，4.2 秒，失败行与下面相同。

| 轨迹 | 种子 | 步 | 复现 |
|---|---:|---|---|
| `t0104` | 104 | `# [44] HandleAppendEntriesRequest s3 s1 36` | `run_one_testcase.sh t0104/MC.out 3` |
| `t0187` | 187 | `# [35] HandleAppendEntriesRequest s2 s3 30` | `run_one_testcase.sh t0187/MC.out 3` |

命令在本目录执行，节点数是 3。期望看到 `Variable "log" compare failed`。

`t0104` 的变量是 n3 的 `log`。投递前两边都是 `[(2, 'v1'), (2, 'v1')]`。投递后代码是 5 条 `(2, 'v1')`，模型仍是 2 条。这条 AppendEntries 的 `mprevLogIdx` 是 0，`mprevLogTerm` 是 0，`mentries` 是 3 条 `(2, v1)`。n3 的 `snapshotLastIdx` 是 1，`snapshotLastTerm` 是 2。`t0187` 是同一条消息形状，不一致的是 n2 的 `log`，代码 5 条，模型 2 条。

库在 `artifact/raft/src/raft_server.c` 的 `raft_recv_appendentries`。`prev_log_idx == 0` 时 430 行的检查被跳过。随后 `log_get_at_idx`（`raft_log.c`）对小于等于快照基址的下标返回 NULL，472 行把 `success` 设成 1，499–508 行把 3 条都 `raft_append_entry` 到日志末尾。

`SandHandleAppendEntriesRequest` 用 `LogTermAt`：下标等于 `snapshotLastIdx` 时任期就是 `snapshotLastTerm`。三条的任期都对得上，`newLog` 保持原来的 2 条。规格和源码都没有为这条记录改过。
