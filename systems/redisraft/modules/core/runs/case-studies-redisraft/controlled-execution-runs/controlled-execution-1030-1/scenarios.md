# 交回 spec_generation 的场景

轮次 `controlled-execution-1030-1`。下面每段都是 E，或者 A 里对不上本轮可执行动作的赋值。不在 `Sand*` 里补协议。加长 `DepthBound` 或在现有五份 cfg 上加种子走不到这些路径：`MCNext` 里没有对应动作，stock 驱动也没有命令。

单节点和日志扩容不在这里。它们的守卫在现有变量上，下一步是另开配置，写在 `未覆盖代码分类.md`。

## 快照和日志压缩

读写 `snapshotLastIdx`、`snapshotLastTerm`、`logOffset`，以及落后节点的 `nextIndex`。守卫是已经执行 `TakeSnapshot` 或 `HandleInstallSnapshot`，并且某个节点的 `nextIndex` 不大于快照点。

现有 `Value` 只有普通条目 `v`。`MCNext` 没有 `TakeSnapshot`、`SendInstallSnapshot`、`HandleInstallSnapshotRequest`、`EndLoadSnapshot`。驱动没有快照命令，快照回调是空的。500 条 30 步轨迹里快照点保持 0，`raft_log_poll` 和 `raft_begin_load_snapshot` 一次都没进入。

因此这些行的赋值对不上本轮能采样的动作：`raft_log_load_from_snapshot` 改 `base`，`raft_end_snapshot` 提交快照点并丢掉前缀，`raft_begin_load_snapshot` 重设任期、提交点和日志，快照传完后把对方 `next_idx` 设成快照点加一。

## 成员变更

读写节点表、投票权、`votingCfgChangeIdx`。守卫是日志里出现 `AddNode`、`AddNonVotingNode` 或 `RemoveNode`，或者集群里有非投票节点被追平。

规格里有 `ProposeAddServer`、`ProposeRemoveServer`。本轮 `MCNext` 没有这两条。客户端条目只有 `v`，产生不了配置条目。驱动没有成员变更命令。

未执行的是增删节点、把已有非投票节点提升为投票节点、`has_sufficient_logs`，以及「同时只允许一个投票权变更」。删掉当前领导者时把 `leader_id` 清掉的那两行是 A，同样因为删除节点这个动作不在 `MCNext` 里。

三个初始节点的 `raft_add_node` 属于初始化，已经执行。上面这些是运行期成员变更。

## 非法定人数读

读写读队列和各节点确认过的 `msg_id`。守卫是：调用者是领导者，读队列非空，已提交当前任期，并且法定人数确认了该 `msg_id`。

规格里有 `ClientNonQuorumRead`，以及 `staleReadDetected`、`noopReadDetected`。`MCNext` 没有读动作。驱动的读回调是 `assert(false)`。

`raft_process_read_queue` 被空队列调用过，非空队列上的放行没走到。`raft_recv_read_request`、`pop_read_queue`、`quorum_msg_id` 没有在有读请求时执行。

## PreVote

读写一个不属于 `Follower` / `Candidate` / `Leader` 的 pre-candidate 状态，并在请求上置 `prevote`。守卫是选举超时，且不跳过 pre-candidate。

规格没有这个状态，也没有 prevote 消息。驱动对非领导者的超时调用 `raft_election_start(me, 1)`，实参恒为 1，`raft_become_precandidate` 整段未执行。库自己的 `raft_periodic_internal` 在超时分支调用 `raft_election_start(me, 0)`，那一臂也没走到，因为超时命令没有走那条入口。

要覆盖必须先在规格里写出 PreVote，或者明确接受驱动跳过。本轮不改 `Sand*` 去调用 `raft_become_precandidate`。

## Check-quorum 卸任

读写角色和领导者。守卫是领导者的 `quorum_timeout` 降到 0，且本轮法定 `msg_id` 没有前进。

规格没有「法定人数心跳丢失就卸任」。驱动在 `RaftInit` 里把选举超时设成 1000000 毫秒，库的 `quorum_timeout` 是它的两倍。30 步里单步最大 2000 毫秒，累计到不了这个期限。若把选举超时改回 1000 毫秒，实现会走出规格没有的卸任，所以不能靠改驱动超时来覆盖。

## 领导权转移和 TimeoutNow

读写转移目标。守卫是领导者调用转移，目标的 `matchIndex` 追上当前日志后发送 TimeoutNow；超时则放弃。

规格的动作列表里没有转移领导者，也没有 TimeoutNow。`raft_transfer_leader` 和 `raft_timeout_now` 未执行。`raft_reset_transfer_leader` 只走到「没有转移目标就返回」。

## 崩溃后恢复任期和投票

读写 `currentTerm` 和 `votedFor`。守卫是执行 `Crash` 之后再恢复持久化元数据。

规格里有 `Crash`。`MCNext` 没有，驱动也没有崩溃命令。`raft_restore_metadata` 未执行。`raft_clear` 同时是销毁路径，分类在 D，不在这里重复成采样任务；那条路径没被执行，资源泄漏这次覆盖率看不出来。
