---
name: 大数据故障排查
description: 大数据平台故障排查手册。Flink/YARN/Doris/ClickHouse/DolphinScheduler/HDFS/Kafka/SeaTunnel
  常见故障现象→根因→修复方案。当大数据智能体遇到系统报错、作业失败、性能下降、集群异常时加载此技能。
---

# 大数据平台故障排查手册

适用场景：大数据智能体在 Dinky/Flink/YARN/Doris/ClickHouse/DolphinScheduler/HDFS/Kafka/SeaTunnel 等系统遇到报错、作业失败、性能下降时，按本手册定位根因并给出修复方案。

---

## 1. Flink / Dinky 作业故障

### 1.1 作业启动失败

| 症状 | 可能原因 | 排查步骤 | 修复方案 |
|------|---------|---------|---------|
| `No space left on device` | 磁盘满 | 查 YARN 节点磁盘 → `yarn list_nodes` | 清理日志/临时文件，扩容磁盘 |
| `Could not build ClassLoader` | Jar 包冲突 | 查作业依赖树 | shade 打包排除冲突依赖 |
| `Connection refused` | 外部服务不可达 | 检查目标数据源连通性 | 修复网络/服务 |
| `Insufficient number of network buffers` | 内存不足 | 查 TaskManager 内存配置 | 调大 `taskmanager.memory.network.fraction` |
| `JobManager 高可用切换中` | JM 故障转移 | 查 JM 日志和 ZK 状态 | 等待自动切换完成或手动重启 JM |

### 1.2 作业运行中失败

| 症状 | 可能原因 | 排查步骤 | 修复方案 |
|------|---------|---------|---------|
| `Checkpoint expired` | Checkpoint 超时 | 查 CP 耗时 → 反压链路 | 增大 `checkpointing.timeout` 或优化反压 |
| `OutOfMemoryError: Java heap` | 堆内存不足 | 查 GC 日志 → 算子状态大小 | 增大 `taskmanager.memory.task.heap.size` |
| `Too many open files` | 文件句柄泄漏 | `ulimit -a` 检查 | 增大系统 `ulimit`，检查 Sink 是否正确关闭连接 |
| `Kafka OffsetOutOfRange` | 消费位点过期 | 查 Kafka Topic 保留策略 | 重置 offset：`--offset-reset-strategy earliest` |
| `SplitNotFoundException` | 上游数据源表结构变更 | 比对上下游 Schema | 重启作业或兼容 Schema 变更 |

### 1.3 反压（Backpressure）排查

```
排查路径：
1. Flink Web UI → 反压百分比 → 定位反压算子
2. 查反压算子的 CPU / GC / 网络指标
3. 常见根因：
   - 下游 Sink 写入慢（数据库瓶颈）→ 限流 / 批量写入
   - 窗口/聚合算子数据倾斜 → 加盐打散 key
   - 序列化/反序列化慢 → 用 POJO 替代 GenericType
   - GC 停顿 → 用 RocksDB 状态后端
```

### 1.4 数据倾斜

```
症状：个别 Task 数据量远超其他 Task
排查：
1. Flink UI → SubTasks Metrics → Bytes Sent/Received
2. 对比各 subtask 的处理数据量
修复：
- Key 加随机前缀：CONCAT(CAST(RAND()*10 AS STRING), '_', key)
- 两阶段聚合：先局部聚合，再全局聚合
- 使用 Flink 的 Rebalance 或 Rescale 分区策略
```

---

## 2. YARN 资源问题

### 2.1 应用状态异常

| 症状 | 可能原因 | 排查步骤 | 修复方案 |
|------|---------|---------|---------|
| `ACCEPTED` 长时间不运行 | 队列资源不足 | `yarn scheduler_info` 查队列用量 | 调整队列容量 / 杀低优先级应用 |
| `FAILED` + `Application killed` | 超出资源限制 | `yarn get_app_detail` 查诊断信息 | 增大 `yarn.scheduler.maximum-allocation-mb` |
| `KILLED` by AM | 内存超限 | 查 Container 日志 | 增大 `mapreduce.map.memory.mb` 或 Flink TM 内存 |
| NodeManager 状态 `LOST` | 节点宕机 | SSH 到节点 → 查系统日志 | 重启 NodeManager，检查硬件 |

### 2.2 资源不足快速处理

```bash
# 查看集群资源概况
yarn cluster_metrics

# 查看各队列使用情况
yarn scheduler_info

# 杀掉低优先级应用释放资源
yarn kill_app <appId>

# 查看节点资源
yarn list_nodes
```

---

## 3. Doris / StarRocks / ClickHouse 查询问题

### 3.1 查询慢

| 症状 | 可能原因 | 排查步骤 | 修复方案 |
|------|---------|---------|---------|
| 全表扫描 | 缺少分区/索引 | `EXPLAIN` 查执行计划 | 建分区表 / Bitmap 索引 / 物化视图 |
| 数据倾斜 | 分桶键选择不当 | 查 BE 节点数据分布 | 重新分桶（`DISTRIBUTED BY HASH`） |
| Join 慢 | 大表 BroadCast | `EXPLAIN` 看 Join 策略 | 大表用 Shuffle Join，小表用 Broadcast |
| 内存不足 | 大查询 OOM | 查 BE/FE 内存指标 | 限制并发查询数，调大 `exec_mem_limit` |

### 3.2 Doris BE 节点异常

