# 补丁

SandTable 基线是 `/users/bingzhuo/sandtable` 的 `af7d6f3`。被测源码基线是 `artifact/redisraft`。

```text
patch -p1 -d <ce>/sandtable < <ce>/patches/sandtable.patch
patch -p1 -d <ce>/system < <ce>/patches/system.patch
```

`system.patch`：`include/raft.h` 声明 `raft_specula_advance_commit`；`src/raft_server.c` 在 `specula_step` 下把提交推进从 `raft_flush` 拆出。

`sandtable.patch`：RedisRaft 驱动、`CMakeLists.txt`、`RedisRaft/scripts/`、`scripts/collect_gcov.sh`、`scripts/run_round.py`。
