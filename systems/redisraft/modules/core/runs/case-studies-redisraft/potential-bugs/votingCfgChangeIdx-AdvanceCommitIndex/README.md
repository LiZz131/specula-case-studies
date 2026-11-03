# AdvanceCommitIndex 的 votingCfgChangeIdx

归类 `spec`。公式修改见 `controlled-execution-runs/controlled-execution-1103-4/spec-repairs.md`。

1. membership，种子 25，步号 `# [26] AdvanceCommitIndex s2`。
2. `votingCfgChangeIdx`：代码值 0，模型值 2。节点 n2 / s2。这一步之后 `commitIndex` 两边都是 2。
3. `system/src/raft_server.c` 的 `raft_apply_entry`，1337–1338 行。
4. 提交点越过下标 2 之后，这一步把该条目应用掉，库把配置变更下标清掉。上一轮的公式在这个动作里保持原值。接收 AppendEntries 的那一步不应用，所以那里仍然不清。
5. 复现：`run_one_testcase.sh potential-bugs/votingCfgChangeIdx-AdvanceCommitIndex/membership-t0025/MC.out 3`。失败步是 `# [26]`。按源码应看到 0。这条 `MC.out` 是修改前的采样，模型值仍是 2。
