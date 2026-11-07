# 1103 

任务1: 在理想情况下, controlled execution的效果最好能做到, specula建模的spec里面，每个 action 与 CE 过程一一对应。当前并不能做到, (你是怎么处理这些不理想的状态的?)
1. 有些在 code 中，几个 action 是同一个 function，理论上应该连续执行，这种情况下 CE 无法精确控制
2. Specula 建模出来的 model，有些在action表现出随机性，但是code层面并无随机性：
    1. 有一个具体的例子，`HandleRequestVoteRequest`，过程中
    2. 目前来看，这种随机性的来源可能是 model 忽略了一些变量导致的，也有可能是忽略了一些 timeout 这种时间相关内容导致的
3. 另外，send 的动作可能不需要极其严格的对比, recv 才需要严格的对比

任务2: 重要: 你需要总结, 所有轮次修复的所有 spec 错误包括哪些? 你具体如何修复的? 给出 patch, 让我明确看到首尾的 base.tla 变化情况!

任务3: 总结你认为 skill 中模糊, 有改进空间的所有地方, 给出详细的修改建议:

任务4: skill 哪些地方表示你需要将 ce 做如此多轮次? 从1-10? 每次重跑就开启一次新的对吗?

任务5: 完全理解 sandtable 里对于消息的处理, 然后我们再考虑是不是针对性修改;
1. 整理出当前 sandtable 对于消息处理的全部可用API, 以及拦截器可以做的所有事情.
2. 按照我的理解, 当前 sandtable 对于每个消息的唯一标识符是 seq, 但是实际上如果发送不符合我们的预期, 那么 seq 是不是就会完全变成无意义的内容? 另外, 我现在还不理解, 每条消息除了 seq 之外, sandtable 是否可以感知到发送方,接收方,消息类型,消息内容? sandtable 能否感知到, 是 A节点 发送给 B节点 这条信息呢(对于A B节点有无感知?)?
3. 未来, 可能结合针对特定 message 的解读和理解, 然后再针对性比较, 而且现在这样似乎也不准确...
4. 举例子: `Specula/case-studies/systems/willemt-raft/modules/core/runs/case-studies-willemt-raft/spec/base.tla`, 这里的 BroadcastAppendEntries 行为是随机发给子集, 那么这个行为在 sandtable 受控执行的时候应该会有很大的难度? 有没有优雅的方案做到呢...

是不是可以正常处理的 trace:
1. n1 作为 leader, 发起 BroadcastAppendEntries, 子集选择为 {n2, n3}
2. n1 作为 leader, 发起 BroadcastAppendEntries, 子集选择为 {n2}
3. n1 作为 leader, 发起 BroadcastAppendEntries, 子集选择为 {n3}

任务5.2:
需要判定, 这种随机性来自于code吗? 来自于时间吗? 来自于network吗? 来自于出于简化的目的吗? (sandtable 是怎么解决这些问题的?)
BroadcastAppendEntries 的行为是发给随机子集, 为什么要这样建模??? (另外这里也出现了随机性..), 这种随机性来自于? 出于什么样的考虑所以这样建模呢?
Specula建模的spec中, 如果存在随机性, 那么我们可以考虑以下来源(目前想到的就是这些):
- 如果是网络带来的随机性, 可以使用 network 对应的 drop / duplicate / recv时机的随机性 来做..
- 如果是超时带来的随机性, 可以用事件触发来做;
- 如果是出于spec建模简化的目的, 引入的随机性(相当于给spec更大的trace空间, 生成可能对code来说不合法的trace), 解决方案暂时未定?
- 如果是code本身的随机性, 可能需要手动 hack 代码

所以, **这里本质上, 是对提前返回这个bug的模拟**, 但是model没有忠实的反映code, 或者说是某种妥协, 因为集合无序, 没有模拟顺序迭代的情况..

另外, 提前返回, 这个违反了哪个 invariant 呢?

