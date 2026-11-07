# become-leader-appendentries

规格问题。成为领导者的那一次 `raft_recv_requestvote_response` 会在返回前发出 AppendEntries。公式没有这些报文，后面的序号就不再指向同一条字节，跟随者也就没有写入模型里的日志。

| 配置 | 轨迹 | 种子 | 步 | 变量 | 代码值 | 模型值 |
|---|---|---|---|---|---|---|
| standard | t0001 | 1 | 10 | log / n2 | `[]` | `[(2, 'v1')]` |

位置：`raft_server.c` 的 `raft_become_leader`，166–176 行。它调用 `raft_send_appendentries`。

库这一步符合“赢得选举后立刻向其他节点发送 AppendEntries”。差在公式的 `HandleRequestVoteResponse` 只丢掉投票响应。修改记在 `controlled-execution-runs/controlled-execution-1103-2/spec-repairs.md`。重新插桩后的轮次是 `controlled-execution-1103-3`。

复现：`run_one_testcase.sh potential-bugs/become-leader-appendentries/t0001/MC.out 3`。失败步是 `# [10] HandleAppendEntriesRequest s2 s1 9`。按源码，步 6 成为领导者时就应发出两条空的 AppendEntries。
