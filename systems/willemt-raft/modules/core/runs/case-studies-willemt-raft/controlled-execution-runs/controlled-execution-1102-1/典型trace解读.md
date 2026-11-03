# 六条典型轨迹

这六条是本轮已经采样并跑通的 TLC 轨迹里，按动作从少到多挑出来的。命令列表由 `testcase_generator.py` 按 `MC.out` 里的 `scr.pc` 生成，没有手写。手写的控制器命令没有模型状态，`compare variable` 对不上。

每一条都重新受控执行过，跑到最后一步，没有 `Variable ... compare failed`，也没有 `Net mgs length compare failed`。控制器读到的值和模型值相同。

记录在 `典型trace/<编号>/`：

| 文件 | 内容 |
|---|---|
| `MC.out` | TLC 模型轨迹，含每步的 `pc` 和全部模型变量 |
| `traces.txt` | 控制器命令全文。每一次读取、每一次 `compare` 都在这里 |
| `log.host` | 控制器实际跑出来的日志，含 `TRACE ... code= model=` |
| `n1.err` `n2.err` `n3.err` | 节点上驱动写到 stderr 的输出。崩溃那条里有 `PERSIST ...` |
| `stdout.txt` | 启动脚本的标准输出 |

`state` 的可见值：Follower 是 `1`，Candidate 是 `2`，Leader 是 `3`。节点名 `s1/s2/s3` 对应 `n1/n2/n3`。

## 怎么读一步

`traces.txt` 里从一个 `# [k]` 到下一个 `# [k]` 之前，就是这一步的全部控制器行为。结构固定：

1. 这一步真正碰系统或网络的命令（可能没有，例如丢包）。
2. 对 n1、n2、n3 各读 12 个变量。每个变量三行：`execute nX get <变量>`、`# variable <变量> sY <模型值>`、`compare variable`。
3. `# net-len <条数>` 和 `compare net-len`。条数是模型消息袋的大小。不相等只警告，这六条没有警告。
4. `status`。

轨迹 1 的第 2 步是最短的例子，后面每个节点还要继续把 12 个变量读完：

```text
# [2] Timeout s2
intercept n2 inc_time_ms 2000
execute n2 raft periodic 2000
execute n1 get commitIndex
# variable commitIndex s1 0
compare variable
execute n1 get currentTerm
# variable currentTerm s1 0
compare variable
```

`log.host` 里同一步会有 `TRACE commitIndex node=n1 code=0 model=0`。`code` 是驱动 `RaftGet` 的返回值，`model` 是上面 `# variable` 那一行。

## 动作覆盖

| 动作 | 第一次出现 |
|---|---|
| Init | 每一条的第 1 步 |
| Timeout | 01 第 2 步 |
| HandleRequestVoteRequest | 01 第 4 步（`lease`），第 10 步（`open`） |
| HandleRequestVoteResponse | 01 第 5 步 |
| ClientRequest | 02 第 8 步 |
| SendAppendEntries | 02 第 6 步 |
| HandleAppendEntriesRequest | 02 第 10 步 |
| HandleAppendEntriesResponse | 02 第 11 步 |
| LoseMessage | 03 第 9 步 |
| BroadcastAppendEntries | 03 第 19 步 |
| Crash | 04 第 4 步 |
| Recover | 04 第 7 步 |
| DuplicateMessage | 05 第 4 步 |
| TakeSnapshot | 06 第 36 步 |
| SendInstallSnapshot | 06 第 38 步 |
| HandleInstallSnapshot | 06 第 43 步 |

## 01 选举

`典型trace/01-election/`。来源 `standard/t0005`，种子 5，11 步。

s2 超时两次，成为 Candidate，任期从 0 到 1 再到 2。随后处理自己发出的投票请求和响应。`lease` 那几步不改可见状态。第 10 步是 `open`，s3 的任期变成 1，`votedFor` 变成 `n2`。这一条没有选出 Leader，s2 停在 Candidate（`state` 为 2）。Leader 出现在下一条的第 5 步。

| 步 | 变化 |
|---|---|
| 2 Timeout s2 | s2 变成 Candidate，任期 1，投票给 n2 |
| 3 Timeout s2 | s2 任期 2 |
| 4–9 投票请求/响应，模式是 lease | 可见状态不变 |
| 10 HandleRequestVoteRequest s3 s2 2 open | s3 任期 1，投票给 n2 |
| 11 响应 | 可见状态不变 |

投票请求的命令是先 `raft vote-mode lease` 或 `open`，再 `deliver-unordered`、等接收队列、`raft recvfrom`。响应没有 `vote-mode`，只有投递和 `recvfrom`。

## 02 客户端写入和点对点复制

`典型trace/02-client-replicate/`。来源 `standard/t0010`，种子 10，20 步。

