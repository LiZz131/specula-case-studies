# 成功的 AppendEntries 应答把 nextIndex 按这条 RPC 回退

公式修改记在 `controlled-execution-runs/controlled-execution-1102-1/spec-repairs.md`。这一轮不作为交付。

31 条，都在 `HandleAppendEntriesResponse`，应答的 `msuccess` 是 TRUE。比较失败的变量只有 `nextIdx`。归类：`spec`。

适配层没有改这个下标。应答先按序号投递，`nextIdx` 读的是库里的 `nextIndex` 加 1。同一步的日志和任期在前一条比较里是对齐的，失败发生在这一步写下的新 `nextIndex`。

库在 `controlled.go` 的 `onAEReply`：成功时 `nextIndex[peer] = ni + len(entries)`，`matchIndex` 是它减 1。`ni` 是这条 RPC 发出时的 `nextIndex`，不是跟随者当前日志的长度。一条偏旧的空心跳（`prev` 为 -1、条目数为 0）会把 `nextIndex` 写回 0，显示成 1。

Raft 里 `nextIndex` 是领导者重试用的提示。这一步没有改已提交的前缀，也没有让两条日志在同一下标上任期不同。协议不要求它等于跟随者此刻的日志长度。把库改成模型里的 `mmatchIndex + 1` 会丢掉这条 RPC 自己的下标。

要改的是 `base.tla` 里 `HandleAppendEntriesResponse` 成功分支。现在写成 `nextIndex' = m.mmatchIndex + 1`，而 `mmatchIndex` 取的是跟随者 `Len(newLog)`。注释自己写的是 `raft.go:647` 的 `ni + len(entries)`。成功分支应使用这条 RPC 的 `ni + len(entries)`。失败分支现在是减 1，源码用的是 `ConflictIndex`，这 31 条没有走到失败分支。

模型值不是修补目标。

