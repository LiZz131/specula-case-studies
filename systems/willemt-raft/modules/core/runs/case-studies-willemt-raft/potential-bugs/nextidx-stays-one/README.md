# 失败的 AppendEntries 响应没有把 nextIndex 从 1 减到 0

三条轨迹的 `MC.out`、`traces.txt`、`log.host`、`replay.status`、`tlc.err`、`tlc.status` 都在本目录的子目录里。轮次里的 `traces/` 被 gitignore，GitHub 上以这里为准。

| 子目录 | 复现 |
|---|---|
| `snapshot-t0158/` | `run_one_testcase.sh snapshot-t0158/MC.out 3`。种子 158。失败步 `# [42] HandleAppendEntriesResponse s1 s2 40`。 |
| `snapshot-t0130/` | `run_one_testcase.sh snapshot-t0130/MC.out 3`。 |
| `log-t0169/` | `run_one_testcase.sh log-t0169/MC.out 3`。 |

三条都是代码的 `nextIdx` 停在 1，模型是 0。命令在本目录执行，节点数是 3。

n1 的 `nextIdx`。上一步两边都是 `{'n2': 1, 'n3': 2}`。这一步代码仍是 `{'n2': 1, 'n3': 2}`，模型是 `{'n2': 0, 'n3': 2}`。模型里这条响应是 `msuccess = FALSE`，`mcurrentIdx = 0`，`mfirstIdx = 2`（prev 为 1）。n2 此时日志为空，`matchIndex` 是 0。

库在 `raft_recv_appendentries_response`（`artifact/raft/src/raft_server.c:310-322`）。失败且 `current_idx < next_idx - 1` 不成立时，把 `next_idx` 减 1。`next_idx` 为 1 时结果是 0。成功且 `current_idx <= match_idx` 时在 343 行直接返回，不改 `next_idx`。代码留下 1，说明节点处理的是成功响应，或者在减之前就返回了。模型按袋里的失败响应走了减 1。

比较项没有快照元数据。n2 的可见日志是空的，快照基址可以不同，响应的 `success` 就会不同。规格的响应公式按模型里的 `msuccess` 更新 `nextIndex`，回放仍得到 1。规格和源码都没有为这条记录改过。