sandtable 本身对于 wraft 也有类似的建模, 我认为上述的 `broadcastAE` 相当于 `AppendEntriesAll`, 在sandtable的建模中, 这里就完全没有出现随机性(所以 sandtable 的建模本身就考虑到不应该添加随机性? 你可以反驳我的观点). 我认为, 也因此, sandtable 建模的模型本身, 可以使用 seq 作为唯一主键, 因为他的 spec 足够好的规避了随机性.


li bingzhuo, 公文??? 


任务6: 
1. 探讨, spec action 发生在同一个 function 的必要性... 这个是必要的吗? 从某种程度上, 这表明 spec 的状态空间更大, code 不一定每个都能走到? 比如说, 对于 A server 的一个 action1 和 send1 一定是同一个函数里面的, 那么加入model采样出来某种behavior, 结果是 action1 -> ...(一直没有出现send1) -> action1 -> send1, 这种情况似乎永远不能受控执行? 只有 action1 之后 crash 了 或者 action1 之后serverA一直没有别的动作直到再次出现 send1; 这些情况下好像才是有意义的?
2. 所以说, 我这里疑惑的是, action 合并是否有必要呢? 或者说我们发现, 分开确实可以探索更大的空间, 但是似乎也会引入一些非法状况.

## 任务 5 的回答

受控执行里，一条“消息”其实是三层不同的东西叠在一起。分清这三层，后面几个问题都有答案。

1. 进程发出的字节。节点上的拦截器挡住 `send` / `sendto` / `write`，在载荷前加 8 字节：`validation = 0xdeadbeef`，加上长度（`mysendto.h` 的 `hacked_sendto_header`）。节点进程自己看不到这个头，也看不到 `seq`。
2. 控制器按 TCP 连接收下来的一帧。连接的两端是套接字地址。配置文件把地址映到节点名，所以控制器知道这是「配置里的 A 发往配置里的 B」。载荷是去掉那 8 字节之后的原始字节。控制器不做协议解码：不知道这是投票还是日志，除非另外写一个该系统的解码器。`Msg::to_string` 只能把载荷打成十六进制。
3. 模型里的一条记录。`mtype`、`msource`、`mdest` 和条目都在 TLA 的记录里。生成器在 Python 里用这些字段决定投给谁，不是从字节里读出来的。

`seq` 只存在于第 2 层和第 3 层的一个平行计数器里。TCP 路径上，控制器把每一帧追加进 `messages_array`，`seq` 就是当时的长度（`TcpNetwork::enqueue_messages_array`）。它不是载荷里的字段，也不是「这条 A→B 连接上的第几条」。UDP 路径才在 `UdpMsg` 里同时保存序号、载荷、源地址和目的地址；这次 wraft 走的是 TCP。

因此：发送和模型不一致时，`seq` 作为「模型第 n 条 = 捕获第 n 条」这个等式失效，但作为「控制器看见的第 n 帧」仍然有效。失效的是两边的对齐，不是这个编号本身。多出来的一帧会把后面所有编号错一位。下一步 `deliver-unordered n1 n2 26` 写到 n2 套接字上的，是捕获数组的第 26 帧，不一定是模型里 `seq = 26` 的那条。

控制器命令里的名字和字节也是分开的，但分开的方式比「把任意一帧写到任意连接」更窄。`deliver-unordered A B seq` 用 A、B 只做一件事：在那条通道的队列里丢掉一帧，用来维持队列长度。真正写回网络的字节，以及写到哪一个套接字，都来自捕获那一帧时记在 `Msg` 里的 `fd`（`deliver_msg` 里是 `write(*msg.fd, msg.body(), ...)`）。这个 `fd` 在 `do_receive` 时就定了，是当时那条连接的对端。所以一帧一旦捕获，目的节点就冻住了，命令行上的 `B` 改不了它。节点进程对 `seq` 没有感知。

