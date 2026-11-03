# 规格对齐

发现于 `controlled-execution-1103-1`。在上一轮已经对齐过的 `spec/base.tla` 上修改，没有用 `<run>/spec/base.tla` 覆盖。`<run>/spec/base.tla` 未改。回放在下一轮。对齐时只对照 `system/src/raft_server.c`。驱动没有改。

## AdvanceCommitIndex 必须取最大下标

| 项 | 内容 |
|---|---|
| 配置 / 轨迹 / 种子 | standard / t0065 / 65 |
| 步号 | `# [24] AdvanceCommitIndex s1` |
| 变量 | commitIndex |
| 代码值 | 2 |
| 模型值 | 1 |
| 这一步之前 | `s1` 是 Leader，任期 1。日志下标 1..4 的任期都是 1。`matchIndex` 为 `n1=4, n2=2, n3=0` |
| 原公式 | `\E n`：任何一个多数派 `matchIndex >= n` 且 `log[n].term = currentTerm` 的下标都可以写入 `commitIndex`。TLC 选了 1 |
| 源码 | `raft_update_commit_idx`，`system/src/raft_server.c` 2228–2251 行。投票节点的 `match_idx` 降序排列后取 `indexes[num_voters / 2]`。三个值 4、2、0 取到 2。该条目任期等于当前任期时写入 `commit_idx`。`raft_specula_advance_commit` 只调用这个函数 |
| 改后 | 候选下标收成一个集合，`commitIndex` 写成 `SetMax(candidates)`。这一步是 2 |
