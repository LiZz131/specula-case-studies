# HandleRequestVoteResponse 在非候选人上丢掉更高任期

归类：`spec`。收到的 RequestVote 响应任期高于本机时，库先改任期再返回。公式里「不是候选人就丢弃且任期不变」和「更高任期就改任期」同时为真，TLC 选了前者。

协议：RPC 响应里的任期大于 currentTerm 时，把 currentTerm 改成该任期并转为 Follower。`raft_recv_requestvote_response`（`system/src/raft_server.c` 1152–1159 行）先做这件事，然后 `return 0`。后面 1168–1172 行「不是候选人就返回」只在任期没有更高时才走到。

公式 `HandleRequestVoteResponse`（`spec/base.tla` 293–305 行）的第二条析取只有 `state[i] /= Candidate`，没有 `m.mterm <= currentTerm[i]`。接收者是 Follower 时两条都成立。模型值是被选中的那条「任期不变」，不是协议要求的结果，也不是库要改成的目标。

要改的公式：不是候选人就丢弃的那条加上 `m.mterm <= currentTerm[i]`。更高任期的那条保持优先，且不要和它重叠。

步前消息的 `mterm` 等于代码后来的 `currentTerm`，大于模型留下的任期。线上交付的就是这封响应。共 18 条：standard 4，crashrecovery 3，membership 3，snapshot 4，staleread 4。每条轨迹的种子、步号和两边的值在同目录的 `traces.tsv`。子目录名是 `<配置>-tNNNN`。复现：`run_one_testcase.sh <该 MC.out> 3`。失败步是 `HandleRequestVoteResponse`。期望：接收者的 currentTerm 变成消息里的 `mterm`，角色变为 Follower。