`drop-unordered` 更松。它按 A、B 找到通道，从队列头取出一帧丢掉，然后把这个 `seq` 记入 `dropped_seqs`。取出的那一帧不一定是 `messages_array[seq-1]`。源码注释写了：无序投递时，为了维持队列长度而丢掉的帧，可以和真正写出去的帧不是同一条。`duplicate-unordered` 复制的是 `messages_array[seq-1]` 的字节，在该通道上再入队，并追加一个新的捕获序号。

### 现在能用的控制器命令

TCP（这次用的）和 UDP 是两套。

| 命令 | 作用 |
|---|---|
| `deliver A B` | 该通道队列的队头，不看 `seq` |
| `deliver-unordered A B seq` | 把捕获的第 `seq` 帧写进 A→B |
| `drop-unordered A B seq` | 丢掉该通道队头的一帧，并禁止以后再投这个 `seq` |
| `duplicate-unordered A B seq` | 把第 `seq` 帧的字节再入队，新捕获号 |
| `clear A B` | 清空这条通道上还没投递的帧 |
| `deliver-all n` | 各通道一直投，直到至少 n 条 |
| `partition X` / `recover X` / `recover-reopen X` / `wait-recover` | 断开或恢复节点 X 的连接 |
| `compare net-len` | 只比捕获条数和模型给出的数 |
| `compare variable` | 比节点上读回的字符串和模型值 |
| `status` | 打印各通道积压 |

UDP 另有 `deliver seq`、`drop seq`、`duplicate seq`、`send A B data`、`block` / `unblock`。`send` 可以塞进控制器自己构造的字节。TCP 路径没有对等的「按内容构造一帧」的命令。

### 拦截器在节点上能做的事

控制器用 `intercept <节点> ...` 发给该节点上的 `libinterceptor`。它注册的命令是：`inc_time_ns`、`inc_time_us`、`inc_time_ms`、`check_has_recv_queue <对端>`、`state_collect`、`state_get`、`print`。也就是拨钟、看接收缓冲区里有没有字节、让驱动把变量收上来。它不解析协议，不改写载荷，不给消息分配 `seq`。

`execute <节点> <驱动命令>` 才进入被测进程的事件循环，例如 `raft recvfrom n1`、`raft periodic 2000`。一次 `execute` 返回，就是一次受控步。

生成器自己还有一套账：按模型记录 `(src, dst, mtype, accounted)`，投递前要求这条通道上恰好有一条未投递、类型匹配、且被模型记过账的消息。对不上就拒绝生成。这套账在 Python 里，不在控制器里。

### 以后按消息内容比较，该补哪一层

通用层只应保证三件事：帧的边界、端点（哪条连接）、原始字节。协议字段是可替换的解码器：给定一帧字节，得出类型、发送方、接收方、以及这次要比较的字段。Raft 的发送方在载荷里；别的系统可能只靠连接方向，载荷里没有身份。解码器按系统写，不要写进 SandTable 核心。

比较的主键不该是全局捕获序号。稳的主键是「端点对 + 在这条连接上的序号」，再加载荷摘要。模型每写一条消息，就得到同一个主键。代码多写一条时，多出来的主键对不上模型，接收方不会拿到错位的字节。现在的全局 `seq` 做不到这一点。

`drop-unordered` 按队列头丢帧，和「丢掉主键为 seq 的那一帧」不是一回事。要按消息丢，就得按主键找到那一帧，而不是 `try_dequeue` 队头。

### `BroadcastAppendEntries` 的随机子集

起点 `base.tla` 里这个动作是：领导者任选 `Server \ {i}` 的一个非空子集，子集里的节点都不需要快照，然后给它们发 AppendEntries。源码 `raft_send_appendentries_all` 不是这样。它按节点加入顺序走，某次 `raft_send_appendentries` 返回非 0 就停下。需要快照时，先把快照发出去，再返回 `RAFT_ERR_NEEDS_SNAPSHOT`。给定 `nextIndex` 和快照下标，前缀是唯一的。

这不是投递层能优雅解决的。控制器无法把「代码发出的那一个确定前缀」变成「模型抽中的另一个子集」。两条轨迹的网络袋不一样，就不是同一次执行。

