# 本轮补丁

SandTable 基线是拷进本轮时的提交 `af7d6f31d1192ed0b433072bacc9e86b3e0df72a`。

被测源码基线是 `<run>/artifact/raft/part3/raft`。协议谓词来自 eliben/raft `d85b35cef3da8bde6c863b9231559e61b1542805`。artifact 里已经把投票应答抽进函数，并在 `controlledReplay` 下关掉计时器。本轮补丁是相对 artifact 的差异，不是相对那个上游提交的差异。

```text
patch -p1 -d <ce>/sandtable < <ce>/patches/sandtable.patch
patch -p1 -d <ce>/system < <ce>/patches/system.patch
```

`<ce>` 是 `controlled-execution-runs/controlled-execution-1102-1`。两条都在临时目录里对基线打过，打完和本轮副本逐文件相同。

## sandtable.patch

| 路径 | 说明 |
|---|---|
| `scripts/run_round.py` | 采样、回放、语句覆盖 |
| `systems/ElibenRaft/testcase_generator.py` | 控制器命令 |
| `systems/ElibenRaft/driver/ElibenRaft.cpp` | 驱动 |
| `systems/ElibenRaft/driver/CMakeLists.txt` | 构建 |
| `systems/ElibenRaft/driver/libeliben.h` | c-shared 声明 |
| `systems/ElibenRaft/driver/bridge/main.go` | 导出给驱动的入口 |
| `systems/ElibenRaft/driver/bridge/go.mod` | 模块 |
| `systems/ElibenRaft/scripts/env.sh` | 控制器和拦截器路径 |
| `systems/ElibenRaft/scripts/system_config.sh` | 允许乱序、保留分区消息 |
| `systems/ElibenRaft/scripts/start_docker.sh` | 覆盖率目录 |
| `systems/ElibenRaft/scripts/run_one_testcase.sh` | 单条回放 |
| `systems/ElibenRaft/scripts/build_lib.sh` | 编 `libeliben.so` |

## system.patch

| 路径 | 说明 |
|---|---|
| `raft.go` | `persistToStorage` 的第一次 `Set` 抽成 `writeCurrentTerm`。`startElection` 把 peer 传给 `onVoteReply` |
| `controlled.go` | 受控入口、文件存储上的读回、投票集合 |
| `filestorage.go` | 新文件。崩溃之后从目录恢复，不沿用旧模块的内存 |
