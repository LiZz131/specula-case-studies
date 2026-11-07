# 补丁

SandTable 基线是 `/users/bingzhuo/sandtable` 的 `af7d6f31d1192ed0b433072bacc9e86b3e0df72a`。被测源码基线是 `artifact/raft`。`<ce>/system` 和这棵基线逐文件相同，没有 `system.patch`。

`sandtable.patch` 里的路径：

- `scripts/common/start_docker_common.sh`
- `systems/WRaft-series/SpeculaWRaft/scripts/testcase_generator.py`
- `systems/WRaft-series/driver/CMakeLists.txt`
- `systems/WRaft-series/driver/deps/WRaft.cpp`

```text
patch -p1 -d <ce>/sandtable < <ce>/patches/sandtable.patch
```