两种合法的做法，对应两种不同的规格：

- 规格要描述这个二进制。子集改成源码的那个前缀。投递层不用改。第 5 轮就是这么做的。
- 规格要描述「领导者可以任选子集」的协议，而实现做不到。这是实现比协议窄，不是 SandTable 的缺陷。受控执行只能跑实现做得到的那些迹。模型抽到别的子集，就记成实现没有覆盖的行为，不要在控制器里伪造那些报文。

若实现本身也随机（例如真正的异步发送、调度不确定），优雅的做法是捕获之后按主键匹配，而不是按全局序号对齐。匹配成功才投递。匹配失败就是这次采样不在实现能到达的集合里。

### 按一次发送把源码走完

下面用三个节点。n1 是领导者，给 n2 发一条空的 AppendEntries。应用看到的载荷是 56 字节。SandTable 在这 56 字节外面还有一个 8 字节的帧头，节点进程看不见这个帧头。

**1. 节点进程调用 `send`。** `raft_send_appendentries` 写到它连向 n2 的那个套接字。拦截器在 `mysendto.c` 里先看这个 fd 是不是配置里关心的地址。是的话，`hack()` 先发 8 字节：

```c
struct hacked_sendto_header buf = {
    .validation = htonl(0xdeadbeef),
    .size = htonl(len),   /* len 是 56，不是 56+8 */
};
```

然后才把应用原来的 56 字节发出去。帧头里没有发送方、没有接收方、没有 `seq`、没有消息类型。拦截器自己知道这个 fd 的对端地址（`check_fd_is_concerned_with_addr`），但它不把地址写进帧头。

**2. 控制器按「哪条 TCP 连接」认出发送方和接收方。** 连接建立时 `add_fd_to_channel` 把两端地址记进 `channel_t`。配置文件的 `addr_to_node` 把地址映成 `n1`、`n2`。`do_receive` 用 `MSG_PEEK` 看前 8 字节，`validation` 对得上才把 `8 + size` 读成一条 `Msg`。`Msg` 的 `fd` 记的是这条连接的出站套接字，也就是写回 n2 的那个 fd。载荷本身仍是那 56 字节，`Msg::to_string` 只把它打成十六进制。

打开无序模式时，`enqueue_msg` 先调用 `enqueue_messages_array`：

```text
messages_array.push_back(msg);
Capture seq <messages_array.size()> bytes <msg.size>
```

第一条就是 `Capture seq 1 bytes 56`。这个 `1` 是全局数组长度，不是「n1→n2 上的第 1 条」，也不是模型里的 `seq`。同一时刻 n1 再给 n3 发一条，控制器打 `Capture seq 2 bytes 56`，即使两条在不同连接上。

**3. 生成器用模型的字段决定命令，不读这 56 字节。** `testcase_generator.py` 的 `capture(src, dst, mtype, accounted)` 自己加一，得到另一个 `seq`。它保存的是模型记录里的 `msource`、`mdest`、`mtype`。随后 `deliver()` 在该通道上找恰好一条未投递、`accounted`、类型相同的记录，发出：

```text
deliver-unordered n1 n2 1
loop intercept n2 check_has_recv_queue n1
execute n2 raft recvfrom n1
```

这里的 `1` 是生成器自己的计数。它和控制器的 `messages_array` 下标一致，当且仅当每一次真实的 `send` 都按同样的顺序调用过一次 `capture()`。

**4. 投递写回的是原始 56 字节，写到捕获时记下的那个 fd。** `deliver_unordered` 先查 `dropped_seqs`。然后 `deliver()` 用名字 `n1`、`n2` 找到通道，取出 `messages_array[0]`。`deliver_msg` 在无序模式下从这条通道的队列里 `try_dequeue` 一帧丢掉。源码注释写明，丢掉的可以不是即将写出去的那一帧，只是为了让队列长度减一。接着：

```cpp
write(*msg.fd, msg.body(), msg.size);
```

