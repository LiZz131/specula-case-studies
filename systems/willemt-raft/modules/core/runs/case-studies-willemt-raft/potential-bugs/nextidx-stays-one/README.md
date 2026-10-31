# 失败的 AppendEntries 响应没有把 nextIndex 从 1 减到 0

配置 `snapshot`，种子 158，深轨迹 `t0158`。失败步是 `# [42] HandleAppendEntriesResponse s1 s2 40`。同一类还有 `snapshot/t0130` 和 `log/t0169`：代码的 `nextIdx` 停在 1，模型是 0。

n1 的 `nextIdx`。上一步两边都是 `{'n2': 1, 'n3': 2}`。这一步代码仍是 `{'n2': 1, 'n3': 2}`，模型是 `{'n2': 0, 'n3': 2}`。模型里这条响应是 `msuccess = FALSE`，`mcurrentIdx = 0`，`mfirstIdx = 2`（prev 为 1）。n2 此时日志为空，`matchIndex` 是 0。

库在 `raft_recv_appendentries_response`（`artifact/raft/src/raft_server.c:310-322`）。失败且 `current_idx < next_idx - 1` 不成立时，把 `next_idx` 减 1。`next_idx` 为 1 时结果是 0。成功且 `current_idx <= match_idx` 时在 343 行直接返回，不改 `next_idx`。代码留下 1，说明节点处理的是成功响应，或者在减之前就返回了。模型按袋里的失败响应走了减 1。

比较项没有快照元数据。n2 的可见日志是空的，快照基址可以不同，响应的 `success` 就会不同。规格的响应公式按模型里的 `msuccess` 更新 `nextIndex`，回放仍得到 1。规格和源码都没有为这条记录改过。
