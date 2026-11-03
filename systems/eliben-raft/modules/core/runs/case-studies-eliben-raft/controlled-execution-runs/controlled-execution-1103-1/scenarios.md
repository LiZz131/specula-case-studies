# 交回 Specula 的场景

没有 E。没有对不上现有动作的 A。

`controlled.go` 86–102 行按 `ConflictTerm` / `ConflictIndex` 改 `nextIndex`。`HandleAppendEntriesResponse` 的失败分支已经写成 `LeaderNextFromConflict`，守卫和写入的值都对得上。这一轮 500 条轨迹没有走出失败的 AppendEntries 应答，所以这 15 行仍未执行。下一步是加长 `DepthBound`，不在 `Sand*` 里再补一条协议。
