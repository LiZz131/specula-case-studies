# 投票应答把当前任期拉低

8 条，都在 `f2a`。比较通过：代码和模型的 `currentTerm` 一起变小，`persistedTerm` 停在原来的值。归类：`bug`。

协议：服务器不接受比自己更小的任期。一张旧选举的 RequestVote 应答不能把节点拽回那个任期。

`f2a` t0003，`# [16] HandleRequestVoteResponse s3 s2 14`。这一步之前 n3 是任期 3 的候选人，`votedFor` 是 3，`persistedTerm` 是 3。这一步之后 n3 的 `currentTerm` 是 2，`votedFor` 是 -1，状态是 Follower，`persistedTerm` 仍是 3。代码和模型相同。

`onVoteReply`（`controlled.go`）在 `reply.Term > savedCurrentTerm` 时调用 `becomeFollower(reply.Term)`。`savedCurrentTerm` 是这条 RequestVote 发出时的任期，不是节点现在的任期。应答任期落在两者中间时，`becomeFollower` 把 `currentTerm` 写成应答任期，并把 `votedFor` 清成 -1。这条路径不调用 `persistToStorage`，所以持久化任期留在 3，当前任期变成 2。`PersistedTermConsistency` 要求持久化任期不超过当前任期，这里被打破。更直接的规则是任期不能回退。

建议修改：用 `currentTerm` 判断这张应答，应答任期不大于当前任期就忽略。模型写下的任期 2 不是修补目标。协议要求 n3 留在任期 3。

`KNOWN`。同一处比较在 [issue #25](https://github.com/eliben/raft/issues/25)。[PR #27](https://github.com/eliben/raft/pull/27) 改成和 `cm.currentTerm` 比较，2026-03-30 合并。被测代码来自 `d85b35cef3da8bde6c863b9231559e61b1542805`，早于这个 PR。

| 轨迹 | 步 | 代码和模型 |
|---|---|---|
| f2a-t0003 | `# [16] HandleRequestVoteResponse s3 s2 14` | n3 持久任期 3，当前任期 2 |
| f2a-t0012 | `# [14] HandleRequestVoteResponse s1 s2 15` | 同上，落在 n1 |
| f2a-t0026 | `# [14] HandleRequestVoteResponse s3 s1 15` | 落在 n3 |
| f2a-t0044 | `# [16] HandleRequestVoteResponse s1 s3 15` | 落在 n1 |
| f2a-t0056 | `# [17] HandleRequestVoteResponse s3 s1 16` | 落在 n3 |
| f2a-t0060 | `# [11] HandleRequestVoteResponse s3 s1 13` | 落在 n3 |
| f2a-t0062 | `# [13] HandleRequestVoteResponse s3 s1 14` | 落在 n3 |
| f2a-t0086 | `# [13] HandleRequestVoteResponse s1 s2 14` | 落在 n1 |

## 复现

节点数 3。先把该目录的 `MC.out` 拷到挂载盘。

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/term-regression/f2a-t0003/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/term-regression/f2a-t0012/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/term-regression/f2a-t0026/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/term-regression/f2a-t0044/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/term-regression/f2a-t0056/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/term-regression/f2a-t0060/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/term-regression/f2a-t0062/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/term-regression/f2a-t0086/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```

期望这一步之后该节点的当前任期保持不变，而不是变成 2。
