# periodic-apply

规格问题。拨钟返回前，库会把已经提交、并且还在日志里的条目应用到状态机。公式的 `Timeout` 不改 `lastApplied`。

| 配置 | 轨迹 | 种子 | 步 | 变量 | 代码值 | 模型值 |
|---|---|---|---|---|---|---|
| standard | t0010 | 10 | 24 | lastApplied / n2 | 1 | 0 |

位置：`raft_server.c` 的 `raft_periodic`，253–259 行，以及 `raft_apply_entry`，812–832 行。

库这一步符合“提交点之后的日志会被应用”。差在公式没写这次应用。修改记在 `controlled-execution-runs/controlled-execution-1103-4/spec-repairs.md`。重新插桩后的轮次是 `controlled-execution-1103-5`。

复现：`run_one_testcase.sh potential-bugs/periodic-apply/t0010/MC.out 3`。失败步是 `# [24] Timeout s2`。按源码，这一步之后 `n2` 的 `lastApplied` 应变成 1。
