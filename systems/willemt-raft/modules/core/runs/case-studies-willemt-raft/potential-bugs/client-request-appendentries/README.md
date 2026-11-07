# client-request-appendentries

规格问题。领导者处理客户端条目时，若对端的 `next_idx` 已经等于新日志的下标，同一次 `raft_recv_entry` 会把这条新日志发出去。公式没有这些报文，序号随后错位，跟随者的日志里出现了模型还没有的条目。

| 配置 | 轨迹 | 种子 | 步 | 变量 | 代码值 | 模型值 |
|---|---|---|---|---|---|---|
| standard | t0001 | 1 | 12 | log / n2 | `[(2, 'v1')]` | `[]` |

位置：`raft_server.c` 的 `raft_recv_entry`，749–764 行。

库这一步符合“追上的跟随者立刻收到新条目”。差在公式的 `ClientRequest` 不发送。修改记在 `controlled-execution-runs/controlled-execution-1103-3/spec-repairs.md`。重新插桩后的轮次是 `controlled-execution-1103-4`。

复现：`run_one_testcase.sh potential-bugs/client-request-appendentries/t0001/MC.out 3`。失败步是 `# [12] HandleRequestVoteRequest s2 s1 1`。按源码，步 8 的 `ClientRequest` 就应向已经对齐的对端发出带 `v1` 的 AppendEntries。
