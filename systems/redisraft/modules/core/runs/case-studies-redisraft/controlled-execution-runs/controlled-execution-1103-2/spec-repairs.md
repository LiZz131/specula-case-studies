# 规格对齐

发现于 `controlled-execution-1103-2`。在已对齐过的 `spec/base.tla` 上修改，没有用 `<run>/spec/base.tla` 覆盖。`<run>/spec/base.tla` 未改。回放在下一轮。对齐时只对照 `system/src/raft_server.c`。驱动没有改。

## HandleAppendEntriesRequest 不能整段覆盖

| 项 | 内容 |
|---|---|
| 配置 / 轨迹 / 种子 | crashrecovery / t0010 / 10 |
| 步号 | `# [28] HandleAppendEntriesRequest s3 s2 15` |
| 变量 | log |
| 代码值 | `[(3, Noop, {}), (3, Value, {}), (3, Value, {})]` |
| 模型值 | `[(3, Noop, {})]` |
| 这一步之前 | `s3` 的日志已有上述三条，任期都是 3。序号 15 的请求 `mprevLogIndex` 为 0，`mentries` 只有第一条 Noop，`mleaderCommit` 为 0 |
| 原公式 | 从 `prevIdx` 之后整段换成消息里的条目。注释写「与源码先找冲突再截断等价」 |
| 源码 | `raft_recv_appendentries`，`system/src/raft_server.c` 973–1014 行。已有条目任期相同则留下，包括消息末尾之后的后缀。只在同一下标任期不同时从该下标删掉后面的条目，再追加剩余条目 |
| 改后 | 找到消息里第一条缺失或任期不同的位置再截断并追加。消息前缀全部吻合时日志保持不变。这一步 `s3` 的日志仍是三条 |
