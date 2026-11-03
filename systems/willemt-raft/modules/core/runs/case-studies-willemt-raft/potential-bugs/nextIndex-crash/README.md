# 成为领导者时规格多写了自己的 nextIndex

归类：`spec`。不是 Raft 实现缺陷，也不是 adapter。

`nextIndex[服务器]` 是领导者准备发给该服务器的下一条日志下标。领导者不给自己发 AppendEntries。`raft_send_appendentries` 开头就 `assert(node != me->node)`。自己的 `nextIndex` 不参与选举安全、日志匹配、领导者完整性和状态机安全。代码在 `raft_become_leader`（`raft_server.c` 170 行）跳过自己，把自己的 `next_idx` 留在初始值 1，对等节点写成 `current_idx + 1`。这和协议一致。

规格 `HandleRequestVoteResponse`（`spec/base.tla` 303–305 行）注释写的是源码 173–174 行，那两行在 `continue` 之后，只作用于对等节点。公式却写成 `[k \in Server |-> LastLogIndex(i) + 1]`，把自己也算进去。日志非空时 `LastLogIndex + 1` 大于 1，比较就失败。这是模型多写了一个赋值。

## 轨迹

| 配置 | 种子 | 步 | 代码 | 模型 |
|---|---:|---|---|---|
| standard | 49 | `# [20] HandleRequestVoteResponse s2 s3 15` | `{'n1': 2, 'n2': 1, 'n3': 2}` | `{'n1': 2, 'n2': 2, 'n3': 2}` |
| vote | 84 | `# [28] HandleRequestVoteResponse s2 s3 17` | 同上 | 同上 |

差的只有 s2 自己。对等节点都是 2，`state` 已经是 Leader。模型轨迹、测试用例和复现命令仍是本目录的 `MC.out`、`traces.txt`：

```text
bash /root/sandtable/specula-wraft/sandtable/systems/WRaft-series/WRaft/scripts/run_one_testcase.sh \
  /root/sandtable/specula-wraft/standard/traces/t0049/MC.out 3
```

## 建议

改规格，不要改库。`nextIndex` 只更新 `Server \ {i}`，自己保持原值。`matchIndex` 同样只写对等节点；这一步两边的 `matchIndex` 本来就是对齐的。
