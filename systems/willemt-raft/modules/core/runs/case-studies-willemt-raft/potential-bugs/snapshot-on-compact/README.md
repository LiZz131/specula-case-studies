# snapshot-on-compact

规格问题。领导者压缩日志时，`raft_end_snapshot` 返回前会给落后的同伴发快照。公式把网络留在未改变里，捕获条数就比 `nSent` 多 1。

| 配置 | 轨迹 | 种子 | 步 | 变量 | 代码值 | 模型值 |
|---|---|---|---|---|---|---|
| hunt_log | t0035 | 35 | 28 | net-len | 28 | 27 |

位置：`raft_server.c` 的 `raft_end_snapshot`，1337–1354 行。`n1` 发给 `n2` 的那条是 32 字节。`n2` 的 `next_idx` 是 1，新快照下标是 2。`n3` 的 `next_idx` 是 3，不发。

库这一步符合“压缩掉的前缀改由快照交给落后节点”。差在公式没有记下这次调用返回前发出的快照。修改记在 `controlled-execution-runs/controlled-execution-1103-8/spec-repairs.md`。重新插桩后的轮次是 `controlled-execution-1103-9`。

复现：`run_one_testcase.sh potential-bugs/snapshot-on-compact/t0035/MC.out 3`。失败步是 `# [28] TakeSnapshot s1`。按源码，这一步应多发出一条给 `n2` 的快照。