`msg.body()` 跳过 8 字节帧头。`msg.fd` 是捕获时记下的出站 fd。所以 n2 上的 `recv` 看到的就是当初 `send` 的那 56 字节。n2 的 Raft 代码可以自己解出 term、条目；SandTable 没有解。`check_has_recv_queue` 只是对 n2 上连向 n1 的 fd 做 `ioctl(FIONREAD)`，等缓冲区里有字节再让驱动调用 `raft_recv_appendentries`。

把命令写成 `deliver-unordered n1 n3 1` 也不会把这 56 字节改道到 n3。`n1 n3` 只决定从哪条队列里扔掉一帧；`write` 仍走 `messages_array[0]` 自己的 fd，也就是 n2。队列若是空的，`try_dequeue` 失败，函数直接返回，字节也不会写出去。TCP 没有一条命令能凭空造出一帧 Raft 消息。UDP 的 `send A B data` 可以，这次走的是 TCP。

### 例 1：发送和模型一致，`seq` 有意义

n1 一次 `raft periodic 200`，按节点名顺序先 n2 再 n3，各发一条空 AE。模型和生成器都预料到这两次发送。

| 顺序 | 控制器看到的 | 生成器账本 | 以后的投递命令 |
|---|---|---|---|
| 1 | `Capture seq 1 bytes 56`，fd 通向 n2 | `(n1, n2, AppendEntries, seq=1)` | `deliver-unordered n1 n2 1` 写出第 1 帧 |
| 2 | `Capture seq 2 bytes 56`，fd 通向 n3 | `(n1, n3, AppendEntries, seq=2)` | `deliver-unordered n1 n3 2` 写出第 2 帧 |

此时 `seq` 同时是「控制器的第 n 帧」和「模型的第 n 条」。接收方拿到的字节就是模型记录所描述的那条。

### 例 2：代码多发了，`seq` 还在，对齐断了

第 2 轮的形状是：`HandleRequestVoteResponse` 让 s1 成为领导者。公式只把投票响应从网络里拿走，没有再发。源码 `raft_become_leader` 在同一次返回前给另外两个节点各发一条空 AE。

生成器没有为这两次发送调用 `capture()`，它的计数停在原地。控制器照单全收：

```text
Capture seq 1 bytes 56    # 实际是 n1 → n2 的空 AE
Capture seq 2 bytes 56    # 实际是 n1 → n3 的空 AE
```

模型下一步若写出它认为的第 1 条消息，生成器发出 `deliver-unordered n1 n2 1`。控制器把 `messages_array[0]` 写回 n2。那是更早的空 AE，不是模型这一步的载荷。后面每条都错一位。`compare net-len` 能看见条数已经差 2，但即使先忽略条数，按 `seq` 投递也会把错的字节交给接收方。

所以 `seq` 没有变成空号。第 1 帧仍然是第 1 帧。失效的是「生成器的 1 = 模型这一步要投的那条」。多出来的发送插进全局数组的前面，后面的编号全部平移。少发则相反：生成器的 `seq` 超过 `messages_array.size()`，`deliver` 打出 `Unordered deliver out of boundary` 并失败。

生成器若能预知这次多发，可以 `capture(..., accounted=False)` 把计数补齐，再 `clear n1 n2` 把代码多出来、模型没有的帧从队列清掉。`clear_channel_msgs` 清的是队列，不从 `messages_array` 里删，也不占用 `dropped_seqs`。清完之后这条通道上不能再 `deliver-unordered`：队列空了，`try_dequeue` 失败，函数返回，哪怕数组里还留着那些字节。这只适合「模型根本没有这条消息」。模型仍要投递的消息不能清。

### 例 3：`drop-unordered` 丢的不是这个 `seq` 的字节

n1→n2 的队列里按到达顺序有两帧，全局序号是 1 和 3（序号 2 在 n1→n3 上）。执行 `drop-unordered n1 n2 3`：

- 检查 3 没有越界、没有被丢过。
- `try_dequeue` 丢掉的是队头，也就是序号 1 那一帧在队列里的副本。
- 把 `3` 放进 `dropped_seqs`。

