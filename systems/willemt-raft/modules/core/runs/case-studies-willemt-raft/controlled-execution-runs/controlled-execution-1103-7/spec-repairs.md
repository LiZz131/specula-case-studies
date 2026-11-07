# 规格对齐

## hunt_broadcast / t0032 / 种子 32 / 步 28

- 变量 `commitIdx`，节点 `n2`（模型 `s2`）
- 代码值 `2`，模型值 `1`
- `pc`：`HandleAppendEntriesRequest s2 s1 25`

这条 AppendEntries 的 `mleaderCommit` 在公式里是 1。库实际发出的那条带的是更新后的提交点，跟随者因此把提交点设成 2。

该报文是更早一次 `HandleAppendEntriesResponse` 在返回前重发的。`<ce>/system/src/raft_server.c` 的 `raft_recv_appendentries_response` 先在 352–373 行可能提高 `commit_idx`，再在 377–379 行调用 `raft_send_appendentries`。发送时读到的是新的提交点。

原公式重发时仍写更新前的 `commitIndex`。

改后的公式：成功路径上的重发使用这次调用已经写下的提交点。失败重试不改提交点，仍用原来的值。