s3 一次超时就当选。第 5 步 `state` 变成 3。第 6、7 步向 s1、s2 各发一次空的 AppendEntries。第 8 步客户端写入一条 `(1, 'v1')`，只出现在 s3 的日志里。第 15 步 s1 的日志才变成同样的一条。第 14 步 s2 又超时，任期 2，s3 退回 Follower。

| 步 | 变化 |
|---|---|
| 2 Timeout s3 | s3 Candidate，任期 1 |
| 3、4 投票请求 open | s1、s2 任期 1，投票给 n3 |
| 5 HandleRequestVoteResponse s3 s1 3 | s3 Leader |
| 6、7 SendAppendEntries | 只发消息，状态不变 |
| 8 ClientRequest s3 v1 | s3 日志 `[(1, 'v1')]` |
| 10–13 收发 AppendEntries | 这一段还没把日志写到 s1 |
| 14 Timeout s2 | s2 Candidate，任期 2 |
| 15 HandleAppendEntriesRequest s1 s3 7 | s1 日志 `[(1, 'v1')]` |
| 16 HandleRequestVoteRequest s3 s2 11 open | s3 退回 Follower，任期 2，投票清空 |

`ClientRequest` 的命令只有 `execute n3 raft cli v1`。库在这条调用里本来还会向同伴发 AppendEntries，驱动把这次内部发送挡住了，不进消息袋。真正的发送是后面单独的 `SendAppendEntries`。

## 03 广播，以及第一次丢包

`典型trace/03-broadcast/`。来源 `broadcast/t0002`，种子 2，31 步。广播配置允许丢包，所以 `LoseMessage` 比单独的丢包轨迹更早出现。

三次超时把 s3 的任期抬到 3。第 17 步 s3 成为 Leader。第 19 步广播只含 s2，命令是一次 `execute n3 raft send n2`。第 20 步 `pc` 是 `s3 s1,s2`，按 s1、s2 的顺序各发一次。第 21、25、26 步三次 `ClientRequest`，s3 的日志从 1 条长到 3 条，条目都是任期 3 的 `v1`。

丢包的命令是 `drop-unordered`，不调用 raft。第 9、11、13 步之后可见状态不变。被丢掉的那一封不再投递。

## 04 崩溃和恢复

`典型trace/04-crash-recover/`。来源 `install-deep/t0040`，种子 40，18 步。

s1 超时到任期 2 之后崩溃。s3、s2 各自超时。然后 s1 恢复。`n1.err` 里崩溃时写下：

```text
PERSIST term=2 vote=1 snap=0:0 log=[]
```

恢复之后 s1 的 `crashed` 回到 `FALSE`，`state` 是 Follower。任期仍是 2，所以表里没有任期这一列的变化。`commitIndex` 和 `lastApplied` 是 0。第 8、9 步丢掉 s1 崩溃前发出的两封投票请求。

| 步 | 变化 |
|---|---|
| 2、3 Timeout s1 | s1 Candidate，任期 1 然后 2 |
| 4 Crash s1 | `crashed` 为 TRUE。进程停了，容器还在。之后的 `get` 读冻结文件 |
| 5 Timeout s3 | s3 Candidate，任期 1 |
| 6 Timeout s2 | s2 Candidate，任期 1 |
| 7 Recover s1 | Follower，`crashed` 为 FALSE。任期、投票、日志从磁盘读回 |
| 15 响应 | s3 退回 Follower，任期 2 |
| 18 响应 | s2 退回 Follower，任期 2 |

崩溃的命令是 `execute n1 raft crash`。恢复是 `execute n1 raft recover`。

## 05 重复和丢失

`典型trace/05-lose-duplicate/`。来源 `log/t0027`，种子 27，21 步。

第 4 步 `DuplicateMessage s3 s1 3`，命令是 `duplicate-unordered n3 n1 3`。节点状态不变，消息袋里多一份。第 17 步和第 18 步的 `pc` 都是 `HandleRequestVoteRequest s1 s3 3 open`，也就是同一封公式消息投递两次。第一次 `deliver-unordered n3 n1 3`，第二次是 `deliver-unordered n3 n1 5`。控制器每投递一次就把那份捕获移走，复制时另外分配捕获序号，所以第二次的数字不是 3。中间的丢包和再次复制把后面的序号又挪了一位。

第 6 步丢的是公式序号 1，命令 `drop-unordered n1 n2 1`。第 15 步公式序号 8，命令已经是 `drop-unordered n3 n2 9`，同样是因为前面的复制把捕获序号推后了。

丢和重复都不改日志、任期和角色。能看见的效果是后面某一步还能不能 `deliver` 到这一份。

## 06 快照

`典型trace/06-snapshot/`。来源 `install-deep/t0004`，种子 4，45 步。前面 35 步把选举、崩溃恢复、丢包、广播、客户端写入和 AppendEntries 又走了一遍。快照相关的是这三步：

