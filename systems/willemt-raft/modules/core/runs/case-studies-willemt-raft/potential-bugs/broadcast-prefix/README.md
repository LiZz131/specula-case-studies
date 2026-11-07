# broadcast-prefix

规格问题。领导者拨钟广播时，库按节点加入顺序发送，并在第一个需要快照的节点处停住。公式可以少发，序号随后错位。

| 配置 | 轨迹 | 种子 | 步 | 变量 | 代码值 | 模型值 |
|---|---|---|---|---|---|---|
| hunt_broadcast | t0001 | 1 | 16 | currentTerm / n1 | 3 | 5 |

位置：`raft_server.c` 的 `raft_send_appendentries_all`，946–953 行。需要快照时的返回在 901–906 行。

库按固定顺序发送。差在公式把接收者写成了任意子集。修改记在 `controlled-execution-runs/controlled-execution-1103-5/spec-repairs.md`。重新插桩后的轮次是 `controlled-execution-1103-6`。

复现：`run_one_testcase.sh potential-bugs/broadcast-prefix/t0001/MC.out 3`。失败步是 `# [16] HandleAppendEntriesRequest s1 s3 20`。按源码，步 13 的广播应发给每一个尚未需要快照的节点。
