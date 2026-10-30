# Specula 到 SandTable：需要的上下文和建议流程

协议规格在 `spec/base.tla`，动作公式没有改。SandTable 受控执行用的是另写的 `spec/base_for_sandtable.tla`：它复制 base 的动作，再加辅助变量 `scr`（`pc` 和 `nSent`）以及消息字段 `seq`。`MCNext` 只走把发送折进同一步的 `Sand*` 动作，这样 `scr.pc` 里的 `seq` 就是 TCP 捕获序号。`base.tla` 不引用这个文件。

100 条随机轨迹的回放和覆盖率写在 `100条受控执行与覆盖率.md`。

## 什么算代码级 bug

模型检查报错分两类。

- 不变式比实现和论文都强。`MC_hunt_commit` 的过期 Leader 就是这种：实现会进入那个状态，但它不是缺陷，修的是不变式。
- 实现动作和模型动作一致，并且违反的是实现自己应该守的性质。任期只增不减是这种。`HandleInstallSnapshot` 把 `currentTerm` 设成 `msnapshotLastTerm`，库函数把 `current_term` 设成 `last_included_term`。两边是同一个赋值。

回放之前先对一下违反点是不是库里的那一行，而不是只对一下“TLC 报了错”。

## 不要改的东西

- `base.tla` / `MC.tla` 里的动作公式。调度可以放在新模块里，用 `step` 挑选已经存在的析取，包括 `LoseMessage`。
- willemt/raft 源码。SandTable 的控制面是进程边界：按序号投递、推进虚拟时钟、调用 driver 里已经有的 `periodic` / `cli` / `snapshot` / `recvfrom`，以及 controller 的 `clear`。
- 为了让某条轨迹好跑而给 driver 加开关。第一轮加过 `sendmode`，已经撤回。库存驱动的默认行为就是要测的行为。

如果一条轨迹只能靠改库或改 driver 才能走通，先停下来写报告，不要先改。

## 动作边界怎么对齐

Specula 把“改本地状态”和“发送”拆开。库经常在同一个函数里做完两者：`raft_become_leader` 会广播，`raft_recv_entry` 在 `next_idx == current_idx` 时会发送，AppendEntries 失败处理会立刻再发一次，这次在 `next_idx < snapshot_last_idx` 时发的是快照。

这些多出来的发送已经进了 TCP 拦截队列。`drop` 只对 UDP 有效。TCP 上可用的是 `clear src dst`，它清掉整条通道，序号表不重排，所以后面的 `deliver-unordered` 仍用原来的捕获序号。

`clear` 只能用在“这条通道上的消息全是模型没有的”时候。若通道里还有模型要保留的 RequestVote，先在调度里用已有的 `LoseMessage` 丢掉它，再清通道。这不改变动作语义，只是选了一条不投递该消息的行为。

模型比代码晚一步才出现的消息（失败步发出的快照，模型写在下一步的 `SendInstallSnapshot`）处理成：本步 `clear`，下一步用库存命令再发一次。Leader 上 `raft periodic 200` 会走 `raft_send_appendentries_all`。该函数在第一个需要快照的节点处返回，因此只发出一份快照，和模型的单目的地发送一致。`periodic` 必须带毫秒数；不带参数时用墙上时钟。

`compare variable` 不等会 assert。`compare net-len` 只警告，所以条数也要逐项看日志，不能只看进程没崩。

## 任意 trace 到受控执行

SandTable 自带生成器依赖 `scr.pc`。这份模型不加这个变量。`sandtable/systems/WRaft-series/SpeculaWRaft/scripts/testcase_generator.py` 用状态差代替它：

