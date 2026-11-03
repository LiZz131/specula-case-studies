# 空日志上把提交点抬到 1 然后断言退出

归类：进程退出是 `bug`。模型给出的 commit 2 和 1 不是这封线上消息的协议结果。

## 线上实际收到的消息

t0026、t0086 的公式消息有两条日志，`leaderCommit` 分别是 2 和 1。库发出的是 56 字节，0 条。原因和 `log-crash` 的 t0020、t0033 相同：`next_idx == snapshot_last_idx == 1`，`log_get_from_idx` 返回空，`NeedsSnapshot` 用的是 `<`，不发快照。`SubLog` 在 `fromIdx <= snapshotLastIdx` 时返回整段内存日志，所以模型以为跟随者会先追加两条再提交。那是规格没模仿到 908 行。adapter 没有丢掉条目。

| 轨迹 | 步 | 接收方步前 | 线上 | 模型之后 |
|---|---|---|---:|---|
| t0026 | `# [36] HandleAppendEntriesRequest s2 s3 26` | 空日志，快照 0，commit 0 | 56 字节 | 两条日志，commit 2 |
| t0086 | `# [35] HandleAppendEntriesRequest s3 s2 26` | 同上 | 56 字节 | 两条日志，commit 1 |

发送步：t0026 是 `# [35] SendAppendEntries s3 s2`，t0086 是 `# [34] BroadcastAppendEntries s2 ['s3']`。

按这封空消息，Raft 的提交规则是 `commitIndex = min(leaderCommit, 最后一条日志的下标)`。日志是空的，最后下标是 0，提交点保持 0，进程继续。

## 代码违反协议的地方

`raft_recv_appendentries` 519 行用 `max(current_idx, 1)`。`current_idx` 是 0，得到 1，再交给 `raft_set_commit_idx`。`raft_server_properties.c` 118 行 `assert(idx <= raft_get_current_idx(me_))` 失败，进程退出。t0026 的 stderr 在 `t0026/n2.err`，重放时 n2 同样打出这一行。提交一个不存在的下标，并且把进程打死，不符合协议。

规格 486–488 行的 `ELSE 1` 是在模仿这句 `max(current_idx, 1)`。如果消息真是空的，模型会把 commit 写成 1 而不是退出。两条轨迹里模型 commit 是 2 和 1，是因为模型先按 `SubLog` 把日志追加了。不要把「修到 commit 2」当成目标。

发送端那个 `<` 也符合「该发快照却发了空 AppendEntries」，见 `log-crash`。那是另一处实现问题，不解释这次断言。

## 建议修改

`raft_set_commit_idx` 在下标超过当前日志时返回错误，不要 `assert`。519 行用 `raft_get_current_idx`，空日志上提交点保持 0。

快照发送的相等情况改成 `next_idx <= snapshot_last_idx` 时发 InstallSnapshot。不要为了贴近 `SubLog` 把后缀塞进 `prev = 0` 的 AppendEntries。

## 复现

节点数 3。测试用例 t0026 在 `traces.txt` 第 4006 行：`deliver-unordered n3 n2 26`，然后 `execute n2 raft recvfrom n3`。

```text
bash /root/sandtable/specula-wraft/sandtable/systems/WRaft-series/WRaft/scripts/run_one_testcase.sh \
  /root/sandtable/specula-wraft/install-deep/traces/t0026/MC.out 3
```

期望 n2 在 `raft_set_commit_idx` 断言退出。协议要求的是进程还在，commit 仍是 0。
