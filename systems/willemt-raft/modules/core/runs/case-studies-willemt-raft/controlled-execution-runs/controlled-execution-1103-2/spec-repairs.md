# 规格对齐

## standard / t0001 / 种子 1 / 步 10

- 变量 `log`，节点 `n2`（模型 `s2`）
- 代码值 `[]`，模型值 `[(2, 'v1')]`
- 比较失败的 `pc`：`HandleAppendEntriesRequest s2 s1 9`

这一步之前，步 6 的 `HandleRequestVoteResponse` 让 `s1` 成为领导者。比较的变量当时一致，但拦截器里的报文比 `nSent` 多两条。步 10 按模型序号取出的字节不是那条带 `v1` 的 AppendEntries，跟随者的日志保持空。

原公式在成为领导者时只丢掉这张投票响应，不发送 AppendEntries。

`<ce>/system/src/raft_server.c` 的 `raft_become_leader`（157–176 行）在同一次 `raft_recv_requestvote_response` 返回前，按节点数组顺序对每个其他节点调用 `raft_send_appendentries`。调用前刚把 `next_idx` 设成 `current_idx + 1`，所以这条报文没有条目，也不会走快照。

改后的公式：达到多数时，丢掉投票响应，并给 `Server \ {i}` 的每个节点发送一条空的 AppendEntries。`prev` 的下标和任期与 `raft_send_appendentries`（884–937 行）在 `next_idx = current_idx + 1` 时相同。
