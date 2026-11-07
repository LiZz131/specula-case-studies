# 规格对齐

## standard / t0001 / 种子 1 / 步 2

- 变量 `currentTerm`，节点 `n3`（模型 `s3`）
- 代码值 `1`，模型值 `0`
- `pc`：`HandleRequestVoteRequest s3 s1 2`

原公式把租约拒绝写成自由选择。`current_leader` 不在状态里，所以 TLC 可以在没有领导者时也走拒绝分支，任期保持 0。

`<ce>/system/src/raft_server.c` 的 `raft_recv_requestvote`：

- 587–591 行：只有 `current_leader` 指向其他节点，并且 `timeout_elapsed < election_timeout` 时，才不更新任期直接拒绝。
- 593–601 行：否则若请求任期更高，调用 `raft_set_current_term`，任期变成请求的任期。

这一步开始时 `current_leader` 是空的。库没有走 587 行，而是把任期设成 1。这和“看到更高任期就采用”一致。

改后的公式：

- 增加 `currentLeader`。`raft_new` 里它是 `Nil`。
- 租约拒绝仅当 `currentLeader[i] \notin {Nil, j}`。
- 其余路径按 593–617 行更新任期，并在提高任期或同意投票时把 `currentLeader` 清成 `Nil`。
- `raft_become_candidate`（192 行）清掉它。成为领导者时 `raft_set_state` 把它设成自己。
- `raft_recv_appendentries` 在没有因任期更低而拒绝时把它设成发送者（427 行）。更高任期的 AppendEntries 响应（302 行）和 `raft_begin_load_snapshot`（1386 行）把它清成 `Nil`。恢复后它是 `Nil`。