之后 `deliver-unordered n1 n2 3` 在写任何字节之前就失败，因为序号 3 被标记为已丢。序号 1 的字节还在 `messages_array[0]` 里，但它的队列副本已经没了，再投递它也会因为队列空而失败。丢弃关系是「这个序号以后不能投」加上「这条通道的队头少一帧」，不是「删掉序号 3 的那 56 字节」。

`duplicate-unordered n1 n2 1` 才按序号取字节：把 `messages_array[0]` 再入队，并 `push_back` 一个新捕获，日志是 `Capture seq N duplicate of 1`。新序号可以再投一次，写出去的仍是当初那一帧，目的 fd 也仍是当初的 n2。

### 例 4：`BroadcastAppendEntries` 的子集，哪些做得到

起点公式允许领导者任选一个非空子集。源码按节点名先 n2 后 n3，只有需要快照时才停。给定 `nextIndex`，代码发出的集合是唯一的。分三种情况：

1. 模型要的集合正好是代码发出的那个前缀。用例 1，`seq` 对齐，直接投递。第 5 轮把 `CHOOSE` 改成这个前缀，就是为了落进这一格。
2. 模型要的是代码发出集合的真子集，而且领导者的本地变量不因为「发过」而和模型分叉。生成器把多出来的记成 `accounted=False`，用 `clear` 或 `drop-unordered` 让网络袋和模型一致。这是在补一次模型没有写出的丢包。TCP 做得到，因为字节已经在数组里，只是不写给接收方。它没有让代码「少执行一次 send」。
3. 模型要一条代码没发过的消息，或同一对节点上内容不同的消息。例如模型只发给 n3，代码却先发给了 n2 再发给 n3，且模型认为 n3 那条的 `mentries` 和代码实际打出来的不一样。控制器没有「按内容构造一帧」的 TCP 命令，也不能改 `messages_array` 里的载荷，也不能把 n2 那一帧的 fd 改成 n3。这种迹回放不了。

因此随机子集没有一个投递层的技巧可以普遍做对。实现做得到、且本地状态一致的那些子集，用丢弃补齐。其余的要么改公式去跟源码的前缀，要么承认那是协议允许、这个二进制走不到的迹。

## 任务 5.2 的回答

节点按加入顺序是 n1、n2、n3，n1 是领导者，且 n2、n3 都不需要快照。`raft_send_appendentries_all` 跳过自己，先对 n2 调用 `raft_send_appendentries`，返回 0 再对 n3 调用。返回非 0 的那一次，在这里就是已经把快照发出去之后的 `RAFT_ERR_NEEDS_SNAPSHOT`。不需要快照时，这一次调用发出的集合只有 `{n2, n3}`，顺序也只有这一种。

三条迹的判定：

1. 子集 `{n2, n3}`，两条都是 AppendEntries。这是代码会发出的那一次。可以回放。
2. 子集 `{n2}`。代码不会停在 n2。它停在 n2 的唯一情况是 n2 需要快照，而那一次发给 n2 的是快照，不是 AppendEntries，n3 也收不到。起点公式又要求子集里每个节点都 `~NeedsSnapshot`，所以 `{n2}` 既不是正常广播，也不是提前中止。不能当作这一步来回放。若先让代码把两条都发出去，再丢掉通向 n3 的那一帧，网络袋可以变成只有 n2。那是「广播给两人，然后丢包」，公式里没有这个丢包动作，领导者的发送函数也已经对 n3 执行过了。
3. 子集 `{n3}`。循环不会先访问 n3。代码要么两条都发，要么在 n2 处发完快照就返回。模型里只有一条发给 n3 的消息，捕获数组里却先有 n2 的那一帧。按模型的 `seq` 去投，投到的是 n2 的字节。不能回放。

### 这种随机性从哪来

不来自代码。给定节点数组、`nextIndex` 和 `snapshot_last_idx`，`raft_send_appendentries_all` 的前缀是唯一的。没有 `rand`，也不读时钟。