| 轨迹 | 失败步 | 代码 | 模型 |
|---|---|---|---|
| f1c-t0045 | `# [27] HandleAppendEntriesResponse s1 s2 20` | Code (n1): {'n2': 1, 'n3': 1} | Model(n1): {'n2': 2, 'n3': 1} |
| f1c-t0048 | `# [30] HandleAppendEntriesResponse s1 s2 19` | Code (n1): {'n2': 1, 'n3': 2} | Model(n1): {'n2': 2, 'n3': 2} |
| f1c-t0055 | `# [30] HandleAppendEntriesResponse s3 s2 21` | Code (n3): {'n1': 1, 'n2': 1} | Model(n3): {'n1': 1, 'n2': 2} |
| f1c-t0081 | `# [30] HandleAppendEntriesResponse s2 s1 21` | Code (n2): {'n1': 1, 'n3': 1} | Model(n2): {'n1': 2, 'n3': 1} |
| f1c-t0083 | `# [27] HandleAppendEntriesResponse s2 s1 19` | Code (n2): {'n1': 1, 'n3': 1} | Model(n2): {'n1': 2, 'n3': 1} |
| f1c-t0088 | `# [27] HandleAppendEntriesResponse s1 s2 18` | Code (n1): {'n2': 1, 'n3': 1} | Model(n1): {'n2': 2, 'n3': 1} |
| standard-t0001 | `# [29] HandleAppendEntriesResponse s3 s2 18` | Code (n3): {'n1': 3, 'n2': 1} | Model(n3): {'n1': 3, 'n2': 3} |
| standard-t0004 | `# [30] HandleAppendEntriesResponse s3 s2 18` | Code (n3): {'n1': 3, 'n2': 1} | Model(n3): {'n1': 3, 'n2': 2} |
| standard-t0005 | `# [28] HandleAppendEntriesResponse s1 s3 17` | Code (n1): {'n2': 1, 'n3': 1} | Model(n1): {'n2': 1, 'n3': 2} |
| standard-t0012 | `# [25] HandleAppendEntriesResponse s1 s3 15` | Code (n1): {'n2': 1, 'n3': 1} | Model(n1): {'n2': 1, 'n3': 2} |
| standard-t0014 | `# [26] HandleAppendEntriesResponse s3 s2 17` | Code (n3): {'n1': 2, 'n2': 2} | Model(n3): {'n1': 2, 'n2': 3} |
| standard-t0018 | `# [25] HandleAppendEntriesResponse s3 s2 18` | Code (n3): {'n1': 1, 'n2': 1} | Model(n3): {'n1': 1, 'n2': 2} |
| standard-t0020 | `# [29] HandleAppendEntriesResponse s2 s1 18` | Code (n2): {'n1': 1, 'n3': 1} | Model(n2): {'n1': 2, 'n3': 1} |
| standard-t0021 | `# [30] HandleAppendEntriesResponse s1 s2 17` | Code (n1): {'n2': 2, 'n3': 3} | Model(n1): {'n2': 3, 'n3': 3} |
| standard-t0030 | `# [27] HandleAppendEntriesResponse s2 s1 17` | Code (n2): {'n1': 1, 'n3': 1} | Model(n2): {'n1': 3, 'n3': 1} |
| standard-t0033 | `# [30] HandleAppendEntriesResponse s2 s3 18` | Code (n2): {'n1': 1, 'n3': 1} | Model(n2): {'n1': 1, 'n3': 3} |
| standard-t0035 | `# [29] HandleAppendEntriesResponse s1 s3 16` | Code (n1): {'n2': 1, 'n3': 1} | Model(n1): {'n2': 1, 'n3': 2} |
| standard-t0038 | `# [29] HandleAppendEntriesResponse s1 s2 18` | Code (n1): {'n2': 2, 'n3': 3} | Model(n1): {'n2': 3, 'n3': 3} |
| standard-t0042 | `# [29] HandleAppendEntriesResponse s3 s2 17` | Code (n3): {'n1': 1, 'n2': 1} | Model(n3): {'n1': 1, 'n2': 3} |
| standard-t0051 | `# [29] HandleAppendEntriesResponse s3 s1 17` | Code (n3): {'n1': 2, 'n2': 2} | Model(n3): {'n1': 3, 'n2': 2} |
| standard-t0058 | `# [27] HandleAppendEntriesResponse s3 s2 19` | Code (n3): {'n1': 1, 'n2': 1} | Model(n3): {'n1': 1, 'n2': 3} |
| standard-t0059 | `# [29] HandleAppendEntriesResponse s2 s3 18` | Code (n2): {'n1': 1, 'n3': 1} | Model(n2): {'n1': 1, 'n3': 2} |
| standard-t0060 | `# [29] HandleAppendEntriesResponse s2 s1 19` | Code (n2): {'n1': 1, 'n3': 1} | Model(n2): {'n1': 2, 'n3': 1} |
| standard-t0061 | `# [26] HandleAppendEntriesResponse s1 s3 18` | Code (n1): {'n2': 1, 'n3': 1} | Model(n1): {'n2': 1, 'n3': 3} |
| standard-t0063 | `# [28] HandleAppendEntriesResponse s1 s2 18` | Code (n1): {'n2': 2, 'n3': 1} | Model(n1): {'n2': 3, 'n3': 1} |
| standard-t0067 | `# [26] HandleAppendEntriesResponse s1 s3 18` | Code (n1): {'n2': 2, 'n3': 2} | Model(n1): {'n2': 2, 'n3': 3} |
| standard-t0068 | `# [25] HandleAppendEntriesResponse s1 s2 15` | Code (n1): {'n2': 1, 'n3': 1} | Model(n1): {'n2': 2, 'n3': 1} |
| standard-t0078 | `# [28] HandleAppendEntriesResponse s1 s3 19` | Code (n1): {'n2': 3, 'n3': 1} | Model(n1): {'n2': 3, 'n3': 3} |
| standard-t0084 | `# [29] HandleAppendEntriesResponse s2 s3 18` | Code (n2): {'n1': 2, 'n3': 1} | Model(n2): {'n1': 2, 'n3': 2} |
| standard-t0090 | `# [30] HandleAppendEntriesResponse s1 s2 17` | Code (n1): {'n2': 1, 'n3': 1} | Model(n1): {'n2': 3, 'n3': 1} |
| standard-t0095 | `# [30] HandleAppendEntriesResponse s2 s1 18` | Code (n2): {'n1': 1, 'n3': 1} | Model(n2): {'n1': 2, 'n3': 1} |

