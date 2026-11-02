# 交回 spec_generation 的场景

轮次 `controlled-execution-1102-1`。下面是 E，以及 A 里对不上 `base.tla` 赋值的生产路径。不在 `Sand*` 里补协议。单节点、日志扩容、prev 任期冲突、快照之后的崩溃，守卫都在现有变量上，下一步是另开配置或加见证，写在 `未覆盖代码分类.md`。

## PreVote

读写一个不属于 `Follower` / `Candidate` / `Leader` 的 pre-candidate，并在请求上置 `prevote`。守卫是选举超时且不跳过 pre-candidate。

`base.tla` 的 `Timeout` 直接成为 Candidate。驱动调用 `raft_election_start(me, 1)`，`raft_become_precandidate` 不执行。要覆盖必须先在规格里写出 PreVote。

## 非投票成员

读写 `ADD_NONVOTING_NODE`、`has_sufficient_logs`、addition-committed。守卫是日志里出现非投票节点，或一个非投票节点被追平后提升。

`base.tla` 的配置条目是一整份服务器集合，只有加入和移除，没有非投票身份。驱动只发 `ADD_NODE` 和 `REMOVE_NODE`。

## 库内读队列

读写读队列和各节点的 `msg_id`。守卫是领导者、队列非空、已提交当前任期，并且法定人数确认了该 `msg_id`。

`ClientNonQuorumRead` 已执行。它比较的是各节点 `commitIndex` 和「当前任期是否已提交」，旗标在驱动里。库的 `raft_recv_read_request` 没有被调用，因为这份 artifact 的 raft 库上面没有 redis 读路径。规格没有 `msg_id`。

## 领导者转移

读写 `node_transferring_leader_to` 和 TimeoutNow。`base.tla` 没有转移领导者这个动作。

## 规格明确不改、开关关掉的生产赋值

这些行改的是规格里已有的变量，但对应的 `base.tla` 动作把它们标成不变，或者把该效果拆到另一个 action：

- `AppendEntries` 不改 `nextIndex`。生产的 `raft_send_appendentries` 在送出后推进 next，并在循环里继续送。
- `BecomeLeader` 不发送、不提交。生产会立刻 `raft_send_appendentries`，单节点还会提交。
- `HandleRequestVoteResponse` 只记票。生产在票数够时调用 `raft_become_leader`。
- `TakeSnapshot` 不发送。生产的 `raft_end_snapshot` 会接着发 InstallSnapshot。
- `HandleInstallSnapshotRequest` 不删除其它节点的 next/match。生产的 `raft_begin_load_snapshot` 会释放其它节点。
- 提交 REMOVE 时生产调用 `raft_remove_node`。规格的 `nextIndex` 和 `matchIndex` 对离开配置的服务器仍有定义。

`specula_step` 为 1 时这些路径不走。不为了盖住这些行去关掉开关，否则 code 会离开 `base.tla`。
