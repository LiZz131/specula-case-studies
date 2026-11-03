# 交回 Specula 的场景

没有 E。下面这条 A 和现有动作对不上：变量已经在规格里，失败分支写的值不是源码写的值。

## 失败的 AppendEntries 用冲突下标回退

`controlled.go` 的 `onAEReply`，约 86–102 行。跟随者的成功位是 false 时，领导者按 `ConflictTerm` 在自己的日志里找最后一个同任期条目，把 `nextIndex` 设成它的下一个下标；没有这个任期就把 `nextIndex` 设成 `ConflictIndex`。跟随者在 `raft.go` 约 398–416 行填写这两个字段，那一段不改跟随者自己的日志，分类是 B。

现有 `HandleAppendEntriesResponse` 的失败分支把 `nextIndex` 减 1。注释写了源码用冲突优化，公式没有用。守卫对得上（应答失败、节点仍是领导者、`savedCurrentTerm` 等于应答任期），写入的值对不上。

这一轮 500 条轨迹里的 `HandleAppendEntriesResponse` 失败都没有走到这条赋值，应答全是成功。成功分支的偏差已经记在 `potential-bugs/nextindex-reply/`：规格用 `mmatchIndex + 1`，库用 `ni + len(entries)`。

不在 `Sand*` 里补。交给 `spec_generation` 时两处一起改：成功分支用这条 RPC 的 `ni + len(entries)`，失败分支用 `ConflictIndex` / `ConflictTerm`，不要改成把库的 `nextIndex` 写成模型值。
