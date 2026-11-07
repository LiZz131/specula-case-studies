# appendentries-response-resend

规格问题。处理 AppendEntries 响应时，库会在返回前再发一次。公式没有这封报文，拦截器里的条数就比 `nSent` 多一。

| 配置 | 轨迹 | 种子 | 步 | 变量 | 代码值 | 模型值 |
|---|---|---|---|---|---|---|
| hunt_broadcast | t0025 | 25 | 26 | net-len | 12 | 11 |

位置：`raft_server.c` 的 `raft_recv_appendentries_response`，326 行和 377–379 行。

可见变量在这一步是对齐的。差在公式只丢掉响应。修改记在 `controlled-execution-runs/controlled-execution-1103-6/spec-repairs.md`。重新插桩后的轮次是 `controlled-execution-1103-7`。

复现：`run_one_testcase.sh potential-bugs/appendentries-response-resend/t0025/MC.out 3`。步 26 是 `HandleAppendEntriesResponse s1 s3 26`。按源码，这一步应再发出一条 AppendEntries。
