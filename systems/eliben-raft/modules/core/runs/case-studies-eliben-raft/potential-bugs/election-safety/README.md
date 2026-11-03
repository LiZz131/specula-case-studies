# 同一任期两名领导者

6 条。比较没有在 `state` 上失败：代码和模型都是两名领导者，任期相同。归类：`bug`。`standard` 的 t0090 后来又在 `nextIdx` 上失败，那一条另记在 `nextindex-reply/`。

协议：一个任期最多一名领导者。旧任期的投票不能算进新任期。同一任期内 `votedFor` 不能被清掉再投给别人。

库有两条路径，都在这批轨迹里发生了。

`controlled.go` 的 `onVoteReply` 用发出 RequestVote 时记下的 `savedCurrentTerm` 和 `reply.Term` 比较，不用节点现在的 `currentTerm`。节点已经进入更高的任期、状态仍是 Candidate 时，旧应答仍然被算进 `ctrlGrants`。`BecomeLeader` 看到的多数票里就有这张旧票。

`raft.go` 的 `becomeFollower` 每次都把 `votedFor` 写成 -1，任期没有变也清。同一任期的 AppendEntries 会走到这里。

`f1a` t0043 的模型轨迹：

1. s3 在任期 2 把票投给 s2。
2. s2、s3 各自再超时，进入任期 3，各投给自己。
3. s2 的 `votesGranted` 仍含有 s3 在任期 2 的那张票。`BecomeLeader s2` 让 s2 成为任期 3 的领导者。
4. s1 再把任期 3 的票投给 s3。`# [22] BecomeLeader s3` 之后 n2 和 n3 的 `state` 都是 2，`currentTerm` 都是 3。代码和模型相同。

`standard` t0041 在两名领导者出现之后，同一任期的 AppendEntries 把 `votedFor` 清成 Nil，任期仍是 2。这是 `becomeFollower` 在任期不变时清票。控制器日志从 `# [20]` 才保留下来，两名领导者的比较在 `# [19] BecomeLeader s3`，代码和模型在之后仍能对上，说明这一步代码也写成了两名领导者。

建议修改对准协议，不是对准模型值。模型里的两名领导者就是这次违规的结果。`reply.Term` 要和 `currentTerm` 比；只有任期真的变了才把 `votedFor` 清掉。

`KNOWN`。[PR #27](https://github.com/eliben/raft/pull/27) 修的就是这两处，2026-03-30 合并。投票应答和 `savedCurrentTerm` 的问题记在 [issue #25](https://github.com/eliben/raft/issues/25)。被测协议代码来自 `d85b35cef3da8bde6c863b9231559e61b1542805`（2025-01-29），早于这个 PR。`artifact/raft` 把应答处理抽进了函数，比较的仍是 `savedCurrentTerm`。

| 轨迹 | 步 | 代码和模型 |
|---|---|---|
| standard-t0041 | `# [19] BecomeLeader s3` | n1 与 n3，任期 2 |
| standard-t0090 | `# [17] BecomeLeader s1` | n1 与 n3，任期 2 |
| f1a-t0043 | `# [22] BecomeLeader s3` | n2 与 n3，任期 3 |
| f1a-t0094 | `# [27] BecomeLeader s3` | n1 与 n3，任期 2 |
| f1a-t0096 | `# [20] BecomeLeader s3` | n2 与 n3，任期 2 |
| f2a-t0079 | `# [30] BecomeLeader s2` | n1 与 n2，任期 2 |

## 复现

节点数 3。先把该目录的 `MC.out` 拷到挂载盘。容器里看不到 `potential-bugs/`。

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/election-safety/standard-t0041/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/election-safety/standard-t0090/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/election-safety/f1a-t0043/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/election-safety/f1a-t0094/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/election-safety/f1a-t0096/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/election-safety/f2a-t0079/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```

t0090 会先在 `# [17]` 成为两名领导者，再在后面的 `HandleAppendEntriesResponse` 上因 `nextIdx` 停住。其余五条比较能走完。期望看到的是一名领导者，不是模型里的两名。