- `counters.timeout / request / lose / snapshot / broadcast` 加一，对应 Timeout、ClientRequest、LoseMessage、TakeSnapshot、BroadcastAppendEntries。谁变了，看 term、log、快照点或新消息的 `msource`。
- counters 没变时，看 bag 里消失和出现的消息类型，对应 Handle*、SendAppendEntries、SendInstallSnapshot。
- 每步按 `raft_server.c` 的发送点预测捕获序号。节点顺序是 `std::set<Node>` 的名字序，`sN` 映射成 `nN` 后 `n1 < n2 < n3`。
- 模型多出来的消息还在队列里、代码却没发过：用 `raft periodic 200` 走 `raft_send_appendentries_all`。它按名字序发送，遇到第一个需要快照的 peer 就返回。模型要的目的地不是这次发送的前缀时，生成器退出。
- 代码多出来的消息：该通道上若只有这些消息，`clear`；若还有模型要留的消息，生成器退出。
- 每步比较 `commitIdx`、`currentTerm`、`log`、`state`，Leader 再比 `nextIdx`、`matchIdx`，以及 `net-len`。期望值来自 TLC 状态，不是手写的。

输入是 TLC `-tool` 写出的 MC.out（文件以 `@!` 开头）。`trace_reader.py` 把空 bag `<<>>` 解析成空列表。输出是 `traces.txt`。`run_one_testcase.sh` 把这两步和 docker 串起来。节点数参数必须等于 `Cardinality(Server)`。

做不到、并且不会改源码去凑的轨迹：

- 同一条 TCP 通道上既要丢掉一条、又要留下另一条。`drop` 只对 UDP。`clear` 清整条通道。过期 Leader 那条反例在第 5 步就是这种情况。
- `DuplicateMessage`。模型 bag 里有两份，TCP 捕获队列里只有一份，`deliver-unordered` 会把它从通道里拿走。
- `Crash` / `Recover`。`RaftRepl` 没有对应命令。
- 发送方当前 term 小于接收方时的 `HandleInstallSnapshot`。驱动在进 `raft_begin_load_snapshot` 之前就返回，模型仍会装上快照。
- 投票处理前驱动会 `raft_periodic(election_timeout)`。随机超时等于 1000 时会多一次选举，大约 1/1000。生成器不覆盖这次分叉。

生成器退出码非 0，并且不把半份 `traces.txt` 交给 controller。

## 建议流程

1. 固定 Specula 用的源码提交，和 driver 链接的库做哈希比较。相同就不要换 vendor 树。
2. 从 bug report 里分开“不变式过强”和“实现赋值”。后者才进入回放。
3. 用 TLC `-tool` 跑。无约束 BFS 太大时，另写一个模块，用 `step` 从 `MCNext` 里挑已有析取。不要改 `base.tla` / `MC.tla`。投票步约束 `votedFor'`，避开租约拒绝那条过近似。
4. 把 MC.out 放到 `SpeculaWRaft/bugs/<name>/MC.out`，`docker_rsync.sh` 之后在 controller 里跑 `run_one_testcase.sh <MC.out> <节点数>`。
5. 生成器拒绝时，看它打印的通道和动作。能用已有的 `LoseMessage` 把那条通道腾空，就改调度再跑 TLC。不能，就停下来写报告。
6. `log.host` 里没有 `compare failed`，并且最后一态就是性质被违反的那一态，这条对应才成立。`compare net-len` 只警告，所以要看生成器自己的队列断言，它在写出 `traces.txt` 之前已经做了。

## 这次特意避开的分叉

- 租约拒绝是模型对 `current_leader` 的过近似。调度约束 `votedFor'`，只走授予分支。库存的投票前 `raft_periodic(election_timeout)` 会把 `timeout_elapsed` 加上 1000；选举超时随机值在 `[1000, 2000)`，所以通常不会因此另起选举。显式超时用 `periodic 2000`，一定能过这个随机阈值。
- 快照 RPC 的驱动检查比的是发送方当前 term，不是 `last_included_term`。发送方 term 2、接收方 term 2、快照 term 1 时检查放行，随后库把任期写成 1。这才是可复现的下降，而不是“模型不看 `mterm`、代码会拒绝”的那种下降。
- `HandleInstallSnapshot` 不产生响应，驱动会发一条 AppendEntries 响应。比较前清掉它。任期在 `recvfrom` 里已经写成 1，清的是响应，不是任期。