## 复现

节点数 3。先把该目录的 `MC.out` 拷到挂载盘。容器里看不到 `potential-bugs/`。

### f1c-t0045

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/f1c-t0045/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [27] HandleAppendEntriesResponse s1 s2 20` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### f1c-t0048

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/f1c-t0048/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [30] HandleAppendEntriesResponse s1 s2 19` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### f1c-t0055

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/f1c-t0055/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [30] HandleAppendEntriesResponse s3 s2 21` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### f1c-t0081

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/f1c-t0081/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [30] HandleAppendEntriesResponse s2 s1 21` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### f1c-t0083

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/f1c-t0083/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [27] HandleAppendEntriesResponse s2 s1 19` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### f1c-t0088

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/f1c-t0088/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [27] HandleAppendEntriesResponse s1 s2 18` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0001

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0001/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [29] HandleAppendEntriesResponse s3 s2 18` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0004

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0004/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [30] HandleAppendEntriesResponse s3 s2 18` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0005

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0005/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [28] HandleAppendEntriesResponse s1 s3 17` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0012

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0012/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [25] HandleAppendEntriesResponse s1 s3 15` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0014

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0014/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [26] HandleAppendEntriesResponse s3 s2 17` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0018

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0018/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [25] HandleAppendEntriesResponse s3 s2 18` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0020

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0020/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [29] HandleAppendEntriesResponse s2 s1 18` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0021

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0021/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [30] HandleAppendEntriesResponse s1 s2 17` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0030

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0030/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [27] HandleAppendEntriesResponse s2 s1 17` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0033

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0033/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [30] HandleAppendEntriesResponse s2 s3 18` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0035

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0035/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [29] HandleAppendEntriesResponse s1 s3 16` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0038

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0038/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [29] HandleAppendEntriesResponse s1 s2 18` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0042

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0042/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [29] HandleAppendEntriesResponse s3 s2 17` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0051

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0051/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [29] HandleAppendEntriesResponse s3 s1 17` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0058

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0058/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [27] HandleAppendEntriesResponse s3 s2 19` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0059

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0059/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [29] HandleAppendEntriesResponse s2 s3 18` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0060

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0060/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [29] HandleAppendEntriesResponse s2 s1 19` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0061

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0061/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [26] HandleAppendEntriesResponse s1 s3 18` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0063

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0063/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [28] HandleAppendEntriesResponse s1 s2 18` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0067

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0067/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [26] HandleAppendEntriesResponse s1 s3 18` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0068

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0068/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [25] HandleAppendEntriesResponse s1 s2 15` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0078

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0078/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [28] HandleAppendEntriesResponse s1 s3 19` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0084

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0084/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [29] HandleAppendEntriesResponse s2 s3 18` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0090

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0090/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [30] HandleAppendEntriesResponse s1 s2 17` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

### standard-t0095

```text
sudo cp /users/bingzhuo/Specula/case-studies/systems/eliben-raft/modules/core/runs/case-studies-eliben-raft/potential-bugs/nextindex-reply/standard-t0095/MC.out /users/bingzhuo/sandtable/build/mount/specula-eliben/work/repro/MC.out
sudo docker exec controller bash /root/sandtable/specula-eliben/sandtable/systems/ElibenRaft/scripts/run_one_testcase.sh /root/sandtable/specula-eliben/work/repro/MC.out 3
```
期望在 `# [30] HandleAppendEntriesResponse s2 s1 18` 看到 `nextIdx` 不一致。协议要求的是库按这条 RPC 的 `ni + len(entries)` 写下的那个下标，不是模型值。

