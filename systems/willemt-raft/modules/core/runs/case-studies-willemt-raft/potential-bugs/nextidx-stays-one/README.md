# nextIndex 减到 0 时被钳成 1

归类 `adapter`，不是库的 bug。三条都走失败的 AppendEntries 响应。模型把 `nextIndex` 写成 0，库的 setter 拒绝小于 1 的下标，存回 1。

| 轨迹 | 种子 | 步 | 代码 | 模型 |
|---|---:|---|---|---|
| `t0158` | 158 | `# [42] HandleAppendEntriesResponse s1 s2 40` | n1 `{'n2': 1, 'n3': 2}` | n1 `{'n2': 0, 'n3': 2}` |
| `t0130` | 130 | `# [48] HandleAppendEntriesResponse s3 s2 42` | n3 `{'n1': 1, 'n2': 1}` | n3 `{'n1': 1, 'n2': 0}` |
| `t0169` | 169 | `# [38] HandleAppendEntriesResponse s1 s2 35` | n1 `{'n2': 1, 'n3': 2}` | n1 `{'n2': 0, 'n3': 2}` |

上一步该下标两边都是 1。模型消息是 `msuccess = FALSE`，`mcurrentIdx = 0`。`SandHandleAppendEntriesResponse` 走失败分支，`newNext = curNextIdx - 1`，写成 0。

库在 `artifact/raft/src/raft_server.c:322` 调用 `raft_node_set_next_idx(node, next_idx - 1)`。`raft_node.c:64-68` 里写着 log index 从 1 开始，`nextIdx < 1` 时存 1。所以失败路径确实执行了，存进去的值是 1。这不是成功响应提前返回，也不是快照元数据没参加比较。

`Sand*` 要收到库的这条分支上：失败响应算出的 `newNext` 小于 1 时写成 1。这是适配层改动，修好后新开一轮，不并旧的 gcda。规格 `base.tla` / `MC.tla` 和库都不要为这三条改。