不来自时间。心跳到期只决定这一次函数被调用。调用之后发给谁，由节点数组和快照条件决定。

不来自网络。丢包、重复、延迟是消息已经发出之后的事。这一步是在决定 `send` 调用哪些节点。

它来自规格用集合代替了数组。注释写了两句：实现里的中止位置依赖于迭代顺序；TLA+ 里用非确定选择来表示中止是否发生。`Server` 是集合，没有下标。作者没有引入一条和 `nodes[]` 一致的序列，而是写成

```tla
\E peers \in SUBSET (Server \ {i}) :
    /\ peers # {}
    /\ \A p \in peers : ~NeedsSnapshot(i, p)
```

「中止或不中止」在固定顺序下只会产生一个前缀：从第一个节点到第一个需要快照的节点之前。上面这个式子比前缀宽。`{n3}`、`{n2}` 在 n2 不需要快照时都不是任何一次中止的结果，公式仍允许。这是为了避开「集合没有顺序」，把实现的一个前缀放大成了所有不含快照节点的非空子集。放大之后，TLC 能采样出这个二进制走不到的迹。

第 10 轮的公式把这件事收了回去：`PeerSeq` 用固定的 `ServerSeq`，`cut` 是这条序列上第一个需要快照的位置。发出去的是前缀上的 AppendEntries，加上中止点上的那一条快照。`CHOOSE` 还在，但谓词只让一个 `k` 成立，所以它不再产生多个子集。

### 四种来源，以及各自怎么处理

这个分类可以用。每一种的处理方式不同，而且「简化」那一种不是还没法定。

网络。丢、重复、乱序、何时投递，留给网络动作。发送动作只描述这次调用写出的字节。SandTable 的控制器用 `drop-unordered`、`duplicate-unordered` 和投递时机做这件事。公式里若把「少发给某个节点」写进发送动作，回放时就分不清这是代码没发，还是网络丢掉了。

时间。超时是一次事件：选举定时器到期，或心跳定时器到期。驱动触发事件，公式用两个动作分开，而不是在一个动作内部用 `\/` 猜测时钟。`HandleRequestVoteRequest` 里曾经出现的分支不是超时随机性。源码在 `current_leader` 指向别人且 `timeout_elapsed < election_timeout` 时拒绝。公式没写 `currentLeader`，于是两条分支同时可走。那是漏了状态，补上变量之后分支互斥。

规格放大。处理方式是分开两份规格。回放用的那份把守卫写成和这次调用相同的前缀，采样出来的迹才能执行。协议规格可以保留更大的集合，用来说明实现比协议窄，但那些迹不交给控制器。不需要改二进制去实现一个它没有的子集。

代码自身在分支里使用了随机数，而且这个选择从外部看不见。选举超时的抖动不是这种。它只改变定时器何时到期，仍按「事件」处理。广播子集也不是这种。真正需要动代码，是选择发生在进程内部、拦截器只能看见结果、而同一次输入会发出不同字节。那时才在被测程序里把选择变成可注入的事件。wraft 的这次广播不需要。

还有一种不在这四类里。SandTable 的 `AppendEntriesAll` 用 `CHOOSE j \in 剩余节点 : TRUE` 把集合排成序列，再沿这个顺序做提前中止，并用 `_BatchAddmsgs` 按这个顺序分配 `seq`。TLA+ 的 `CHOOSE` 在多个元素满足时不规定选哪一个，但 TLC 对同一个集合总是选它内部顺序下的同一个元素，所以模型检测不会把多种顺序都跑出来。这不是「公式证明了顺序无关」，而是检查器把一种未写明的顺序冻结了。冻结后的顺序仍可能和 `nodes[]` 的加入顺序不同。顺序不同，`seq` 就和捕获编号错位。

### SandTable 的模型并没有把随机性去掉

`AppendEntriesAll` 的形状确实更接近源码：遍历每个其他节点，遇到需要快照的节点就把它算进去然后停下，而不是 `\E peers \in SUBSET`。没有快照时，接收方的集合是全部其他节点，这一点和代码一致。这是它比起点 `BroadcastAppendEntries` 好的地方。

