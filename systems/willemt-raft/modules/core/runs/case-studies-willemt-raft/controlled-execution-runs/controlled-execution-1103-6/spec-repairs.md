# 规格对齐

## hunt_broadcast / t0025 / 种子 25 / 步 26

- 报文条数，代码 `12`，模型 `11`
- `pc`：`HandleAppendEntriesResponse s1 s3 26`
- 这一步的可见变量一致。库在同一次调用里又发出一条 120 字节的报文。

原公式只丢掉这条 AppendEntries 响应。

`<ce>/system/src/raft_server.c` 的 `raft_recv_appendentries_response`：

- 310–327 行：失败且不是过期响应时，更新 `next_idx` 后立刻 `raft_send_appendentries`。
- 377–379 行：成功且新的 `next_idx` 上还有日志条目时，再发送一次。
- 更高任期（294–300 行）和过期响应在返回前不发送。

改后的公式在这两个分支里补上这一次发送。`next_idx` 低于快照时发送快照，否则发送 AppendEntries。
