# BecomeLeader 把自己的 nextIndex 写成 last+1

归类：`spec`。库在 `raft_become_leader` 里跳过自己，不写 `next_idx`。自己的值停在初始的 1。跟随者的 `next_idx` 写成当前最后下标，和公式的 `ELSE newLastIdx` 一致。领导者不给自己发 AppendEntries，这个字段不参与复制。协议不要求领导者维护一条指向自己的 nextIndex。

公式 `BecomeLeader`（`spec/base.tla` 339–340 行）写的是 `j = i` 时 `newLastIdx + 1`。注释指 `raft_server.c` 476–487 行，那些行没有这条赋值。真正设置跟随者 nextIndex 的是 `raft_become_leader` 497–506 行，`me->node == node` 时 `continue`。

模型值不是修补目标。不要在驱动里把 `next_idx[self]` 改成 `last+1`。要改的是公式：`BecomeLeader` 不要给 `nextIndex[i][i]` 赋 `newLastIdx + 1`，自己的项保持不变。

共 482 条：standard 96，crashrecovery 97，membership 97，snapshot 96，staleread 96。每条轨迹的种子、步号和两边的值在同目录的 `traces.tsv`。子目录名是 `<配置>-tNNNN`。复现：把该轨迹的 `MC.out` 放到控制器能读的路径，然后

`run_one_testcase.sh <该 MC.out> 3`

失败步是 `BecomeLeader`。比较停在行动者自己的 `nextIndex`。期望：跟随者 nextIndex 等于新日志最后下标，自己的 nextIndex 仍是步前的值（这些轨迹里是 1）。日志里的 no-op、角色 Leader、自己的 matchIndex 等于最后下标，这些和库一致。
