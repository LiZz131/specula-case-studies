# vote-lease-term

规格问题。库这一步符合 `raft_recv_requestvote`：没有 `current_leader` 时，更高任期的 RequestVote 会把本机任期更新为请求任期。

| 配置 | 轨迹 | 种子 | 步 | 变量 | 代码值 | 模型值 |
|---|---|---|---|---|---|---|
| standard | t0001 | 1 | 2 | currentTerm / n3 | 1 | 0 |

位置：`raft_server.c` 的 `raft_recv_requestvote`，587–601 行。

公式把租约拒绝写成了与 `current_leader` 无关的自由选择。修改记在 `controlled-execution-runs/controlled-execution-1103-1/spec-repairs.md`。重新插桩后的轮次是 `controlled-execution-1103-2`。

复现：`run_one_testcase.sh potential-bugs/vote-lease-term/t0001/MC.out 3`。失败步是 `# [2] HandleRequestVoteRequest s3 s1 2`。按源码，`s3` 的任期应变成 1。
