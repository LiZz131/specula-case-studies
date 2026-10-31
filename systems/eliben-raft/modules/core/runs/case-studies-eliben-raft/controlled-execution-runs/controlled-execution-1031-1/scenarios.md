# 交回 Specula 的场景

这些是未覆盖分类里的 E。不在 `Sand*` 里补。A 里和现有动作对得上的行不在这里：冲突回退对得上 `SandHandleAppendEntriesResponse`，`diverge` 配置没有走到，记在 `行分类.tsv` 的下一步里。

## 应用到状态机

`commitChanSender`（`raft.go` 664–689）在 `commitIndex` 前进之后把条目送到 `commitChan`，并写下 `lastApplied`。`AppendEntries` 里往 `newCommitReadyChan` 发送（`raft.go` 389–390）是这条路径的通知。受控构造不启动 `commitChanSender`，受控的 `AppendEntries` 也不发这个通知。

规格有 `commitIndex`，没有 `lastApplied`，也没有应用通道。比较的是 `commitIdx`（代码的 `commitIndex + 1`），不是状态机看到的下标。现有动作把提交点算出来就停了，产生不了 `lastApplied`。

## 墙钟计时器

`electionTimeout`（`raft.go` 422–430）返回 150 到 300 毫秒的 `time.Duration`。`runElectionTimer`（439–456、475–476）每 10 毫秒看一次墙钟，到期才 `startElection`。`startLeader` 的心跳协程（557–558、560–588、592–593）用 `time.Timer` 和 `triggerAEChan`。`Submit` 在非受控模式往 `triggerAEChan` 发送（180–182）。

受控模式不跑这些循环。`Timeout` 是 `raft periodic 2000`，`AppendEntriesAll` 是 `raft periodic 200`，`Submit` 触发的那一轮已经折进 `SandClientRequest`。规格里没有墙钟，也没有这些通道。现有的 `Timeout` 和 `AppendEntriesAll` 产生不了 `time.Sleep` 或 ticker。不要把计时器写进规格。

## net/rpc 测试服务器

`server.go` 的 `Serve`、`Call`、`ConnectToPeer`、`DisconnectPeer`、`DisconnectAll`、`IsLeader`、`Server.Submit`，以及 `RPCProxy` 的转发、按环境变量 sleep 或丢弃（208–251）。驱动把 `server` 留空，字节走 SandTable 的 `TcpNetwork`。

规格里的消息是袋子，按 `seq` 投递或 `LoseMessage` 丢掉。没有监听套接字、rpc 客户端或 `RAFT_UNRELIABLE_RPC`。这些字段现有动作产生不了。不要把 `net/rpc` 写进规格。
