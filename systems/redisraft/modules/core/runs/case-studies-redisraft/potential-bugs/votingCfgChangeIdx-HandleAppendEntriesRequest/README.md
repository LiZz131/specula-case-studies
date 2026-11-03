# HandleAppendEntriesRequest 的 votingCfgChangeIdx

归类 `spec`。公式修改见 `controlled-execution-runs/controlled-execution-1103-3/spec-repairs.md`。

1. membership，种子 25，步号 `# [30] HandleAppendEntriesRequest s3 s2 18`。
2. `votingCfgChangeIdx`：代码值 2，模型值 0。节点 n3 / s3。同一时刻 `commitIndex` 两边都是 2，日志都是 `[(4, Noop, {}), (4, Config, {n2,n3})]`。
3. `system/src/raft_server.c`。追加在 `raft_append_entry` 1296–1297 行，删除在 424–425 行，应用在 `raft_apply_entry` 1337–1338 行。
4. 这一步把提交点推进到配置条目，但没有应用它。库留下下标 2。协议里的单次成员变更要等到该条目被应用才结束。原公式在提交时写成 0。
5. 复现：`run_one_testcase.sh potential-bugs/votingCfgChangeIdx-HandleAppendEntriesRequest/membership-t0025/MC.out 3`。失败步是 `# [30]`。按源码应看到 `votingCfgChangeIdx` 为 2。这条 `MC.out` 是修改前的采样，模型值仍是 0。
