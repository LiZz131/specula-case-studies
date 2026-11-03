# 规格对齐

发现于 `controlled-execution-1103-3`。在已对齐过的 `spec/base.tla` 上修改，没有用 `<run>/spec/base.tla` 覆盖。`<run>/spec/base.tla` 未改。回放在下一轮。对齐时只对照 `system/src/raft_server.c`。驱动没有改。

## votingCfgChangeIdx 不随提交清掉

| 项 | 内容 |
|---|---|
| 配置 / 轨迹 / 种子 | membership / t0025 / 25 |
| 步号 | `# [30] HandleAppendEntriesRequest s3 s2 18` |
| 变量 | votingCfgChangeIdx |
| 代码值 | 2 |
| 模型值 | 0 |
| 这一步之后两边已经相同的状态 | `s3` 的日志是 `[(4, Noop, {}), (4, Config, {n2,n3})]`，`commitIndex` 是 2。配置条目就在下标 2 |
| 原公式 | 提交点盖过的配置条目不再算未提交，`votingCfgChangeIdx` 写成 0。`AdvanceCommitIndex` 里也有同样的清零，注释指向 `raft_server.c:1301` |
| 源码 | `raft_append_entry` 在 1296–1297 行追加投票配置时把 `voting_cfg_change_log_idx` 写成当前下标。`raft_delete_entry_from_idx` 在 424–425 行删到该下标时写成 -1。`raft_apply_entry` 在 1337–1338 行应用到该下标时写成 -1。`raft_recv_appendentries` 推进 `commit_idx` 时不清这个字段，这一步也不调用 `raft_apply_entry`。`raft_update_commit_idx` 同样不清 |
| 改后 | `HandleAppendEntriesRequest` 只在删掉该下标或新追加配置条目时改 `votingCfgChangeIdx`。提交本身保持原值。`AdvanceCommitIndex` 不再改它。这一步 `s3` 仍是 2 |
