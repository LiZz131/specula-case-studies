# AdvanceCommitIndex 的 commitIndex

归类 `spec`。公式修改见 `controlled-execution-runs/controlled-execution-1103-1/spec-repairs.md`。

1. standard，种子 65，步号 `# [24] AdvanceCommitIndex s1`。
2. `commitIndex`：代码值 2，模型值 1。节点 n1 / s1。
3. `system/src/raft_server.c` 的 `raft_update_commit_idx`，2228–2251 行。降序后取 `indexes[num_voters / 2]`。
4. 这一步之前 `matchIndex` 是 `n1=4, n2=2, n3=0`，日志 1..4 的任期都是 1。多数派已经到达的最大下标是 2。库写下 2，符合「提交多数派已复制且任期为当前任期的最大下标」。原公式用 `\E`，1 和 2 都能被选中。
5. 复现：`run_one_testcase.sh potential-bugs/commitIndex-AdvanceCommitIndex/standard-t0065/MC.out 3`。失败步是 `# [24]`。按源码应看到 `commitIndex` 为 2。这条 `MC.out` 是修改前的采样，模型值仍是 1。
