# AppendEntries 之后的日志长度

11 条都在 `install-deep`，失败步都是 `HandleAppendEntriesRequest`。adapter 没有改这些日志：控制器交付的是库发出的字节，`log` 读的是库的内存日志。线上长度是 `56 + 32 × 条目数`，56 字节就是 0 条。

按 Raft 的 AppendEntries 和 InstallSnapshot 重新判过。不能把 `base.tla` 的结果当成协议要求的结果：这份规格是按源码行号模仿实现的。

## 发送端：比较失败是规格问题，空消息本身违反协议

t0020、t0033。归类：这条 compare 是 `spec`。

领导者的 `nextIndex` 已经退到 `snapshot_last_idx`（两条都是快照 1、`nextIndex` 1、内存里还有两条日志）。`NeedsSnapshot`（`base.tla` 160–162 行）和源码 902 行都用 `next_idx < snapshot_last_idx`。相等时不发快照。`log_get_from_idx`（`raft_log.c` 177–180 行）对 `idx <= base` 返回 0 条，所以库发出 56 字节的空 AppendEntries，`prev_log_idx` 仍是 0。跟随者原日志不动。空 AppendEntries 本来就不该改日志，接收端这一步没有写错。

规格 `SubLog`（140–143 行）在 `fromIdx <= snapshotLastIdx` 时返回整段内存日志，注释还把它当成 `raft_get_entries_from_idx`（908 行）。公式消息因此有两条，模型日志变长。这是模型没模仿到源码：908 行在这个下标上返回的是空。

库的发送仍然不符合 Raft。`nextIndex` 落在快照最后下标上时，那条日志已经不在日志数组里，领导者要发 InstallSnapshot，而不是空心跳。源码的 `<` 少了相等的情况，跟随者补不上已提交的前缀。修的时候把条件改成 `next_idx <= snapshot_last_idx` 就发快照。不要改成规格那样带 `prev = 0` 把后缀塞进 AppendEntries，那也不是协议。

| 轨迹 | 失败步 | 跟随者步前 | 公式消息 | 线上 | 代码日志 | 模型日志 |
|---|---|---|---|---:|---|---|
| t0020 | `# [42] HandleAppendEntriesRequest s3 s1 28` | 一条 `(3,v1)`，快照 0 | 两条，leaderCommit 1 | 56 | 一条 | 两条 |
| t0033 | `# [44] HandleAppendEntriesRequest s1 s2 29` | 一条 `(3,v1)`，快照 0 | 两条，leaderCommit 1 | 56 | 一条 | 两条 |

发送步：t0020 是 `# [37] SendAppendEntries s1 s3`，t0033 是 `# [40] SendAppendEntries s2 s1`。

## 接收端：相同消息下代码多追加，违反日志匹配

其余 9 条。公式消息的条目数和线上字节数一致，adapter 交的就是这封 AppendEntries。`prev_log_idx` 是 0，条目按协议落在下标 1、2、3。跟随者已经打过快照，这些下标有的落在快照里。

协议：下标已经包含在快照里的条目不能再追加；只处理快照之后、本地还没有或任期冲突的下标。

代码（`raft_recv_appendentries` 433 行跳过 prev 检查，480–513 行从下标 1 找）：下标 1 在 `base` 之下，`raft_get_entry_from_idx` 返回空，循环把「空」当成「后面都没有」，`raft_append_entry` 接到后缀末尾。新条目拿到的是新下标，不是消息里的 1、2、3。同一任期的命令出现在错误下标上，违反日志匹配。9 条都是代码条数 = 步前条数 + 消息条数。这是实现问题。

建议改库：`ety_index <= snapshot_last_idx` 的条目跳过，从 `snapshot_last_idx + 1` 再和后缀比对。

规格并不是这 9 条的正确结果。`LogTermAt` 对严格小于快照下标的位置返回 0（`base.tla` 110–115 行，注释里标成实现的 bug）。`HandleAppendEntriesRequest` 把这个 0 当成任期冲突，把消息条目写进后缀数组。后缀数组的含义是「快照之后的日志」，写进去之后下标就错了。

| 轨迹 | 步前（条数，快照/任期） | 消息下标 | 协议要求的后缀条数 | 模型条数 | 代码条数 | 模型是否等于协议 |
|---|---|---|---:|---:|---:|---|
| t0030 | 2，快照 1/2 | 1 | 2 | 2 | 3 | 是 |
| t0038 | 1，快照 1/2 | 1 | 1 | 1 | 2 | 是 |
| t0051 | 1，快照 2/2 | 1 | 1 | 1 | 2 | 可见值相同 |
| t0060 | 1，快照 1/2 | 1、2 | 1 | 1 | 3 | 是 |
| t0037 | 3，快照 3/4 | 1、2、3 | 3 | 3 | 6 | 可见值相同 |
| t0014 | 1，快照 2/1 | 1、2 | 1 | 2 | 3 | 否 |
| t0036 | 1，快照 2/3 | 1、2 | 1 | 2 | 3 | 否 |
| t0073 | 1，快照 2/3 | 1、2、3 | 1 | 3 | 4 | 否 |
| t0083 | 1，快照 2/3 | 1、2 | 1 | 2 | 3 | 否 |

前五行的模型可见日志和协议要求一致，compare 直接说明代码多追加了。后四行模型自己也变长了，不能把模型日志当成要修到的目标；代码比协议要求更长，仍然是实现把快照里的条目又追加了一遍。t0051、t0037 的公式走的是「任期 0 冲突然后整段换掉」，换进去的值碰巧和原后缀一样，所以看起来对齐。

失败步和测试用例位置：

| 轨迹 | 步 | traces.txt |
|---|---|---|
| t0014 | `# [40] HandleAppendEntriesRequest s1 s2 16` | 第 4469 行 |
| t0030 | `# [38] HandleAppendEntriesRequest s1 s2 15` | |
| t0036 | `# [36] HandleAppendEntriesRequest s3 s2 15` | |
| t0037 | `# [43] HandleAppendEntriesRequest s1 s3 15` | |
| t0038 | `# [37] HandleAppendEntriesRequest s2 s3 17` | |
| t0051 | `# [42] HandleAppendEntriesRequest s2 s1 14` | |
| t0060 | `# [41] HandleAppendEntriesRequest s3 s1 24` | |
| t0073 | `# [41] HandleAppendEntriesRequest s2 s3 20` | |
| t0083 | `# [43] HandleAppendEntriesRequest s1 s2 20` | |

## 复现

节点数 3。

```text
bash /root/sandtable/specula-wraft/sandtable/systems/WRaft-series/WRaft/scripts/run_one_testcase.sh \
  /root/sandtable/specula-wraft/install-deep/traces/t0030/MC.out 3
bash /root/sandtable/specula-wraft/sandtable/systems/WRaft-series/WRaft/scripts/run_one_testcase.sh \
  /root/sandtable/specula-wraft/install-deep/traces/t0020/MC.out 3
```

t0030 期望 n1 的代码日志是 3 条、模型是 2 条，协议要求也是 2 条。t0020 期望代码和步前一样是 1 条，模型是 2 条；那 2 条是规格多放进消息里的。
