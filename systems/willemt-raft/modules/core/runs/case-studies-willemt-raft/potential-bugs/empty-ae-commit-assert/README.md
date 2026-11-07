# empty-ae-commit-assert

库在快照边界发出一条没有条目的 AppendEntries，跟随者日志为空时进程在断言处退出。表现是崩溃。

| 配置 | 轨迹 | 种子 | 步 | 变量 | 代码值 | 模型值 |
|---|---|---|---|---|---|---|
| hunt_broadcast | t0050 | 50 | 28 | commitIdx / n2 | 空（进程已退出） | 1 |
| hunt_broadcast | t0050-1103-9 | 50 | 28 | commitIdx / n2 | 空（进程已退出） | 1 |
| hunt_snapshot | t0031 | 31 | 29 | commitIdx / n2 | 空（进程已退出） | 2 |
| hunt_broadcast | t0050-1103-10 | 50 | 29 | commitIdx / n2 | 空（进程已退出） | 1 |
| hunt_log | t0032 | 32 | 27 | commitIdx / n2 | 空（进程已退出） | 1 |
| hunt_snapshot | t0010 | 10 | 28 | commitIdx / n1 | 空（进程已退出） | 1 |
| hunt_snapshot | t0031-1103-10 | 31 | 29 | commitIdx / n2 | 空（进程已退出） | 1 |
| hunt_snapshot | t0050-hunt-snapshot | 50 | 28 | commitIdx / n2 | 空（进程已退出） | 1 |
| hunt_snapshot | t0066 | 66 | 29 | commitIdx / n2 | 空（进程已退出） | 1 |
| hunt_snapshot | t0089 | 89 | 28 | commitIdx / n3 | 空（进程已退出） | 1 |

`n3` 的快照停在下标 1，后面还留着一条日志。它对 `n2` 的 `next_idx` 也是 1。`raft_send_appendentries`（`raft_server.c` 901–909 行）只在 `next_idx < snapshot_last_idx` 时发快照。相等时走 `log_get_from_idx`（`raft_log.c` 177–180 行）：下标不大于日志基址就返回 0 条。发出的报文是 `prev_log_idx = 0`、`leader_commit = 1`、没有条目。捕获长度 56 字节，比带一条日志的报文少一个 `raft_entry_t`。

`n2` 当时日志为空，当前下标是 0。`raft_recv_appendentries`（515–520 行）把提交点设成 `min(max(current_idx, 1), leader_commit)`，也就是 1。`raft_set_commit_idx`（`raft_server_properties.c` 117–118 行）要求这个下标不超过当前日志末尾，断言失败，进程退出。比较读到的代码值是空的。

协议要求提交点不超过本机已有日志，进程保持运行。领导者在要发送的下标已经落在快照里、而快照之后仍有日志时，应带上这些日志，前一条指向快照；没有可发送的日志时才发空的 AppendEntries，并且不得把跟随者的提交点抬过它的日志末尾。模型值 1 不是修补目标。

复现：`run_one_testcase.sh potential-bugs/empty-ae-commit-assert/t0050/MC.out 3`。同一现象在 `controlled-execution-1103-9` 的 `hunt_broadcast` 种子 50 再次出现，轨迹在 `t0050-1103-9`。复现：`run_one_testcase.sh potential-bugs/empty-ae-commit-assert/t0050-1103-9/MC.out 3`。失败步是 `# [28] HandleAppendEntriesRequest s2 s3 26`。

`controlled-execution-1103-9` 的 `hunt_snapshot` 种子 31 是同一类。`n3` 的快照下标是 1，`n2` 的 `next_idx` 也是 1，发出的仍是 56 字节的空 AppendEntries，`leader_commit` 在库侧高于空日志。复现：`run_one_testcase.sh potential-bugs/empty-ae-commit-assert/t0031/MC.out 3`。失败步是 `# [29] HandleAppendEntriesRequest s2 s3 23`。按协议，`n2` 应仍在运行，提交点保持 0。