```
排查路径：
1. list_backends → 查节点状态（Alive/Dead/TabletNum）
2. Dead 节点 → SSH → 查 be.out 日志
3. 常见原因：
   - 磁盘满 → 清理 trash/临时文件
   - OOM → 调大 be.conf 的 memory_limit
   - 网络分区 → 检查集群网络连通性
```

### 3.3 ClickHouse 特有问题

| 症状 | 原因 | 修复 |
|------|------|------|
| `Too many parts` | Merge 跟不上写入 | 减小写入频率 / 调大 `max_parts_in_total` |
| `Memory limit exceeded` | 查询内存超限 | 设置 `max_memory_usage` / 优化查询 |
| `Replication lag` | 副本同步延迟 | 检查 ZK 连接 / 网络带宽 |

---

## 4. DolphinScheduler 调度问题

### 4.1 任务失败

| 症状 | 可能原因 | 排查步骤 | 修复方案 |
|------|---------|---------|---------|
| `Task execution timeout` | 超时阈值太小 | 查任务实际耗时 | 增大超时时间 |
| `Dependent task not finished` | 依赖任务未完成 | 查上游任务状态 | 修复上游任务或调整依赖关系 |
| `Worker group not found` | Worker 分组不存在 | 查 Worker 分组配置 | 修正任务的 Worker 分组 |
| `Resource not found` | 资源文件被删 | 查资源中心 | 重新上传资源文件 |
| `SQL task error` | SQL 执行失败 | 查任务日志 → 定位 SQL 错误 | 修复 SQL 语句 |

### 4.2 调度异常

```
排查路径：
1. 查 workflow_instance 状态 → 定位失败节点
2. 查 task_instance 日志 → 获取具体错误
3. 常见场景：
   - 所有任务排队 → Worker 资源不足 → 扩容 Worker
   - 调度不触发 → 检查 Cron 表达式 + 工作流是否上线
   - 重复执行 → 检查是否有多实例策略
```

---

## 5. HDFS 存储问题

### 5.1 常见故障

| 症状 | 可能原因 | 排查步骤 | 修复方案 |
|------|---------|---------|---------|
| `Safe mode is ON` | NameNode 安全模式 | 查 NN 日志 → 等待副本达标 | `hdfs dfsadmin -safemode leave` |
| `No space left` | 磁盘满 | `hdfs content_summary` 查用量 | 清理过期数据 / 扩容 DataNode |
| `Under-replicated blocks` | 副本不足 | `hdfs fsck /` 检查 | 修复 DataNode / 等待自动复制 |
| `Cannot create file` | NameNode 压力大 | 查 NN RPC 队列 | 增大 `dfs.namenode.handler.count` |

### 5.2 快速诊断

```bash
# 查看 HDFS 总体使用情况
hdfs_content_summary(path="/")

# 检查文件系统健康
hdfs fsck / -files -blocks -locations

# 查看 DataNode 状态
# 通过 NameNode Web UI: http://namenode:9870/dfshealth.html
```

---

## 6. Kafka 消息队列问题

### 6.1 消费积压（Lag 堆积）

```
排查路径：
1. list_consumer_groups → 找到 Lag 大的消费者组
2. get_consumer_group → 查各分区 Lag
3. 常见原因：
   - 消费者处理慢 → 优化消费逻辑 / 增加消费者实例
   - 消费者挂了 → 重启消费者
   - 分区数不足 → 增加 Topic 分区
   - 数据倾斜 → 检查消息 Key 分布
```

### 6.2 生产/消费异常

| 症状 | 可能原因 | 修复方案 |
|------|---------|---------|
| `NotLeaderForPartition` | Leader 选举中 | 等待选举完成 / 检查 Broker 状态 |
| `RecordTooLargeException` | 消息超大 | 调大 `max.message.bytes` |
| `OffsetCommitFailed` | 消费者组 rebalance | 检查 `session.timeout.ms` |
| Broker `UnderReplicatedPartitions` | 副本同步异常 | 检查 Broker 网络 / ISR 列表 |

---

## 7. SeaTunnel / DataX 数据同步问题

### 7.1 同步任务失败

| 症状 | 可能原因 | 修复方案 |
|------|---------|---------|
| `Connection timeout` | 源/目标数据库不可达 | 检查网络和数据库状态 |
| `Column count mismatch` | 源表结构变更 | 更新同步配置中的字段映射 |
| `Duplicate key` | 主键冲突 | 配置 `replace into` 或 `ON DUPLICATE KEY UPDATE` |
| `Out of memory` | 单批数据量太大 | 减小 `batch_size` / 增大执行器内存 |

### 7.2 数据一致性

```
排查路径：
1. 对比源表和目标表的行数
2. 抽样对比关键字段值
3. 常见原因：
   - CDC 延迟 → 检查 Binlog 位点
   - 类型转换丢失精度 → 统一字段类型
   - NULL 值处理不一致 → 配置 null 值策略
```

---

## 8. 通用排查流程

```
遇到问题时的标准排查路径：

1. 确认现象
   - 哪个系统？哪个作业/任务？
   - 什么时候开始的？影响范围？

2. 收集信息
   - 查看系统状态（集群/节点/资源）
   - 查看错误日志和诊断信息
   - 检查最近是否有变更（配置/代码/数据量）

3. 定位根因
   - 从错误信息出发 → 查找对应章节
   - 关联多个系统信息交叉验证

4. 执行修复
   - 先止血（杀异常作业/重启服务）
   - 再治本（修复代码/调优配置/扩容资源）

5. 验证恢复
   - 确认作业恢复正常
   - 监控一段时间确认稳定
```
