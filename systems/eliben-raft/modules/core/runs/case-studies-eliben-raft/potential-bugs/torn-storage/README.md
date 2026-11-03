# 只写下任期之后恢复失败

公式修改记在 `controlled-execution-runs/controlled-execution-1102-1/spec-repairs.md`。这一轮不作为交付。

90 条。动作是 `PartialPersist`。归类：`spec`。

`MCPartialPersist` 把 `persistedTerm` 写成当前任期，然后把节点恢复成一个活着的 Follower：`votedFor` 取还没更新的 `persistedVotedFor`，日志不变。库做的是另一件事。`ControlledPersistTermOnly` 只调用 `writeCurrentTerm`，然后用同一目录新建 `ConsensusModule`。目录里已经有文件，`HasData` 为真，`restoreFromStorage` 要求 `currentTerm`、`votedFor`、`log` 三个键都在。后两个键还没写过，于是 `log.Fatal`。节点日志是 `votedFor not found in storage`，位置在 `raft.go` 的 `restoreFromStorage`。控制器接着读到的 `commitIdx` 是空的，因为进程已经退出。

这次退出没有在同一任期里再投一票。协议不要求节点带着缺键的存储继续运行。公式恢复出来的那个 Follower 也不是协议要求的结果，它带着过期的 `votedFor`。不要改 `restoreFromStorage` 去凑这个状态。

要改的是 `MC_for_sandtable.tla` 的 `MCPartialPersist`，以及它对应的 `MC.tla` 里的 `PartialPersist`：只有 `currentTerm` 被写到存储里时，恢复不是一个活着的 Follower。`base.tla` 的 `Crash` 不用改，它恢复的是三个键都已经写过的状态。

| 轨迹 | 步 |
|---|---|
| f1b-t0003 | `# [6] PartialPersist s3` |
| f1b-t0004 | `# [3] PartialPersist s2` |
| f1b-t0005 | `# [9] PartialPersist s3` |
| f1b-t0009 | `# [6] PartialPersist s3` |
| f1b-t0010 | `# [8] PartialPersist s3` |
| f1b-t0011 | `# [7] PartialPersist s1` |
| f1b-t0012 | `# [3] PartialPersist s1` |
| f1b-t0016 | `# [5] PartialPersist s1` |
| f1b-t0018 | `# [2] PartialPersist s2` |
| f1b-t0019 | `# [7] PartialPersist s3` |
| f1b-t0020 | `# [2] PartialPersist s1` |
| f1b-t0021 | `# [4] PartialPersist s3` |
| f1b-t0022 | `# [6] PartialPersist s2` |
| f1b-t0024 | `# [5] PartialPersist s2` |
| f1b-t0027 | `# [4] PartialPersist s3` |
| f1b-t0029 | `# [2] PartialPersist s2` |
| f1b-t0031 | `# [4] PartialPersist s1` |
| f1b-t0036 | `# [2] PartialPersist s1` |
| f1b-t0037 | `# [5] PartialPersist s3` |
| f1b-t0039 | `# [5] PartialPersist s2` |
| f1b-t0040 | `# [4] PartialPersist s2` |
| f1b-t0043 | `# [4] PartialPersist s1` |
| f1b-t0046 | `# [6] PartialPersist s2` |
| f1b-t0047 | `# [4] PartialPersist s3` |
| f1b-t0048 | `# [5] PartialPersist s1` |
| f1b-t0050 | `# [6] PartialPersist s3` |
| f1b-t0053 | `# [6] PartialPersist s2` |
| f1b-t0055 | `# [9] PartialPersist s1` |
| f1b-t0057 | `# [4] PartialPersist s3` |
| f1b-t0059 | `# [3] PartialPersist s3` |
| f1b-t0061 | `# [3] PartialPersist s3` |
| f1b-t0066 | `# [2] PartialPersist s3` |
| f1b-t0069 | `# [3] PartialPersist s1` |
| f1b-t0072 | `# [3] PartialPersist s1` |
| f1b-t0082 | `# [6] PartialPersist s2` |
| f1b-t0085 | `# [4] PartialPersist s3` |
| f1b-t0086 | `# [7] PartialPersist s3` |
| f1b-t0090 | `# [2] PartialPersist s2` |
| f1b-t0092 | `# [3] PartialPersist s3` |
| f1b-t0093 | `# [7] PartialPersist s3` |
| f1b-t0094 | `# [8] PartialPersist s2` |
| f1b-t0095 | `# [4] PartialPersist s1` |
| f1b-t0096 | `# [4] PartialPersist s1` |
| f1b-t0098 | `# [3] PartialPersist s2` |
| f1c-t0001 | `# [3] PartialPersist s1` |
| f1c-t0004 | `# [3] PartialPersist s2` |
| f1c-t0005 | `# [9] PartialPersist s3` |
| f1c-t0008 | `# [4] PartialPersist s3` |
| f1c-t0009 | `# [5] PartialPersist s3` |
| f1c-t0011 | `# [3] PartialPersist s1` |
| f1c-t0016 | `# [5] PartialPersist s1` |
| f1c-t0020 | `# [2] PartialPersist s1` |
| f1c-t0021 | `# [4] PartialPersist s3` |
| f1c-t0024 | `# [5] PartialPersist s2` |
| f1c-t0027 | `# [4] PartialPersist s3` |
| f1c-t0029 | `# [2] PartialPersist s2` |
| f1c-t0031 | `# [4] PartialPersist s1` |
| f1c-t0034 | `# [3] PartialPersist s2` |
| f1c-t0036 | `# [2] PartialPersist s1` |
| f1c-t0037 | `# [4] PartialPersist s1` |
| f1c-t0040 | `# [3] PartialPersist s2` |
| f1c-t0043 | `# [4] PartialPersist s1` |
| f1c-t0046 | `# [5] PartialPersist s2` |
| f1c-t0057 | `# [4] PartialPersist s3` |
| f1c-t0061 | `# [3] PartialPersist s3` |
| f1c-t0062 | `# [3] PartialPersist s1` |
| f1c-t0069 | `# [6] PartialPersist s2` |
| f1c-t0070 | `# [4] PartialPersist s2` |
| f1c-t0071 | `# [3] PartialPersist s3` |
| f1c-t0072 | `# [3] PartialPersist s1` |
| f1c-t0075 | `# [3] PartialPersist s1` |
| f1c-t0079 | `# [7] PartialPersist s3` |
| f1c-t0085 | `# [4] PartialPersist s3` |
| f1c-t0087 | `# [5] PartialPersist s3` |
| f1c-t0090 | `# [2] PartialPersist s2` |
| f1c-t0092 | `# [3] PartialPersist s3` |
| f1c-t0094 | `# [3] PartialPersist s1` |
| f1c-t0095 | `# [4] PartialPersist s1` |
| f1c-t0096 | `# [4] PartialPersist s1` |
| f1c-t0098 | `# [3] PartialPersist s2` |
| standard-t0007 | `# [2] PartialPersist s1` |
| standard-t0024 | `# [2] PartialPersist s1` |
| standard-t0034 | `# [3] PartialPersist s2` |
| standard-t0050 | `# [2] PartialPersist s1` |
| standard-t0057 | `# [2] PartialPersist s1` |
| standard-t0065 | `# [2] PartialPersist s3` |
| standard-t0071 | `# [2] PartialPersist s3` |
| standard-t0073 | `# [2] PartialPersist s3` |
| standard-t0094 | `# [2] PartialPersist s2` |
| standard-t0098 | `# [2] PartialPersist s2` |

