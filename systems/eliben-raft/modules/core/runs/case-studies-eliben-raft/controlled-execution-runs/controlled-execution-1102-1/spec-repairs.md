# spec-repairs

协议公式改的是这一轮 `<ce>/spec/base.tla` 和 `<ce>/spec/MC.tla`。`<run>/spec/base.tla` 没有改。下面两条公式覆盖 `failures.tsv` 里全部 121 条 `spec`。

## nextIdx

| | |
|---|---|
| 配置 | standard |
| 轨迹 | t0001 |
| 种子 | 1 |
| 步 | # [29] HandleAppendEntriesResponse s3 s2 18 |
| 变量 | nextIdx |
| 代码值 | Code (n3): {'n1': 3, 'n2': 1} |
| 模型值 | Model(n3): {'n1': 3, 'n2': 3} |
| 源码 | `<ce>/system/controlled.go` 的 `onAEReply`，成功分支是 `nextIndex[peer] = ni + len(entries)`，`matchIndex` 是它减 1。`ni` 是这条 RPC 发出时的下标。应答字段来自 `encodeAER`。失败分支是同函数里的 `ConflictTerm` / `ConflictIndex`，跟随者在 `raft.go` 的 `AppendEntries` 里填写。 |

旧公式（成功）：`nextIndex' = m.mmatchIndex + 1`，`mmatchIndex` 取跟随者 `Len(newLog)`。

旧公式（失败）：`nextIndex' = Max(1, nextIndex - 1)`。

新公式（成功）：`nextIndex' = m.mprevLogIndex + m.mentryLen + 1`，`matchIndex' = m.mprevLogIndex + m.mentryLen`。这两个字段从这条 RPC 复制到应答上。

新公式（失败）：`nextIndex' = LeaderNextFromConflict(i, m.mnextHint, m.mconflictTerm)`。`mnextHint` 是跟随者按 `ConflictIndex` 换算后的 1-based 下标：日志不够长时为 `LastLogIndex + 1`，否则是冲突任期在该前缀里的最小下标。领导者若自己的日志含有该任期，则取该任期最大下标加 1，否则用这个提示。

同一公式还覆盖其余 30 条 `nextIdx`（standard、f1c）。这 31 条的 `msuccess` 都是 TRUE，失败分支是按同一段源码对齐的，这一轮没有走到。

## restore

| | |
|---|---|
| 配置 | standard |
| 轨迹 | t0007 |
| 种子 | 7 |
| 步 | # [2] PartialPersist s1 |
| 变量 | restore |
| 代码值 | 2026/11/03 04:39:42 votedFor not found in storage |
| 模型值 | MCPartialPersist recovers a live follower |
| 源码 | `<ce>/system/raft.go` 的 `restoreFromStorage`。`HasData` 为真但 `votedFor` 或 `log` 还没写过时 `log.Fatal`。`ControlledPersistTermOnly` 只写 `currentTerm`。三个键都写过之后，`Crash` 的恢复不变。 |

旧公式：`currentTerm /= persistedTerm` 时写下 `persistedTerm`，再把节点恢复成 Follower，`votedFor` 取旧的 `persistedVotedFor`。

新公式：增加 `storageReady`。`Init` 为 FALSE。每次 `persistToStorage`（任期、`votedFor`、日志三个键都写）把它设为 TRUE。`PartialPersist` 增加 `storageReady[i]`。键不存在时这个动作不启用，不恢复出一个活着的 Follower。键已经存在时，恢复赋值和原来一样。

同一公式还覆盖其余 89 条 `restore`（standard、f1b、f1c）。
