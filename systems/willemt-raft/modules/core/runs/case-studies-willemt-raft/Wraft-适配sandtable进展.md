# WRaft 适配 SandTable 进展

协议模块 `spec/base.tla`、`spec/MC.tla` 没有改。willemt/raft 源码和 SandTable 驱动 `WRaft.cpp` 最终与仓库原件一致。受控执行只用已有的 controller / driver 命令：`deliver-unordered`、`raft periodic`、`raft cli`、`raft snapshot`、`raft recvfrom`、`clear`。

## 代码级 bug

`raft_begin_load_snapshot` 把 `current_term` 直接写成快照的 `last_included_term`（`raft_server.c:1383-1384`），不经过 `raft_set_current_term`，任期可以变小。Specula 把它写进 `HandleInstallSnapshot`。`MC.tla` 里的时序性质 `TermNeverDecreases` 就是用来抓它的。这是 PR #118 Bug 4，bug report 里的 KB-1。

`MC_hunt_commit` 那条 11 状态反例不是这个 bug。它违反的是修复前的 `LeaderCompleteness`：过期 Leader 手里没有更高任期已经提交的条目。bug report 已说明这不是实现缺陷。那次为了压掉模型里没有的发送，曾经在 `WRaft.cpp` 加过 `sendmode` / `votemode` / `sendto`，随后已用 `git checkout` 撤回。当前 `git diff` 里这份驱动没有改动。

## 模型检查

无约束 BFS 会被丢消息和广播子集撑大，短反例出不来。`MC_term.tla` 只用 `step` 从 `MCNext` 里挑已经存在的动作，不改动作公式。TLC `-tool` 报告 `TermNeverDecreases` 被违反，完整深度 23（初始状态加 22 步）。

关键状态：

1. n2 在 term 1 成为 Leader，追加两条 `[term 1, v1]`，复制给 n3，`commitIndex` 到 2。
2. n3 对已提交日志做快照：`snapshotLastIdx = 2`，`snapshotLastTerm = 1`，日志被压空。
3. n3 超时到 term 2，n1 投票，n3 成为 Leader。此时 n1 的 term 也是 2。
4. n3 发给 n1 的 AppendEntries 因日志对不上失败，`nextIndex[n1]` 降到 1，低于快照点 2，于是发送 InstallSnapshot。
5. n1 加载快照。发送方当前 term 是 2，不小于 n1 的 term 2，驱动里的 RPC term 检查放行；库把 `current_term` 写成 `last_included_term` 1。

两条 `LoseMessage` 丢掉这份调度不会投递的 RequestVote（n2→n1、n3→n2）。这是原有的 `MCLoseMessage`，用来让随后代码多发的消息独占一条 TCP 通道。

## 没有改 spec，也没有 pc

`spec/base.tla` 和 `spec/MC.tla` 的动作公式没有加 `scr.pc`，也没有改语义。SandTable 自带的 `WRaft/scripts/testcase_generator.py` 读的是 `WillemtRaft.tla` 里的 `scr.pc`。这份 Specula 模型没有这个变量。TLC `-tool` 对一条析取写出的标签是整个 `TraceNext` 或 `MCNext`，不是子动作名，所以不能靠 MC.out 里的动作名驱动生成器。

生成器改成读相邻两个状态：`counters` 哪一项加一，以及 `messages` 这个 bag 多了或少了哪几条。任期下降这条反例上推断出的动作序列是 Timeout、HandleRequestVoteRequest、LoseMessage、HandleRequestVoteResponse、两次 ClientRequest、BroadcastAppendEntries，直到 SendInstallSnapshot、HandleInstallSnapshot。它不依赖 `MC_term.tla` 里的 `step`。任何带 `counters` 和协议变量的 TLC `-tool` 反例都可以喂进去，包括直接从 `MC.tla` 跑出来的。

`MC_term.tla` 只负责让 TLC 在有限步里走到这条行为。它挑选的仍是 `MCNext` 里已有的析取。

## 受控执行怎么从 trace 生成

库和驱动都没有改。生成器按代码的发送点预测 TCP 捕获序号，模型里没有的发送用 `clear src dst` 拿掉，而且只在该通道上没有模型还要保留的消息时才清。序号按捕获顺序编号，清掉的序号不再投递。