## 复现

节点数 3。先把该目录的 `MC.out` 拷到挂载盘。

### f1b-t0003

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0003/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [6] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0004

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0004/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0005

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0005/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [9] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0009

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0009/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [6] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0010

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0010/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [8] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0011

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0011/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [7] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0012

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0012/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0016

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0016/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [5] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0018

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0018/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [2] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0019

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0019/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [7] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0020

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0020/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [2] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0021

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0021/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0022

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0022/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [6] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0024

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0024/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [5] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0027

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0027/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0029

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0029/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [2] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0031

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0031/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0036

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0036/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [2] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0037

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0037/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [5] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0039

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0039/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [5] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0040

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0040/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0043

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0043/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0046

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0046/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [6] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0047

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0047/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0048

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0048/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [5] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0050

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0050/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [6] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0053

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0053/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [6] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0055

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0055/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [9] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0057

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0057/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0059

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0059/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0061

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0061/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0066

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0066/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [2] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0069

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0069/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0072

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0072/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0082

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0082/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [6] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0085

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0085/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0086

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0086/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [7] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0090

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0090/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [2] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0092

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0092/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0093

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0093/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [7] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0094

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0094/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [8] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0095

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0095/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0096

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0096/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1b-t0098

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1b-t0098/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0001

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0001/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0004

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0004/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0005

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0005/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [9] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0008

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0008/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0009

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0009/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [5] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0011

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0011/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0016

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0016/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [5] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0020

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0020/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [2] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0021

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0021/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0024

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0024/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [5] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0027

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0027/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0029

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0029/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [2] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0031

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0031/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0034

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0034/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0036

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0036/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [2] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0037

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0037/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0040

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0040/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0043

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0043/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0046

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0046/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [5] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0057

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0057/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0061

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0061/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0062

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0062/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0069

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0069/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [6] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0070

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0070/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0071

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0071/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0072

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0072/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0075

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0075/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0079

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0079/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [7] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0085

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0085/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0087

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0087/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [5] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0090

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0090/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [2] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0092

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0092/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0094

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0094/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0095

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0095/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0096

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0096/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [4] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### f1c-t0098

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/f1c-t0098/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### standard-t0007

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/standard-t0007/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [2] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### standard-t0024

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/standard-t0024/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [2] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### standard-t0034

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/standard-t0034/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [3] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### standard-t0050

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/standard-t0050/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [2] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### standard-t0057

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/standard-t0057/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [2] PartialPersist s1` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### standard-t0065

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/standard-t0065/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [2] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### standard-t0071

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/standard-t0071/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [2] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### standard-t0073

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/standard-t0073/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [2] PartialPersist s3` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### standard-t0094

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/standard-t0094/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [2] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

### standard-t0098

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/torn-storage/standard-t0098/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [2] PartialPersist s2` 的 `partial-persist` 上退出，节点日志含有 `votedFor not found in storage`。不要期望模型里的那个 Follower。