它并没有一条「不要随机性」的原则。同一段递归里，下一个节点仍是 `CHOOSE`。`RequestVoteAll` 也是同一写法。没有人需要快照时，TLC 只探索一种发送顺序；有人需要快照时，谁排在前面会改变谁收到消息，只是 TLC 不把其他排法算出来。另外，`AddMsg` 在 `ScrNodeConnected` 为假时直接不把消息放进网络，也不占用 `seq`。分区造成的少发写在发送里面，不是一个独立的丢包动作。

他们的生成器把模型消息上的 `seq` 原样放进 `deliver-unordered`：

```python
def deliver(src, dst, seq):
    yield ['deliver-unordered', src, dst, str(seq)]
```

这里的 `seq` 能当主键，是因为他们把公式改到和这次调用的发送序列一致，并且假定 TLC 排出的顺序等于拦截器观察到的顺序。一致性一旦破掉，同一个生成器会把错的捕获帧写回去。起点公式若直接接上这个生成器，`{n3}` 那条迹的 `seq` 就对不上。`seq` 是序列中的位置。规格要提供和代码相同的序列，而不是仅仅把 `\E` 写掉。没有 `\E` 的一份错误顺序，同样不能用 `seq` 当主键。

## 任务 6 的回答

TLA 的 action 是状态和下一状态的关系，不是函数。函数是实现里的一次调用。两件事「在同一个 function 里」的意思是：在被测进程回到事件循环之前，中间状态不会成为下一次受控步的起点。

所以合并不是逻辑上永远必要，而是由可见的让出点决定。SandTable 能看见的让出点，是一次 `execute` 返回。两次返回之间源码做完的事，实现里没有单独的状态。规格若把它们拆开，状态空间里就多出一类状态：第一段已经发生，第二段还没有。

用你的例子。`action1` 返回前一定会执行 `send1`。模型采样出 `action1`，然后别的服务器走了很多步，很久以后才出现 `send1`。回放做不到：`action1` 的那次调用返回时，字节已经在控制器的捕获数组里。模型的网络袋里还没有这条消息。下一步无论投递还是丢弃，对不上。`action1` 之后该服务器不再动作、直到模型写出 `send1`，同样对不上，因为发送已经在第一次返回里发生了。进程崩溃插在两次 `execute` 之间，也杀不掉函数中间那一段；当前的崩溃是调用之间的，不是调用内部的。

这些迹不是「协议上非法」。它们是这个二进制到不了的状态。协议完全可以允许「先记下日志，崩溃，再发送」；操作系统也确实能在 `send` 系统调用之前杀掉进程。当前这套受控执行没有那个让出点，所以这类迹不能拿来回放。把它们留在协议规格里是有意义的，那是更大的状态空间。把它们放进用来采样回放的规格里，采样器会不断产生无法执行的迹。

因此两份规格不要合成一份：

- 协议规格按协议的原子性写。动作可以比函数细。它用来讲安全性，也用来留下实现到不了、但协议允许的空隙。
- 回放规格的原子性等于执行器能看见的让出点。同一次返回里的效果放进同一步。这就是这次把发送并回 `HandleRequestVoteResponse`、`ClientRequest`、`HandleAppendEntriesResponse`、`TakeSnapshot` 的原因。并回去之后，采样出来的迹才是这个二进制的迹。

合并的代价是：函数中间的崩溃、以及「只做了前半段」的交错，从回放规格里消失。那不是把它们宣判为非法，而是承认当前执行器看不见它们。若以后能在调用内部让出（信号、断点、或者系统调用前的崩溃注入），让出点变了，回放规格的动作边界要跟着拆开，协议规格不用改。

这个划分不依赖 Raft。任何系统都一样：执行器只能在它能停住的地方对齐模型。停不住的地方拆成两个 action，得到的是更细的规格，不是更多可回放的迹。