| 步 | 命令 | 变化 |
|---|---|---|
| 36 TakeSnapshot s1 | `execute n1 raft snapshot` | s1 日志变空，`snapshotLastIdx` 2，`snapshotLastTerm` 2。`lastApplied` 仍是 0 |
| 38 SendInstallSnapshot s1 s2 | `execute n1 raft send n2` | 可见状态不变。库发现同伴落后于快照，发出的是快照而不是日志 |
| 43 HandleInstallSnapshot s2 s1 30 | `deliver-unordered` 然后 `execute n2 raft recvfrom n1` | s2 的 `snapshotLastIdx` 2，`snapshotLastTerm` 2，`commitIndex` 2，`lastApplied` 2，`votedFor` 清空，日志仍空 |

第 40 步又向 s2 发了一次快照，状态不变。第 41 步 s1 在快照之后再写入一条，日志变成 `[(2, 'v1')]`。第 45 步 s2 收到这条，日志也变成一条。

`SendInstallSnapshot` 和 `SendAppendEntries` 的控制器命令都是 `raft send`。区别在库：`nextIndex` 落在快照之前时，`raft_send_appendentries` 改走快照回调。公式把这两件事分成两个 action，控制器一步只调用一次 send。

## 粒度

一步公式对应一次受控的命令串，然后三个节点各读 12 个变量。这六条上读到的值都和模型一致。

够细的地方：

- 超时只拨该节点 2000 毫秒，再调用一次 `raft_periodic`。别的动作不拨时钟。
- 收一封、发一封、丢一封、复制一封都是单独一步。广播是 `pc` 里列出的每个对端各一次 `raft send`，顺序固定为 s1、s2、s3。
- 客户端写入和随后的复制拆开。处理请求时，库回调里多出来的发送不进消息袋。投票回复和 AppendEntries 回复在库函数返回后由驱动按公式发出。装入快照的公式不发回复，驱动也不发。
- 崩溃停的是库服务器，不是容器。恢复只读磁盘副本，再把角色、`commitIndex`、`lastApplied` 按公式设回去。

同一条 `raft send` 覆盖了「发日志」和「发快照」两种公式动作。要看这一步发的是哪一种，看 `pc` 的名字，不看命令字符串。

复制和丢弃改的是控制器里的捕获序号。`pc` 末尾的数字是公式序号。`deliver-unordered` / `drop-unordered` / `duplicate-unordered` 上的数字是捕获序号，复制之后两者会岔开。轨迹 5 的第 17 步和第 18 步就是这个岔开。

## 引擎能读到的变量

每一步、每个节点，控制器都会读下面 12 个。值来自 `execute nX get <名字>`，驱动 `RaftGet` 把库内存格式化成字符串。节点已经崩溃时，读的是崩溃当时写好的冻结文件，不是停掉的进程。

| 变量 | 这六条里见过的取值 | 从哪读 |
|---|---|---|
| `commitIndex` | `0`，轨迹 6 里到过 `2` | `commit_idx` |
| `currentTerm` | `0` 起，轨迹 3 的 s3 到过 `3` | `current_term` |
| `log` | `[]` 或 `[(任期, 'v1'), ...]` | 日志数组里快照之后的条目。值存在条目指针的低位，所以只能看到 `v1` 这种短字符串 |
| `state` | `1` Follower，`2` Candidate，`3` Leader | `state` |
| `lastApplied` | 多数时候 `0`。轨迹 6 第 43 步 s2 变成 `2` | `last_applied_idx` |
| `votedFor` | `Nil`，或 `n1`/`n2`/`n3` | `voted_for`。空投票在模型里是 `Nil` |
| `votesGranted` | `{}` 或 `{n1,n2}` 这种 | 哪些节点的 `vote_for_me` 为真 |
| `snapshotLastIdx` | `0`，轨迹 6 里到过 `2` | `snapshot_last_idx` |
| `snapshotLastTerm` | `0`，轨迹 6 里到过 `2` | `snapshot_last_term` |
| `crashed` | `FALSE`，崩溃后到恢复前是 `TRUE` | 进程还在就是 FALSE。崩溃后冻结文件里写成 TRUE |
| `nextIndex` | `{'n1': 1, 'n2': 1, 'n3': 1}` 这种 | 每个 `raft_node` 的 `next_idx` |
| `matchIndex` | 同样的字典 | 每个节点的 `match_idx` |

然后读一次消息袋长度，标签是 `net-len`。它不是节点变量，是控制器自己数的捕获条数和模型消息袋大小。这六条两边相等。

读不到、也不比较的有：选举超时已经走了多少、`current_leader`、某一封消息的字段、状态机里应用过的字符串。轨迹结尾有 `execute nX raft statemachine`，只是打印，没有 `compare`。

每个变量在库里的读取函数、崩溃时改读冻结文件的路径，写在 `修改文件具体介绍.md`。
