# controlled-execution-1102-1 的补丁

两份补丁都相对 `/mydata/bingzhuo/src/SandTable` 的 `main`（`af7d6f3`）。在本轮的 `<ce>/sandtable` 上用 `patch -p1` 打入。`CMakeLists.txt` 从旁边的 `<ce>/system` 编译库。

`<ce>/system` 和 `artifact/raft` 逐文件相同，库本身没有补丁。

| 文件 | 内容 |
|---|---|
| `sandtable.patch` | 新增 `scripts/collect_gcov.sh`、`scripts/run_round.py` |
| `wraft.patch` | `WRaft.cpp`、测试用例生成器、`CMakeLists.txt`、`env.sh`、`start_docker.sh` |

```text
patch -p1 -d <ce>/sandtable < <ce>/patches/sandtable.patch
patch -p1 -d <ce>/sandtable < <ce>/patches/wraft.patch
```
