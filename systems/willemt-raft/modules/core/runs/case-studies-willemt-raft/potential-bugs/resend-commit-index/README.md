# resend-commit-index

规格问题。AppendEntries 响应成功并提高提交点之后，同一次调用重发的 AppendEntries 带着新的提交点。公式重发时仍写旧的提交点，跟随者的 `commitIdx` 就对不上。

| 配置 | 轨迹 | 种子 | 步 | 变量 | 代码值 | 模型值 |
|---|---|---|---|---|---|---|
| hunt_broadcast | t0032 | 32 | 28 | commitIdx / n2 | 2 | 1 |

位置：`raft_server.c` 的 `raft_recv_appendentries_response`，352–379 行。提交点先更新，再发送。

库这一步符合“心跳和复制携带当前提交点”。差在公式用了更新前的值。修改记在 `controlled-execution-runs/controlled-execution-1103-7/spec-repairs.md`。重新插桩后的轮次是 `controlled-execution-1103-8`。

复现：`run_one_testcase.sh potential-bugs/resend-commit-index/t0032/MC.out 3`。失败步是 `# [28] HandleAppendEntriesRequest s2 s1 25`。按源码，`n2` 的提交点应变成 2。