这条反例上，自动生成的 749 条命令和原先手写的 `traces.txt` 逐条相同。controller 里重放后，`compare variable` 全部通过，n1 的 `currentTerm` 从 2 变成 1，`log.1` 有 `loaded snapshot sli:2 slt:1`。

第一轮那条过期 Leader 轨迹现在会被生成器拒绝：第 5 步 `clear n2 -> n1` 会把模型还保留的 RequestVote 一起清掉。这不是手写特例，是同一套规则。那条轨迹要走通，得先在模型里丢掉这条通道上的消息，或者接受改 driver。源码没有为它改。

和模型对齐的发送点：

| 代码多做的事 | 模型 | 控制命令 |
|---|---|---|
| `raft_become_leader` 向所有 peer 发 AppendEntries | 成为 Leader 的那一步不发 | `clear` 这两条通道 |
| 第一次 `raft_recv_entry` 在 `next_idx == current_idx` 时发送 | `ClientRequest` 不改 `messages` | `clear` |
| `raft_periodic` 触发的 `send_appendentries_all` 发给所有 peer | `BroadcastAppendEntries` 只选一个目的地 | 保留模型里的那条，`clear` 另一条 |
| AppendEntries 失败处理里立刻 `raft_send_appendentries`，此处变成快照 | 失败步只改 `nextIndex`，快照是下一步 `SendInstallSnapshot` | 失败步 `clear` 掉提前发出的快照；下一步 `raft periodic 200`，`send_appendentries_all` 在第一个需要快照的节点处返回，只发出这一份快照 |
| 驱动在加载快照后总是回 AppendEntries 响应 | `HandleInstallSnapshot` 只 `Discard` | 比较前 `clear` 掉这条响应 |

最后一轮比较（实现返回值 = 模型）：

| 节点 | state | term | commitIdx | log |
|---|---|---|---|---|
| n1 | 1 Follower | 1（上一步是 2） | 2 | `[]` |
| n2 | 3 Leader | 1 | 2 | `[(1, 'v1'), (1, 'v1')]` |
| n3 | 3 Leader | 2 | 2 | `[]` |

n3 的 `nextIdx` 是 `{'n1': 1, 'n2': 3}`，`matchIdx` 是 `{'n1': 0, 'n2': 0}`。`compare variable` 不相等会 assert，全部通过，包括每步 `net-len`。

节点日志：

- `log.3`：`begin snapshot sli:2 slt:1`，随后 `becoming leader term:2`
- `log.1`：`loaded snapshot sli:2 slt:1`，`currentTerm` 从 2 变成 1
- `log.2`：`becoming leader term:1`

日志文件：`sandtable/build/mount/systems/WRaft-series/SpeculaWRaft/bugs/term_drop/test/log.host`

## 一次回放的输入和输出

1. TLC 读 `spec/MC_term.cfg`，模块是 `spec/MC_term.tla`（展开 `MC.tla`、`base.tla`）。必须带 `-tool`。反例原文在 `sandtable/systems/WRaft-series/SpeculaWRaft/bugs/term_drop/MC.out`。普通 TLC 的 `State 1:` 文本 `trace_reader.py` 不认。
2. `scripts/docker_rsync.sh` 把 `sandtable/systems` 和 `sandtable/scripts` 同步到 `sandtable/build/mount`。容器里的 `/root/sandtable` 就是这个目录。
3. `sudo docker exec controller .../SpeculaWRaft/scripts/run_one_testcase.sh <MC.out> 3`。第二个参数是节点数，要和模型里的 `Server` 一样大。脚本在 `bugs/term_drop/test/` 写出 `config/config.txt` 和 `traces.txt`。
4. `testcase_generator.py` 读 MC.out 和 config，写出 `traces.txt`。controller 执行这份文件。节点 stdout 在 `log.1`、`log.2`、`log.3`，controller 日志在 `log.host`。`compare variable` 失败会 assert。

## pc、seq 与 100 条随机轨迹

