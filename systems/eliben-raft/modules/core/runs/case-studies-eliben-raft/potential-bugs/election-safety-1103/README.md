# 同一任期两名领导者

4 条。比较没有在 `state` 上失败：代码和模型都是两名领导者，任期相同。归类：`bug`。

协议：一个任期最多一名领导者。旧任期的投票不能算进新任期。

`controlled.go` 的 `onVoteReply`（约 30–40 行）用发出 RequestVote 时记下的 `savedCurrentTerm` 和 `reply.Term` 比较，不用节点现在的 `currentTerm`。节点已经进入更高的任期、状态仍是 Candidate 时，旧应答仍然被算进投票集合。`BecomeLeader` 看到的多数票里就有这张旧票。

`raft.go` 的 `becomeFollower`（533–537 行）每次都把 `votedFor` 写成 -1，任期没有变也清。

建议修改对准协议，不是对准模型值。模型里的两名领导者就是这次违规的结果。`reply.Term` 要和 `currentTerm` 比；只有任期真的变了才把 `votedFor` 清掉。

`KNOWN`。[PR #27](https://github.com/eliben/raft/pull/27) 修的就是这两处，2026-03-30 合并。投票应答和 `savedCurrentTerm` 的问题记在 [issue #25](https://github.com/eliben/raft/issues/25)。被测代码早于这个 PR。

| 轨迹 | 步 | 代码和模型 |
|---|---|---|
| f1a-t0043 | `# [25] BecomeLeader s3` | n2 与 n3，任期 3 |
| f1a-t0094 | `# [27] BecomeLeader s3` | n1 与 n3，任期 2 |
| f1a-t0096 | `# [20] BecomeLeader s3` | n2 与 n3，任期 2 |
| f1b-t0061 | `# [24] BecomeLeader s3` | n2 与 n3，任期 2 |

## 复现

节点数 3。容器里看不到 `potential-bugs/`。先把该目录的 `MC.out` 拷到挂载盘，再执行。期望在表里的那一步之后，两个节点的 `state` 都是 2，任期相同。协议要求这一步只有一名领导者。

```text
sudo cp <本目录>/<轨迹>/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
