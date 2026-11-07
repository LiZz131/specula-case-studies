# 规格对齐

## standard / t0001 / 种子 1 / 步 12

- 变量 `log`，节点 `n2`（模型 `s2`）
- 代码值 `[(2, 'v1')]`，模型值 `[]`
- 比较失败的 `pc`：`HandleRequestVoteRequest s2 s1 1`

步 8 是 `ClientRequest s1 v1`。那一步的变量比较通过了，拦截器里的报文比 `nSent` 多两条。后面按模型序号交付时，`n2` 收到的是这次调用已经发出的 AppendEntries，日志里有 `v1`。公式里的 `n2` 还没有这条日志。

原公式的 `ClientRequest` 只追加日志，不发送。

`<ce>/system/src/raft_server.c` 的 `raft_recv_entry`（749–764 行）在追加之后、返回之前，按节点数组顺序检查每个其他投票节点。若 `next_idx` 等于追加之后的 `current_idx`，就调用 `raft_send_appendentries`。这条报文带上刚追加的条目。`leader_commit` 用的是发送当时的提交点，单节点提交写在这次发送之后（767–768 行）。

改后的公式：追加条目，并向 `nextIndex[i][p] = LastLogIndex(i) + 1` 的其他节点发送带这条新条目的 AppendEntries。