`spec/base_for_sandtable.tla` 在 base 的动作之外增加 `scr`。`Sand*` 动作给发出的消息盖 `seq = nSent+1, +2, ...`，并把 `scr.pc` 写成 `<<"Timeout", i>>` 或 `<<"HandleRequestVoteRequest", 接收者, 发送者, seq>>` 这种元组。`spec/MC_for_sandtable.tla` 的 `MCNext` 只包含这些 `Sand*` 动作。`scripts/testcase_generator.py` 看到状态里有 `scr` 就按 `pc` 发命令，`deliver-unordered` 直接用 `pc` 里的 `seq`。

用 `MC.cfg` 的界限（`SnapshotLimit=0` 等）对 `MC_for_sandtable` 做 100 个种子的模拟，深度到 12 层。100 条 `pc` 序列都不同，全部在 controller 里跑完。99 条 `compare variable` 通过。t098 在 Leader 收到更高任期的 RequestVote 时，代码不更新 `currentTerm`。覆盖率在第 74 条封顶：行 44.16%（507/1148），分支至少一次 29.41%（185/629）。快照、成员变更、日志压缩没有走到。明细在 `100条受控执行与覆盖率.md`。

为了在 interceptor 的 `_exit` 之前把 gcov 计数写出，`src/interceptor/router.cpp` 在关闭路由套接字时调用弱符号 `wraft_gcov_dump`。带 `--coverage` 的 `WRaftDriver` 才导出它。`start_docker.sh` 设置 `GCOV_PREFIX`。willemt 源码和 `WRaft.cpp` 没有改。

## 六种配置各 100 条

`MC.cfg`、`MC_hunt_commit.cfg`、`MC_hunt_broadcast.cfg`、`MC_hunt_log.cfg`、`MC_hunt_snapshot.cfg`、`MC_hunt_vote.cfg` 的界限各自写成 `MC_for_sandtable_*.cfg`，模块仍是 `MC_for_sandtable`。随机游走在 level 31 停下（最多 30 步）。600 条都做了受控执行。实现侧墙钟合计 1164.9 秒。变量全一致 528 条。71 条停在更高任期的 RequestVote（`raft_server.c:586` 不更新任期）。7 条最后 `net-len` 多 1。`log/t027` 的 TCP 连接在投递中途断开。

`Crash`、`Recover`、`Duplicate` 没有进入 `MCNext`：驱动没有崩溃命令，`duplicate` 只对 UDP。`SandLoseMessage` 只丢掉通道上唯一的那条消息。`HandleInstallSnapshot` 在这 600 条里没有出现，`raft_begin_load_snapshot` 未执行。

成功的 AppendEntries 响应会先提交再发送。`WireMsg` 改为带上发送时的提交点，否则跟随者看到的 `leader_commit` 偏小。

明细在 `全部建模配置受控执行.md`。第一轮数字在 `coverage-by-config-round1.json`。

## 第二轮：把可对齐的差异写进 Sand*

领导者收到 RequestVote 时，驱动不推进 `timeout_elapsed`（`WRaft.cpp` 的 `MSG_RV` 只对非领导者调用 `raft_periodic(election_timeout)`）。库因此走 `raft_recv_requestvote` 的租约拒绝，不改任期。`base.tla` 里这条分支本来就是非确定性的；`SandHandleRequestVoteRequest` 以前总是更新任期。现已在接收者是 Leader 时回复 not granted，任期不变。

`raft_end_snapshot` 在领导者上会给 `next_idx < snapshot_last_idx` 的每个 peer 发 InstallSnapshot。`SandTakeSnapshot` 以前不记这些发送，所以 `net-len` 比代码少 1。现已按 peer 名字顺序把这些消息盖进同一步。

一条含两次 `TakeSnapshot` 的快照配置轨迹已经整段比完（`bugs/random/snap_smoke2`）。六种配置第二轮 600 条变量比较全部通过，实现侧合计 1204.3 秒。

把随机游走加长到 80 步后，`nextIndex` 等于 `snapshotLastIdx` 时 `EntriesFrom` 仍把快照之后的日志整段放进 AppendEntries。`log_get_from_idx` 在 `idx <= base` 时返回 0 条。深轨迹 `bugs/random/deep/s001` 因此在第 61 步对不上：模型给 n2 两条日志，代码仍是一条。`EntriesFrom` 已改成这种情况发空消息。第三轮六种配置各 100 条变量比较全部通过，实现侧合计 1203.3 秒。数字在 `coverage-by-config.json`，第二轮留在 `coverage-by-config-round2.json`。30 步随机游走仍然没有 `HandleInstallSnapshot`。

