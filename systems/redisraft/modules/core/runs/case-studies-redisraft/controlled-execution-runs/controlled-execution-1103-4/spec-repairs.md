# 规格对齐

发现于 `controlled-execution-1103-4`。上一轮把 `AdvanceCommitIndex` 改成不碰 `votingCfgChangeIdx`。这一轮同一变量在这个动作上反过来了。`<run>/spec/base.tla` 未改。`HandleAppendEntriesRequest` 的改动保留。

## AdvanceCommitIndex 应用到提交点时清掉配置下标

| 项 | 内容 |
|---|---|
| 配置 / 轨迹 / 种子 | membership / t0025 / 25 |
| 步号 | `# [26] AdvanceCommitIndex s2` |
| 变量 | votingCfgChangeIdx |
| 代码值 | 0 |
| 模型值 | 2 |
| 这一步之前 | `s2` 的 `votingCfgChangeIdx` 是 2，`commitIndex` 是 0。这一步之后 `commitIndex` 两边都是 2 |
| 原公式 | `UNCHANGED votingCfgChangeIdx`。这是上一轮按 `raft_update_commit_idx` 不改该字段写成的 |
| 源码 | `raft_update_commit_idx` 本身不改这个字段。紧接着的 `raft_apply_all` 会应用到新的提交点。`raft_apply_entry` 在 `system/src/raft_server.c` 1337–1338 行，应用到 `voting_cfg_change_log_idx` 时把它写成 -1。接收 AppendEntries 的那一步不调用 `raft_apply_entry`，所以 follower 上的那次差仍然不清 |
| 改后 | `votingCfgChangeIdx > 0` 且不超过新提交点时写成 0。`HandleAppendEntriesRequest` 仍只在删除或新追加配置条目时修改 |
