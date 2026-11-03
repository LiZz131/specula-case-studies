# HandleAppendEntriesRequest 的 log

归类 `spec`。公式修改见 `controlled-execution-runs/controlled-execution-1103-2/spec-repairs.md`。

1. crashrecovery，种子 10，步号 `# [28] HandleAppendEntriesRequest s3 s2 15`。
2. `log`：代码值 `[(3, Noop, {}), (3, Value, {}), (3, Value, {})]`，模型值 `[(3, Noop, {})]`。节点 n3 / s3。
3. `system/src/raft_server.c` 的 `raft_recv_appendentries`，973–1014 行。
4. 序号 15 的请求只带第一条 Noop，`prevLogIndex` 为 0。接收方日志里同一下标的任期已经是 3，后面还有两条。库留下后缀。协议只在同一下标任期冲突时删除后继。原公式从 `prevIdx` 之后整段覆盖。
5. 复现：`run_one_testcase.sh potential-bugs/log-HandleAppendEntriesRequest/crashrecovery-t0010/MC.out 3`。失败步是 `# [28]`。按源码应看到三条日志。这条 `MC.out` 是修改前的采样，模型值仍是一条。
