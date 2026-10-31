# ae-prev0-reappend

证据记录。结论在重放之后：`REPRODUCED`。

## 代码

`artifact/raft/src/raft_server.c` 的 `raft_recv_appendentries`。

- 430–432 行：`prev_log_idx > 0` 才做 prev 检查。`prev_log_idx == 0` 整段跳过。
- 472–473 行：把 `success` 设为 1，`current_idx` 设为 `prev_log_idx`。
- 483–501 行：已有条目用 `raft_get_entry_from_idx`。`log_get_at_idx` 对 `idx <= base` 返回 NULL。快照基址之后的下标因此被当成缺失。
- 505–508 行：从第一条起 `raft_append_entry`。

调用链：驱动 `RaftRecvMsg` 的 `MSG_AE` → `raft_recv_appendentries`。入口是正常的 AppendEntries 接收，不是直接调用内部函数。

触发：跟随者已经有快照（`snapshotLastIdx = 1`，`snapshotLastTerm = 2`），日志里还留着快照之后的两条 `(2, v1)`。领导者发来 `prev_log_idx = 0`、三条同样的 `(2, v1)`。

## 开发者记录

`modeling-brief.md` 把同一机制记为 MC-7，并引用 willemt/raft PR #118 Bug 1，状态 UNFIXED。`analysis-report.md` 的 CRITICAL-3 描述的是同一处：`prev_log_idx == 0` 时跳过 §5.3 的一致性检查，已压缩条目被再追加。代码附近没有把这条路径标成有意行为。

Novelty: KNOWN（cite: case study MC-7，PR #118 Bug 1；fix-status: unfixed）。来源是模型轨迹的回放，不是新的代码审阅，所以不因已有记录而丢弃。

## 重放

2026-10-30 对 `t0104/MC.out` 再执行一次 `run_one_testcase.sh`，耗时 4.2 秒，脚本退出码 0，日志里控制器在比较处断言。

```
# [44] HandleAppendEntriesRequest s3 s1 36
Variable "log" compare failed
- Code (n3): [(2, 'v1'), (2, 'v1'), (2, 'v1'), (2, 'v1'), (2, 'v1')]
- Model(n3): [(2, 'v1'), (2, 'v1')]
```

级别 0：消息由 TLC 轨迹投递，节点经公开的接收路径处理。可见日志变长，状态机之后会看到重复条目。`t0187` 的已有日志是同一形状。

Status: REPRODUCED。Severity: High。Location: `artifact/raft/src/raft_server.c:430`。
