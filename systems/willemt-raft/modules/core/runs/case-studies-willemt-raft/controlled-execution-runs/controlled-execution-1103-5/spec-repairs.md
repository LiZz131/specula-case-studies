# 规格对齐

## hunt_broadcast / t0001 / 种子 1 / 步 16

- 变量 `currentTerm`，节点 `n1`（模型 `s1`）
- 代码值 `3`，模型值 `5`
- 比较失败的 `pc`：`HandleAppendEntriesRequest s1 s3 20`

步 13 的 `BroadcastAppendEntries` 之后，拦截器里的报文比 `nSent` 多一条。后面按模型序号取到的字节不是公式里的那条 AppendEntries，任期因此对不上。

原公式用任意非空子集表示这次广播，子集里的节点都可以不需要快照。

`<ce>/system/src/raft_server.c` 的 `raft_send_appendentries_all`（946–953 行）按节点数组顺序发送。`raft_send_appendentries` 返回非 0 就停。这里唯一会返回非 0 的是需要快照：先发出快照，再返回 `RAFT_ERR_NEEDS_SNAPSHOT`（901–906 行）。没有快照时，每个其他节点都会收到 AppendEntries。

改后的公式按 `s1, s2, s3` 去掉自己之后的顺序发送。遇到第一个需要快照的节点时，只给它发快照并停止。