`controlled-execution-1103-10` 的 `hunt_broadcast` 种子 50 被 `NoCommittedEntryDeletion` 拦住：模型把 `s2` 的提交点写成 1，日志仍是空的。回放同一条 `MC.out` 时，`n2` 在 `raft_set_commit_idx` 断言处退出。复现：`run_one_testcase.sh potential-bugs/empty-ae-commit-assert/t0050-1103-10/MC.out 3`。失败步是 `# [29] HandleAppendEntriesRequest s2 s3 26`。按协议，`n2` 应仍在运行，提交点保持 0。

`controlled-execution-1103-10` 的 `hunt_log` 种子 32 同样被 `NoCommittedEntryDeletion` 拦住，`s2` 日志为空、提交点为 1。回放时 `n2` 在同一断言处退出。复现：`run_one_testcase.sh potential-bugs/empty-ae-commit-assert/t0032/MC.out 3`。失败步是 `# [27] HandleAppendEntriesRequest s2 s1 26`。按协议，`n2` 应仍在运行，提交点保持 0。

`controlled-execution-1103-10` 的 `hunt_snapshot` 种子 10 同样被 `NoCommittedEntryDeletion` 拦住，这次是 `s1`：日志为空、提交点为 1。回放时 `n1` 在同一断言处退出。复现：`run_one_testcase.sh potential-bugs/empty-ae-commit-assert/t0010/MC.out 3`。失败步是 `# [28] HandleAppendEntriesRequest s1 s3 22`。按协议，`n1` 应仍在运行，提交点保持 0。

`controlled-execution-1103-10` 的 `hunt_snapshot` 种子 31 同样被这个不变量拦住：`s2` 日志为空、提交点为 1。回放时 `n2` 在同一断言处退出。复现：`run_one_testcase.sh potential-bugs/empty-ae-commit-assert/t0031-1103-10/MC.out 3`。失败步是 `# [29] HandleAppendEntriesRequest s2 s3 23`。按协议，`n2` 应仍在运行，提交点保持 0。

`controlled-execution-1103-10` 的 `hunt_snapshot` 种子 50 同样被这个不变量拦住：`s2` 日志为空、提交点为 1。回放时 `n2` 在同一断言处退出。复现：`run_one_testcase.sh potential-bugs/empty-ae-commit-assert/t0050-hunt-snapshot/MC.out 3`。失败步是 `# [28] HandleAppendEntriesRequest s2 s3 24`。按协议，`n2` 应仍在运行，提交点保持 0。

`controlled-execution-1103-10` 的 `hunt_snapshot` 种子 66 同样被这个不变量拦住：`s1` 的快照下标是 1，对 `s2` 的 `next_idx` 也是 1，发出的仍是空 AppendEntries，`leader_commit` 为 1。`s2` 日志为空、提交点被写成 1。回放时 `n2` 在同一断言处退出。复现：`run_one_testcase.sh potential-bugs/empty-ae-commit-assert/t0066/MC.out 3`。失败步是 `# [29] HandleAppendEntriesRequest s2 s1 24`。按协议，`n2` 应仍在运行，提交点保持 0。

`controlled-execution-1103-10` 的 `hunt_snapshot` 种子 89 同样被这个不变量拦住：`s1` 的快照下标是 1，对 `s3` 的 `next_idx` 也是 1，发出的仍是空 AppendEntries，`leader_commit` 为 1。`s3` 日志为空、提交点被写成 1。回放时 `n3` 在同一断言处退出。复现：`run_one_testcase.sh potential-bugs/empty-ae-commit-assert/t0089/MC.out 3`。失败步是 `# [28] HandleAppendEntriesRequest s3 s1 25`。按协议，`n3` 应仍在运行，提交点保持 0。

KNOWN: https://github.com/willemt/raft/pull/118 第 2 点。其中的 `TestCluster_trace_3_99878_assertion_set_commit_idx_le_current_idx` 就是 `raft_set_commit_idx` 的这个断言。该 PR 仍是 open。
