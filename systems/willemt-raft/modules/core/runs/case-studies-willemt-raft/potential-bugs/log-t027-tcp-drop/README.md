# log/t027：投递中途 TCP 断开

这不是模型公式和库赋值对不上。回放执行到向 n2 投递 n1 的 AppendEntries 时，`check_has_recv_queue` 连续失败，随后 n2 与 n1 的连接被关闭。这一步没有在 n2 上执行，所以 n2 的 `commitIdx` 停在 1，模型是 3。前面几次 `net-len` 警告是连接已经开始丢队列。

位置：`log.host` 约 1705–1783 行。控制器在 `Command.cpp:288` 对 `commitIdx` assert。轨迹以 `logout` 结束，但是断言已经失败。

同目录保留重跑前的 `MC.out`、`traces.txt`、`log.host`。配置是 `MC_for_sandtable_log.cfg`，种子对应第一轮 t027。
