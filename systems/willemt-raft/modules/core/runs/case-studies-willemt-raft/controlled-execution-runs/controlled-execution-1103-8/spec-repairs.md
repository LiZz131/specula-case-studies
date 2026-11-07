# 规格对齐

## hunt_log / t0035 / 种子 35 / 步 28

- 变量 `net-len`
- 代码捕获到第 28 条，模型 `nSent` 是 27
- `pc`：`TakeSnapshot s1`

`n1` 是领导者。压缩后快照下标是 2，`n2` 的 `next_idx` 是 1。`raft_end_snapshot` 在返回前按节点加入顺序检查每个同伴。`next_idx < snapshot_last_idx` 时调用 `send_snapshot`。这次只发给 `n2`，32 字节。

原公式把 `messages` 留在 `UNCHANGED` 里，这次调用发出的快照没有写进模型。

改后的公式：领导者在压缩时，对每个 `nextIndex <` 新快照下标的同伴，按 `PeerSeq` 发一条 `InstallSnapshotRequest`。快照下标和任期用这次写下的新值。跟随者不发。