`log/t027` 是投递中途 TCP 断开，不是协议赋值差异。原文在 `potential-bugs/log-t027-tcp-drop/`。

## 日志配置 2000 条（新机器重放）

同一批 `MC.out`（`MC_for_sandtable_log.cfg`，30 步）在新机器上重放。2000 条变量比较全部通过，没有 `net-len` 偏差，实现侧合计 6144.7 秒。行覆盖在第 1420 条封顶，62.46%（717/1148），分支 49.76%。第 919 条执行到 `raft_server.c:495` 的日志删除；`:467` 和 `raft_begin_load_snapshot` 仍是 0。分类在 `未覆盖代码分类.md`，逐行 gcov 在 `coverage-log2000-gcov/`，曲线在 `coverage-log2000-rerun.json`。

## 文件清单

### 仍在树上的新增文件

| 路径 | 作用 |
|---|---|
| `artifact/raft` | willemt/raft `e428eeb921a014192d1d703dd317f3f29f5916c5`。与 SandTable `driver/deps/WRaft` 的 `raft_server.c`、`raft_log.c`、`raft_private.h` 字节相同，没有替换 vendor 副本。 |
| `spec/MC_term.tla` | 上述 22 步调度。动作全是 `MC*` 包装。 |
| `spec/MC_term.cfg` | 界限与 `MC_hunt_vote.cfg` 同一类，`LoseLimit = 2`，`SnapshotLimit = 1`，检查 `TermNeverDecreases`。无对称归约。 |
| `spec/MC_witness.tla`、`spec/MC_hunt_commit_witness.cfg` | 第一轮：修复前的 `LeaderCompleteness`。不是代码 bug，留下作对照。 |
| `spec/MC_trace.tla`、`spec/MC_trace.cfg` | 第一轮那条 11 状态调度。 |
| `sandtable/systems/WRaft-series/SpeculaWRaft/scripts/env.sh` | 指向仓库 `scripts/env.sh`。 |
| `.../system_config.sh` | `partition_keep_msgs`、`allow_msg_unordered`。 |
| `.../start_docker.sh` | controller + n1 n2 n3，客户端是原来的 `WRaftDriver`。 |
| `.../run_one_testcase.sh` | 转调公共脚本。 |
| `.../testcase_generator.py` | 有 `scr.pc` 时按 pc 发命令，`seq` 直接作 `deliver-unordered` 的序号。没有 `scr` 的旧反例仍走状态差。 |
| `spec/base_for_sandtable.tla` | base 的副本加上辅助变量 `scr`、消息字段 `seq`，以及把发送折进同一步的 `Sand*` 动作。 |
| `spec/MC_for_sandtable.tla`、`spec/MC_for_sandtable.cfg` | `MCNext` 只含 `Sand*`。界限来自 `MC.cfg`，无对称归约，另有 `DepthBound`。 |
| `100条受控执行与覆盖率.md`、`coverage-100.json` | 100 条种子的比较结果和累计 gcov。 |
| `sandtable/src/interceptor/router.cpp` | `_exit` 前调用弱符号 `wraft_gcov_dump`，让覆盖率计数能写出来。 |
| `.../bugs/term_drop/MC.out` | 这次 TLC 反例。 |
| `.../bugs/stale_leader/MC.out` | 第一轮反例，对应的驱动补丁已撤回，不要再拿它当代码 bug 回放。 |

### 曾修改、已撤回

`sandtable/systems/WRaft-series/driver/deps/WRaft.cpp`：加过 `sendmode drop|pass`、`votemode manual|periodic`、`sendto`。用于压掉第一轮模型里没有的发送。现已 `git checkout` 回原文件，并在 controller 里按原文件重编了 `WRaftDriver`。

### 运行产物

`scripts/docker_rsync.sh` 同步到 `sandtable/build/mount`。回放日志在 `build/mount/systems/WRaft-series/SpeculaWRaft/bugs/term_drop/test/`。无约束 TLC 的 `spec/states/` checkpoint 已删。TLC 写在 `spec/` 下的 `*_TTrace_*` 已删。
