# controlled-execution-1030-1-sanitizer

覆盖率轮次 `controlled-execution-1030-1` 的 `RedisRaftDriver` 没有链接 ASan/UBSan。这一轮复用它已经采好的 500 条 `MC.out`，没有重新采样。

- 二进制：`sandtable/driver/build-san/RedisRaftDriver`
- 编译：库和驱动 `-fsanitize=address,undefined -g -O1 -fno-omit-frame-pointer`，没有 `--coverage`
- 动态库：`libasan.so.6`、`libubsan.so.1`
- 节点环境：`ASAN_OPTIONS=detect_leaks=0:verify_asan_link_order=0`
- 启动：stock interceptor 的 `LD_PRELOAD`。不把 `libasan.so` 再放进 `LD_PRELOAD`，否则三个节点在构造函数里 `SEGV`，`pc` 为 0
- 不查泄漏
- 五个配置各 100 条，全部 `ok`，退出后日志里没有 AddressSanitizer / UBSan `runtime error`
- `failures.tsv` 没有行
- 覆盖率轮次的 `lcov.info` 时间戳停在该轮结束（2026-10-31T04:41:59Z），没有并入这一轮的计数
