# 补丁

SandTable 基线是提交 `af7d6f31d1192ed0b433072bacc9e86b3e0df72a`。被测源码基线是 `<run>/artifact/raft`。`<ce>/system` 与这棵树逐文件相同，没有 `system.patch`。

`sandtable.patch` 含这些路径：

- `scripts/common/start_docker_common.sh`
- `systems/WRaft-series/SpeculaWRaft/scripts/testcase_generator.py`
- `systems/WRaft-series/driver/CMakeLists.txt`
- `systems/WRaft-series/driver/deps/WRaft.cpp`

打回本轮副本：

```text
patch -p1 -d <ce>/sandtable < <ce>/patches/sandtable.patch
```
