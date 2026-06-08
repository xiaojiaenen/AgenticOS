"""大数据生态外部系统预设定义。

包含数据开发、调度、存储、OLAP、数据集成、数据治理、BI 监控等 20+ 系统。
每个预设定义了 name、description、auth_type、credential_template 和 apis。
"""

# ── 一、数据开发与计算引擎 ─────────────────────────────────────────────

DINKY = {
    "name": "Dinky",
        "category": "compute",
    "description": "基于 Apache Flink 的实时数据开发平台。支持 Flink SQL 开发调试、作业提交部署、运行监控、数据血缘。"
                   "提供 OpenAPI，可通过 API 实现 Flink 作业的全生命周期管理。",
    "base_url": "http://your-dinky-host:8888",
    "auth_type": "jwt_login",
    "credential_template": {"fields": [
        {"key": "username", "label": "用户名", "type": "text", "required": True, "help_text": "Dinky 平台登录用户名"},
        {"key": "password", "label": "密码", "type": "password", "required": True, "help_text": "Dinky 平台登录密码"},
    ]},
    "jwt_login_url": "/api/v1/login",
    "jwt_request_body_template": '{"username": "{username}", "password": "{password}"}',
    "jwt_response_token_path": "data.token",
    "jwt_response_expires_path": "",
    "apis": [
        {"name": "list_jobs", "display_name": "获取作业列表", "method": "GET", "path": "/api/v1/jobInstance/list",
         "description": "查询所有 Flink 作业实例，返回作业名称、状态、提交时间等信息"},
        {"name": "get_job_detail", "display_name": "获取作业详情", "method": "GET", "path": "/api/v1/jobInstance/{id}",
         "description": "获取指定作业的详细信息，包括配置、状态、Flink JobId"},
        {"name": "save_task", "display_name": "保存 Flink SQL 任务", "method": "POST", "path": "/api/v1/task",
         "description": "保存一个新的 Flink SQL 任务定义（不立即提交）"},
        {"name": "submit_task", "display_name": "提交任务到集群", "method": "POST", "path": "/api/v1/task/submit",
         "description": "将 Flink SQL 任务提交到 Flink 集群执行"},
        {"name": "cancel_task", "display_name": "取消任务", "method": "GET", "path": "/api/v1/task/cancel",
         "description": "取消正在运行的 Flink 任务，触发 Savepoint 后停止"},
        {"name": "restart_task", "display_name": "重启任务", "method": "GET", "path": "/api/v1/task/restart",
         "description": "从最近的 Savepoint 重启 Flink 任务"},
        {"name": "list_catalogs", "display_name": "获取数据目录", "method": "GET", "path": "/api/v1/catalog/list",
         "description": "获取已注册的 Flink Catalog 列表（数据库、表等元信息）"},
        {"name": "execute_sql", "display_name": "执行 SQL 语句", "method": "POST", "path": "/api/v1/studio/execute",
         "description": "在 Dinky 中执行 Flink SQL 语句，返回执行结果（SELECT/SHOW/DESCRIBE 等）"},
        {"name": "get_job_log", "display_name": "获取作业日志", "method": "GET", "path": "/api/v1/jobInstance/log",
         "description": "获取指定作业的运行日志，用于排查错误"},
    ],
}

SPARK = {
    "name": "Apache Spark",
        "category": "compute",
    "description": "Apache Spark 统一计算引擎。支持大规模批处理、流处理、机器学习和图计算。"
                   "通过 Spark Thrift Server（JDBC/HTTP）提供 SQL 查询能力，兼容 Hive SQL 语法。",
    "base_url": "http://your-spark-thriftserver:10000",
    "auth_type": "basic",
    "credential_template": {"fields": [
        {"key": "username", "label": "用户名", "type": "text", "required": True, "help_text": "Spark Thrift Server 用户名（无认证可填任意值）"},
        {"key": "password", "label": "密码", "type": "password", "required": False, "help_text": "密码（无认证可留空）"},
    ]},
    "apis": [
        {"name": "get_server_info", "display_name": "获取服务信息", "method": "GET", "path": "/info",
         "description": "获取 Spark Thrift Server 版本和状态信息"},
        {"name": "get_server_status", "display_name": "获取服务状态", "method": "GET", "path": "/api/v1/status",
         "description": "检查 Thrift Server 是否正常运行"},
    ],
}

FLINK_NATIVE = {
    "name": "Apache Flink",
        "category": "compute",
    "description": "Apache Flink 原生 REST API（非 Dinky 管理）。直接与 Flink JobManager 交互，"
                   "管理作业、Savepoint、集群配置。适用于非 Dinky 管理的独立 Flink 集群。",
    "base_url": "http://your-jobmanager:8081",
    "auth_type": "basic",
    "credential_template": {"fields": [
        {"key": "username", "label": "用户名", "type": "text", "required": False, "help_text": "JobManager 认证用户名（无认证可留空）"},
        {"key": "password", "label": "密码", "type": "password", "required": False, "help_text": "JobManager 认证密码（无认证可留空）"},
    ]},
    "apis": [
        {"name": "cluster_overview", "display_name": "集群概览", "method": "GET", "path": "/overview",
         "description": "获取 Flink 集群概览：版本、TaskManager 数量、总 Slot 数、可用 Slot"},
        {"name": "list_jobs", "display_name": "获取作业列表", "method": "GET", "path": "/jobs",
         "description": "列出所有作业及其状态（RUNNING/FINISHED/CANCELED/FAILED 等）"},
        {"name": "get_job_detail", "display_name": "获取作业详情", "method": "GET", "path": "/jobs/{jobid}",
         "description": "获取指定作业的详细信息，包括执行图、指标、异常信息"},
        {"name": "cancel_job", "display_name": "取消作业", "method": "PATCH", "path": "/jobs/{jobid}",
         "description": "取消正在运行的作业（触发 Savepoint）"},
        {"name": "trigger_savepoint", "display_name": "触发 Savepoint", "method": "POST", "path": "/jobs/{jobid}/savepoints",
         "description": "手动触发 Savepoint，用于作业恢复或版本升级"},
        {"name": "list_taskmanagers", "display_name": "TaskManager 列表", "method": "GET", "path": "/taskmanagers",
         "description": "获取所有 TaskManager 的状态、资源、日志路径"},
    ],
}

TRINO = {
    "name": "Trino",
        "category": "compute",
    "description": "Trino 分布式 SQL 查询引擎（原 PrestoSQL）。支持跨数据源联邦查询，可同时查询 "
                   "MySQL、Hive、Iceberg、Kafka、Elasticsearch 等数十种数据源，无需数据搬迁。",
    "base_url": "http://your-trino-coordinator:8080",
    "auth_type": "basic",
    "credential_template": {"fields": [
        {"key": "username", "label": "用户名", "type": "text", "required": True, "help_text": "Trino 用户名"},
    ]},
    "apis": [
        {"name": "cluster_info", "display_name": "集群信息", "method": "GET", "path": "/v1/info",
         "description": "获取 Trino 集群版本和状态"},
        {"name": "list_queries", "display_name": "查询列表", "method": "GET", "path": "/v1/query",
         "description": "列出当前正在运行和最近完成的查询"},
        {"name": "get_query_info", "display_name": "查询详情", "method": "GET", "path": "/v1/query/{queryId}",
         "description": "获取指定查询的执行详情、耗时、数据量"},
        {"name": "cancel_query", "display_name": "取消查询", "method": "DELETE", "path": "/v1/query/{queryId}",
         "description": "取消正在执行的查询"},
    ],
}

DORIS = {
    "name": "Apache Doris",
        "category": "compute",
    "description": "Apache Doris 实时分析数据库。支持高并发低延迟的即席查询，兼容 MySQL 协议。"
                   "适用于实时报表、多维分析、用户画像、日志分析等场景。",
    "base_url": "http://your-fe-host:8030",
    "auth_type": "basic",
    "credential_template": {"fields": [
        {"key": "username", "label": "用户名", "type": "text", "required": True, "help_text": "Doris FE 用户名"},
        {"key": "password", "label": "密码", "type": "password", "required": True, "help_text": "Doris FE 密码"},
    ]},
    "apis": [
        {"name": "list_backends", "display_name": "BE 节点列表", "method": "GET", "path": "/rest/v2/manager/node/backends",
         "description": "获取所有 Backend 节点状态、磁盘使用、负载信息"},
        {"name": "list_frontends", "display_name": "FE 节点列表", "method": "GET", "path": "/rest/v2/manager/node/frontends",
         "description": "获取所有 Frontend 节点状态"},
        {"name": "query_profile", "display_name": "查询 Profile", "method": "GET", "path": "/rest/v2/manager/query/query_info",
         "description": "获取最近执行的查询列表及其耗时"},
        {"name": "get_query_plan", "display_name": "查询执行计划", "method": "GET", "path": "/rest/v2/manager/query/sql/{query_id}",
         "description": "获取指定查询的 SQL 和文本执行计划"},
        {"name": "list_tables", "display_name": "获取表列表", "method": "GET", "path": "/api/show_data",
         "description": "获取数据库中的表列表和数据量信息"},
    ],
}

STARROCKS = {
    "name": "StarRocks",
        "category": "compute",
    "description": "StarRocks 高性能分析型数据库。支持极速多维分析、实时数据仓库、联邦查询。"
                   "兼容 MySQL 协议，提供 HTTP SQL API 可直接执行 SQL 查询。",
    "base_url": "http://your-fe-host:8030",
    "auth_type": "basic",
    "credential_template": {"fields": [
        {"key": "username", "label": "用户名", "type": "text", "required": True, "help_text": "StarRocks 用户名"},
        {"key": "password", "label": "密码", "type": "password", "required": True, "help_text": "StarRocks 密码"},
    ]},
    "apis": [
        {"name": "list_be_nodes", "display_name": "BE 节点列表", "method": "GET", "path": "/api/show_backends",
         "description": "获取所有 BE 节点状态和资源使用情况"},
        {"name": "list_fe_nodes", "display_name": "FE 节点列表", "method": "GET", "path": "/api/show_frontends",
         "description": "获取所有 FE 节点状态"},
        {"name": "list_databases", "display_name": "数据库列表", "method": "GET", "path": "/api/show_database",
         "description": "获取所有数据库列表"},
        {"name": "list_tables", "display_name": "表列表", "method": "GET", "path": "/api/show_tables",
         "description": "获取指定数据库下的表列表"},
        {"name": "execute_sql", "display_name": "执行 SQL", "method": "POST", "path": "/api/v1/catalogs/{catalog}/databases/{database}/query",
         "description": "通过 HTTP SQL API 执行 SELECT/SHOW/EXPLAIN 语句"},
    ],
}

CLICKHOUSE = {
    "name": "ClickHouse",
        "category": "compute",
    "description": "ClickHouse 列式分析型数据库。极致的查询性能，支持实时数据写入和分析。"
                   "通过 HTTP 接口可直接执行 SQL，适用于日志分析、实时指标、用户行为分析。",
    "base_url": "http://your-clickhouse:8123",
    "auth_type": "basic",
    "credential_template": {"fields": [
        {"key": "username", "label": "用户名", "type": "text", "required": True, "help_text": "ClickHouse 用户名"},
        {"key": "password", "label": "密码", "type": "password", "required": True, "help_text": "ClickHouse 密码"},
    ]},
    "apis": [
        {"name": "cluster_info", "display_name": "集群信息", "method": "GET", "path": "/?query=SELECT+*+FROM+system.clusters+LIMIT+10",
         "description": "获取 ClickHouse 集群配置信息"},
        {"name": "list_databases", "display_name": "数据库列表", "method": "GET", "path": "/?query=SHOW+DATABASES",
         "description": "列出所有数据库"},
        {"name": "list_tables", "display_name": "表列表", "method": "GET", "path": "/?query=SHOW+TABLES+FROM+{database}",
         "description": "列出指定数据库下的所有表"},
        {"name": "execute_query", "display_name": "执行 SQL 查询", "method": "POST", "path": "/?query={sql}",
         "description": "通过 HTTP 接口执行 SQL 查询，返回结果"},
        {"name": "server_status", "display_name": "服务状态", "method": "GET", "path": "/ping",
         "description": "检查 ClickHouse 服务是否正常（返回 Ok）"},
        {"name": "list_processes", "display_name": "运行中的查询", "method": "GET", "path": "/?query=SELECT+*+FROM+system.processes",
         "description": "查看当前正在执行的查询列表"},
    ],
}

HIVE = {
    "name": "Apache Hive",
        "category": "compute",
    "description": "Apache Hive 数据仓库基础设施。基于 Hadoop 的数据仓库工具，将结构化数据映射为表，"
                   "提供 HiveSQL 查询能力。通过 HiveServer2 Thrift 接口或 HTTP API 对外服务。",
    "base_url": "http://your-hiveserver2:10002",
    "auth_type": "basic",
    "credential_template": {"fields": [
        {"key": "username", "label": "用户名", "type": "text", "required": True, "help_text": "Hive 用户名"},
        {"key": "password", "label": "密码", "type": "password", "required": False, "help_text": "密码（无认证可留空）"},
    ]},
    "apis": [
        {"name": "server_info", "display_name": "服务信息", "method": "GET", "path": "/info",
         "description": "获取 HiveServer2 版本和状态信息"},
        {"name": "server_status", "display_name": "服务状态", "method": "GET", "path": "/api/v1/status",
         "description": "检查 HiveServer2 是否正常运行"},
    ],
}

# ── 二、任务调度与工作流 ──────────────────────────────────────────────

DOLPHIN_SCHEDULER = {
    "name": "DolphinScheduler",
        "category": "scheduler",
    "description": "Apache DolphinScheduler 分布式工作流调度平台。可视化 DAG 编排，支持 Shell/SQL/Spark/Flink/"
                   "Python 等 30+ 任务类型。提供完善的 REST API，支持工作流的创建、上线、执行和监控。",
    "base_url": "http://your-ds-host:12345",
    "auth_type": "token",
    "credential_template": {"fields": [
        {"key": "token", "label": "Token", "type": "password", "required": True,
         "help_text": "在 DolphinScheduler 安全中心 → 令牌管理 中创建 API Token",
         "help_url": "https://dolphinscheduler.apache.org/zh-cn/docs/latest/user_guide/token"},
    ]},
    "apis": [
        {"name": "list_projects", "display_name": "获取项目列表", "method": "GET", "path": "/projects",
         "description": "获取所有项目列表，返回项目编码、名称、描述"},
        {"name": "list_workflows", "display_name": "获取工作流列表", "method": "GET",
         "path": "/projects/{projectCode}/process-definition",
         "description": "获取指定项目下的所有工作流定义"},
        {"name": "get_workflow_detail", "display_name": "获取工作流详情", "method": "GET",
         "path": "/projects/{projectCode}/process-definition/{code}",
         "description": "获取工作流的 DAG 定义、任务节点、依赖关系"},
        {"name": "online_workflow", "display_name": "上线工作流", "method": "POST",
         "path": "/projects/{projectCode}/process-definition/{code}/online",
         "description": "将工作流上线（发布），上线后才能被调度执行"},
        {"name": "offline_workflow", "display_name": "下线工作流", "method": "POST",
         "path": "/projects/{projectCode}/process-definition/{code}/offline",
         "description": "将工作流下线，暂停调度执行"},
        {"name": "run_workflow", "display_name": "运行工作流", "method": "POST",
         "path": "/projects/{projectCode}/executors/start-process-instance",
         "description": "手动触发工作流执行，可指定参数和告警策略"},
        {"name": "list_workflow_instances", "display_name": "查询执行实例", "method": "GET",
         "path": "/projects/{projectCode}/process-instances",
         "description": "查询工作流的执行历史，包括状态、耗时、开始/结束时间"},
        {"name": "list_task_instances", "display_name": "查询任务实例", "method": "GET",
         "path": "/projects/{projectCode}/task-instances",
         "description": "查询工作流中各任务的执行详情"},
        {"name": "delete_workflow", "display_name": "删除工作流", "method": "DELETE",
         "path": "/projects/{projectCode}/process-definition/{code}",
         "description": "删除指定工作流定义（需先下线）"},
    ],
}

AIRFLOW = {
    "name": "Apache Airflow",
        "category": "scheduler",
    "description": "Apache Airflow 工作流编排平台。用 Python 代码定义 DAG，支持复杂的任务依赖、"
                   "回填、参数化执行。通过 REST API 管理 DAG 触发、任务监控和日志查看。",
    "base_url": "http://your-airflow-host:8080",
    "auth_type": "basic",
    "credential_template": {"fields": [
        {"key": "username", "label": "用户名", "type": "text", "required": True, "help_text": "Airflow Web UI 登录用户名"},
        {"key": "password", "label": "密码", "type": "password", "required": True, "help_text": "Airflow Web UI 登录密码"},
    ]},
    "apis": [
        {"name": "health_check", "display_name": "健康检查", "method": "GET", "path": "/api/v1/health",
         "description": "检查 Airflow 元数据库、调度器和 Executor 状态"},
        {"name": "list_dags", "display_name": "获取 DAG 列表", "method": "GET", "path": "/api/v1/dags",
         "description": "获取所有 DAG 定义，返回 DAG ID、调度计划、是否暂停"},
        {"name": "get_dag_detail", "display_name": "获取 DAG 详情", "method": "GET", "path": "/api/v1/dags/{dag_id}",
         "description": "获取指定 DAG 的详细配置和调度信息"},
        {"name": "trigger_dag", "display_name": "触发 DAG 运行", "method": "POST", "path": "/api/v1/dags/{dag_id}/dagRuns",
         "description": "手动触发 DAG 执行，可传入配置参数"},
        {"name": "list_dag_runs", "display_name": "获取执行历史", "method": "GET", "path": "/api/v1/dags/{dag_id}/dagRuns",
         "description": "获取 DAG 的执行历史，包括状态、开始/结束时间"},
        {"name": "list_task_instances", "display_name": "获取任务实例", "method": "GET",
         "path": "/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances",
         "description": "获取指定 DAG Run 中各任务的执行状态"},
        {"name": "get_task_logs", "display_name": "获取任务日志", "method": "GET",
         "path": "/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{task_try_number}",
         "description": "获取指定任务的运行日志"},
        {"name": "pause_dag", "display_name": "暂停 DAG", "method": "PATCH", "path": "/api/v1/dags/{dag_id}",
         "description": "暂停/恢复 DAG 调度（设置 is_paused 字段）"},
    ],
}

# ── 三、数据存储 ─────────────────────────────────────────────────────

HDFS = {
    "name": "HDFS",
        "category": "storage",
    "description": "Hadoop 分布式文件系统。通过 WebHDFS REST API 提供文件的浏览、读取、写入、删除等操作。"
                   "支持查看文件状态、目录汇总、文件权限管理。是大数据生态的核心存储层。",
    "base_url": "http://your-namenode:9870",
    "auth_type": "basic",
    "credential_template": {"fields": [
        {"key": "username", "label": "HDFS 用户", "type": "text", "required": True,
         "help_text": "HDFS 操作用户名（如 hdfs、hive 等），会以 user.name 参数传递",
         "help_url": "https://hadoop.apache.org/docs/stable/hadoop-hdfs/WebHDFS.html"},
    ]},
    "apis": [
        {"name": "list_directory", "display_name": "列出目录内容", "method": "GET",
         "path": "/webhdfs/v1/{path}?op=LISTSTATUS&user.name={username}",
         "description": "列出指定目录下的文件和子目录，返回文件名、大小、修改时间、权限"},
        {"name": "file_status", "display_name": "获取文件状态", "method": "GET",
         "path": "/webhdfs/v1/{path}?op=GETFILESTATUS&user.name={username}",
         "description": "获取文件/目录的元信息：类型、大小、副本数、块大小、权限"},
        {"name": "content_summary", "display_name": "目录汇总信息", "method": "GET",
         "path": "/webhdfs/v1/{path}?op=GETCONTENTSUMMARY&user.name={username}",
         "description": "获取目录的汇总信息：总大小、文件数、目录数"},
        {"name": "read_file", "display_name": "读取文件内容", "method": "GET",
         "path": "/webhdfs/v1/{path}?op=OPEN&user.name={username}",
         "description": "读取文件内容（适合文本文件，大文件请用偏移量分段读取）"},
        {"name": "create_directory", "display_name": "创建目录", "method": "PUT",
         "path": "/webhdfs/v1/{path}?op=MKDIRS&user.name={username}",
         "description": "创建新目录（支持递归创建）"},
        {"name": "delete_path", "display_name": "删除文件/目录", "method": "DELETE",
         "path": "/webhdfs/v1/{path}?op=DELETE&user.name={username}",
         "description": "删除指定文件或目录（目录会递归删除）"},
        {"name": "rename_path", "display_name": "重命名/移动", "method": "PUT",
         "path": "/webhdfs/v1/{path}?op=RENAME&destination={destination}&user.name={username}",
         "description": "重命名或移动文件/目录"},
        {"name": "set_permission", "display_name": "设置权限", "method": "PUT",
         "path": "/webhdfs/v1/{path}?op=SETPERMISSION&permission={permission}&user.name={username}",
         "description": "设置文件/目录权限（如 755、777）"},
    ],
}

HBASE = {
    "name": "Apache HBase",
        "category": "storage",
    "description": "Apache HBase 分布式 NoSQL 数据库。基于 HDFS 的列族存储，支持海量数据的随机读写。"
                   "通过 REST API（Stargate）提供数据的 CRUD 操作和表管理。",
    "base_url": "http://your-hbase-rest:8080",
    "auth_type": "basic",
    "credential_template": {"fields": [
        {"key": "username", "label": "用户名", "type": "text", "required": False, "help_text": "HBase 用户名（无认证可留空）"},
        {"key": "password", "label": "密码", "type": "password", "required": False, "help_text": "HBase 密码（无认证可留空）"},
    ]},
    "apis": [
        {"name": "cluster_status", "display_name": "集群状态", "method": "GET", "path": "/status/cluster",
         "description": "获取 HBase 集群状态（Live/Dead RegionServers 数量）"},
        {"name": "list_tables", "display_name": "表列表", "method": "GET", "path": "/",
         "description": "获取 HBase 中所有表名"},
        {"name": "get_table_schema", "display_name": "表结构", "method": "GET", "path": "/{table}/schema",
         "description": "获取指定表的 Schema（列族定义）"},
        {"name": "scan_table", "display_name": "扫描表数据", "method": "GET", "path": "/{table}/*",
         "description": "扫描表中的数据行，支持范围过滤"},
        {"name": "get_row", "display_name": "获取单行数据", "method": "GET", "path": "/{table}/{row}",
         "description": "根据 RowKey 获取单行数据"},
        {"name": "put_row", "display_name": "写入数据", "method": "PUT", "path": "/{table}/{row}",
         "description": "向表中写入一行数据"},
    ],
}

KAFKA = {
    "name": "Apache Kafka",
        "category": "storage",
    "description": "Apache Kafka 分布式事件流平台。通过 REST Admin API 管理 Topic、查看消费者组状态、"
                   "监控集群健康。是实时数据管道和流处理的核心基础设施。",
    "base_url": "http://your-kafka-rest:8082",
    "auth_type": "basic",
    "credential_template": {"fields": [
        {"key": "username", "label": "用户名", "type": "text", "required": False, "help_text": "Kafka REST 代理用户名（无认证可留空）"},
        {"key": "password", "label": "密码", "type": "password", "required": False, "help_text": "Kafka REST 代理密码（无认证可留空）"},
    ]},
    "apis": [
        {"name": "list_topics", "display_name": "获取 Topic 列表", "method": "GET", "path": "/v3/clusters/{clusterId}/topics",
         "description": "获取 Kafka 集群中所有 Topic 列表"},
        {"name": "get_topic_config", "display_name": "获取 Topic 配置", "method": "GET",
         "path": "/v3/clusters/{clusterId}/topics/{topicName}/configs",
         "description": "获取 Topic 的配置参数（分区数、副本数、保留策略等）"},
        {"name": "list_consumer_groups", "display_name": "消费者组列表", "method": "GET",
         "path": "/v3/clusters/{clusterId}/consumer-groups",
         "description": "获取所有消费者组及其状态"},
        {"name": "get_consumer_group", "display_name": "消费者组详情", "method": "GET",
         "path": "/v3/clusters/{clusterId}/consumer-groups/{consumerGroupId}",
         "description": "获取消费者组的详细信息、消费 Lag"},
        {"name": "get_cluster_info", "display_name": "集群信息", "method": "GET", "path": "/v3/clusters",
         "description": "获取 Kafka 集群 ID、Controller 节点、Broker 数量"},
        {"name": "list_brokers", "display_name": "Broker 列表", "method": "GET", "path": "/v3/clusters/{clusterId}/brokers",
         "description": "获取所有 Broker 节点状态和配置"},
    ],
}

MINIO = {
    "name": "MinIO",
        "category": "storage",
    "description": "MinIO 高性能对象存储。兼容 Amazon S3 API，适用于大数据湖、机器学习数据集、"
                   "备份归档等场景。支持 Bucket 管理、文件上传下载、权限控制。",
    "base_url": "http://your-minio:9000",
    "auth_type": "basic",
    "credential_template": {"fields": [
        {"key": "username", "label": "Access Key", "type": "text", "required": True, "help_text": "MinIO Access Key"},
        {"key": "password", "label": "Secret Key", "type": "password", "required": True, "help_text": "MinIO Secret Key"},
    ]},
    "apis": [
        {"name": "list_buckets", "display_name": "获取 Bucket 列表", "method": "GET", "path": "/",
         "description": "列出所有可用的 Bucket"},
        {"name": "list_objects", "display_name": "列出对象", "method": "GET", "path": "/{bucket}?list-type=2",
         "description": "列出指定 Bucket 中的对象"},
        {"name": "head_object", "display_name": "对象信息", "method": "HEAD", "path": "/{bucket}/{object}",
         "description": "获取对象的元信息（大小、类型、修改时间）"},
        {"name": "server_info", "display_name": "服务信息", "method": "GET", "path": "/minio/health/live",
         "description": "检查 MinIO 服务健康状态"},
    ],
}

# ── 四、资源管理 ──────────────────────────────────────────────────────

YARN = {
    "name": "YARN",
        "category": "resource",
    "description": "Hadoop YARN 资源管理器。通过 ResourceManager REST API 监控集群资源使用情况、"
                   "管理应用程序（查看/终止）、查看节点健康状态和调度队列配置。",
    "base_url": "http://your-rm-host:8088",
    "auth_type": "basic",
    "credential_template": {"fields": [
        {"key": "username", "label": "用户名", "type": "text", "required": False, "help_text": "YARN 用户名（无认证可留空）"},
        {"key": "password", "label": "密码", "type": "password", "required": False, "help_text": "YARN 密码（无认证可留空）"},
    ]},
    "apis": [
        {"name": "cluster_info", "display_name": "集群信息", "method": "GET", "path": "/ws/v1/cluster/info",
         "description": "获取 YARN 集群基本信息：HA 状态、RM 版本、Hadoop 版本"},
        {"name": "cluster_metrics", "display_name": "集群资源指标", "method": "GET", "path": "/ws/v1/cluster/metrics",
         "description": "获取集群资源使用概况：总/已用内存、VCores、节点数、应用数"},
        {"name": "list_nodes", "display_name": "节点列表", "method": "GET", "path": "/ws/v1/cluster/nodes",
         "description": "获取所有 NodeManager 节点状态、资源、健康状况"},
        {"name": "get_node_info", "display_name": "节点详情", "method": "GET", "path": "/ws/v1/cluster/nodes/{nodeId}",
         "description": "获取指定节点的详细资源和运行中容器信息"},
        {"name": "list_apps", "display_name": "应用列表", "method": "GET", "path": "/ws/v1/cluster/apps",
         "description": "获取应用列表，支持按状态、用户、队列筛选"},
        {"name": "get_app_detail", "display_name": "应用详情", "method": "GET", "path": "/ws/v1/cluster/apps/{appId}",
         "description": "获取应用详细信息：状态、资源占用、运行时间、诊断信息"},
        {"name": "kill_app", "display_name": "终止应用", "method": "PUT", "path": "/ws/v1/cluster/apps/{appId}/state",
         "description": "终止指定应用（发送 KILL 命令）"},
        {"name": "scheduler_info", "display_name": "调度器信息", "method": "GET", "path": "/ws/v1/cluster/scheduler",
         "description": "获取调度器配置和队列资源分配情况"},
    ],
}

KUBERNETES = {
    "name": "Kubernetes",
        "category": "resource",
    "description": "Kubernetes 容器编排平台。通过 REST API 管理 Pod、Service、Deployment、ConfigMap 等资源。"
                   "适用于云原生大数据平台（Spark on K8s、Flink on K8s）的运维管理。",
    "base_url": "https://your-k8s-api-server:6443",
    "auth_type": "bearer",
    "credential_template": {"fields": [
        {"key": "token", "label": "ServiceAccount Token", "type": "password", "required": True,
         "help_text": "Kubernetes ServiceAccount Token（kubectl create token 或从 Secret 获取）",
         "help_url": "https://kubernetes.io/docs/concepts/security/service-accounts/"},
    ]},
    "apis": [
        {"name": "cluster_info", "display_name": "集群信息", "method": "GET", "path": "/api/v1",
         "description": "获取 K8s API 版本和可用资源"},
        {"name": "list_namespaces", "display_name": "命名空间列表", "method": "GET", "path": "/api/v1/namespaces",
         "description": "获取所有命名空间"},
        {"name": "list_pods", "display_name": "Pod 列表", "method": "GET", "path": "/api/v1/namespaces/{namespace}/pods",
         "description": "获取指定命名空间下的所有 Pod 及状态"},
        {"name": "get_pod_detail", "display_name": "Pod 详情", "method": "GET",
         "path": "/api/v1/namespaces/{namespace}/pods/{name}",
         "description": "获取 Pod 详细信息：状态、容器、事件、资源请求"},
        {"name": "list_services", "display_name": "Service 列表", "method": "GET",
         "path": "/api/v1/namespaces/{namespace}/services",
         "description": "获取 Service 列表"},
        {"name": "list_deployments", "display_name": "Deployment 列表", "method": "GET",
         "path": "/apis/apps/v1/namespaces/{namespace}/deployments",
         "description": "获取 Deployment 列表和副本状态"},
        {"name": "list_nodes", "display_name": "节点列表", "method": "GET", "path": "/api/v1/nodes",
         "description": "获取集群所有节点状态、资源、标签"},
        {"name": "get_pod_logs", "display_name": "Pod 日志", "method": "GET",
         "path": "/api/v1/namespaces/{namespace}/pods/{name}/log",
         "description": "获取指定 Pod 的容器日志"},
    ],
}

# ── 五、数据集成 ──────────────────────────────────────────────────────

SEATUNNEL = {
    "name": "Apache SeaTunnel",
        "category": "integration",
    "description": "Apache SeaTunnel 分布式数据集成平台。支持 100+ 数据源连接器，提供批量同步和实时 CDC 能力。"
                   "通过 REST API 管理同步任务的创建、执行、监控。",
    "base_url": "http://your-seatunnel:8080",
    "auth_type": "bearer",
    "credential_template": {"fields": [
        {"key": "token", "label": "API Token", "type": "password", "required": True,
         "help_text": "SeaTunnel Zeta Engine 的 API 认证 Token"},
    ]},
    "apis": [
        {"name": "cluster_info", "display_name": "集群信息", "method": "GET", "path": "/hazelcast/rest/cluster",
         "description": "获取 SeaTunnel Zeta 引擎集群状态"},
        {"name": "submit_job", "display_name": "提交任务", "method": "POST", "path": "/hazelcast/rest/submit-job",
         "description": "提交数据同步任务（支持 JSON/Config 格式）"},
        {"name": "list_jobs", "display_name": "任务列表", "method": "GET", "path": "/hazelcast/rest/submit-job",
         "description": "获取所有任务及其运行状态"},
        {"name": "get_job_info", "display_name": "任务详情", "method": "GET", "path": "/hazelrest/rest/job-info/{jobId}",
         "description": "获取指定任务的详细执行信息"},
        {"name": "cancel_job", "display_name": "取消任务", "method": "GET", "path": "/hazelcast/rest/cancel-job",
         "description": "取消正在运行的同步任务"},
    ],
}

NIFI = {
    "name": "Apache NiFi",
        "category": "integration",
    "description": "Apache NiFi 数据流自动化平台。可视化拖拽式数据管道编排，支持实时数据收集、"
                   "路由、转换和分发。通过 REST API 管理 Processor、ProcessGroup 和 FlowFile。",
    "base_url": "http://your-nifi:8080/nifi-api",
    "auth_type": "basic",
    "credential_template": {"fields": [
        {"key": "username", "label": "用户名", "type": "text", "required": True, "help_text": "NiFi 登录用户名"},
        {"key": "password", "label": "密码", "type": "password", "required": True, "help_text": "NiFi 登录密码"},
    ]},
    "apis": [
        {"name": "system_diagnostics", "display_name": "系统诊断", "method": "GET", "path": "/system-diagnostics",
         "description": "获取 NiFi 系统资源使用：内存、CPU、磁盘、线程"},
        {"name": "list_process_groups", "display_name": "流程组列表", "method": "GET",
         "path": "/process-groups/root/process-groups",
         "description": "获取根流程组下的所有子流程组"},
        {"name": "list_processors", "display_name": "处理器列表", "method": "GET",
         "path": "/process-groups/{processGroupId}/processors",
         "description": "获取流程组下的所有 Processor"},
        {"name": "get_processor_status", "display_name": "处理器状态", "method": "GET",
         "path": "/processors/{id}/status",
         "description": "获取处理器运行状态、处理量、错误信息"},
        {"name": "start_processor", "display_name": "启动处理器", "method": "PUT",
         "path": "/processors/{id}",
         "description": "启动指定处理器"},
        {"name": "stop_processor", "display_name": "停止处理器", "method": "PUT",
         "path": "/processors/{id}",
         "description": "停止指定处理器"},
        {"name": "get_flow_status", "display_name": "全局流量状态", "method": "GET",
         "path": "/flow/status",
         "description": "获取全局流量统计：活跃线程数、排队数据量、传输速率"},
    ],
}

DATAX = {
    "name": "DataX",
        "category": "integration",
    "description": "DataX 阿里离线数据同步框架。通过 REST API 管理数据同步任务，支持 MySQL/Oracle/HDFS/Hive/"
                   "Kafka 等 30+ 异构数据源之间的高速数据迁移。",
    "base_url": "http://your-datax-server:9090",
    "auth_type": "basic",
    "credential_template": {"fields": [
        {"key": "username", "label": "用户名", "type": "text", "required": False, "help_text": "DataX 管理端用户名"},
        {"key": "password", "label": "密码", "type": "password", "required": False, "help_text": "DataX 管理端密码"},
    ]},
    "apis": [
        {"name": "list_jobs", "display_name": "任务列表", "method": "GET", "path": "/api/datax/jobs",
         "description": "获取所有同步任务列表"},
        {"name": "submit_job", "display_name": "提交任务", "method": "POST", "path": "/api/datax/job",
         "description": "提交新的数据同步任务"},
        {"name": "get_job_status", "display_name": "任务状态", "method": "GET", "path": "/api/datax/job/{jobId}",
         "description": "获取指定任务的执行状态和统计"},
        {"name": "stop_job", "display_name": "停止任务", "method": "POST", "path": "/api/datax/job/{jobId}/stop",
         "description": "停止正在执行的同步任务"},
    ],
}

# ── 六、数据治理与元数据 ──────────────────────────────────────────────

OPENMETADATA = {
    "name": "OpenMetadata",
        "category": "governance",
    "description": "OpenMetadata 数据治理平台（14k+ Stars）。统一数据目录、血缘追踪、数据质量、"
                   "数据分类。通过 REST API 搜索资产、查看血缘关系、管理数据策略。",
    "base_url": "http://your-openmetadata:8585",
    "auth_type": "bearer",
    "credential_template": {"fields": [
        {"key": "token", "label": "API Token", "type": "password", "required": True,
         "help_text": "在 OpenMetadata Settings > Bots > Create Bot 中生成 Token",
         "help_url": "https://docs.open-metadata.org/latest/sdk/python"},
    ]},
    "apis": [
        {"name": "search_assets", "display_name": "搜索数据资产", "method": "GET", "path": "/api/v1/search/query",
         "description": "搜索表、主题、仪表盘、Pipeline 等数据资产"},
        {"name": "list_databases", "display_name": "数据库列表", "method": "GET", "path": "/api/v1/databases",
         "description": "获取所有已注册的数据库服务"},
        {"name": "list_tables", "display_name": "表列表", "method": "GET", "path": "/api/v1/tables",
         "description": "获取所有表的元数据信息"},
        {"name": "get_table_detail", "display_name": "表详情", "method": "GET", "path": "/api/v1/tables/{id}",
         "description": "获取表的 Schema、描述、标签、Owner、使用统计"},
        {"name": "get_lineage", "display_name": "数据血缘", "method": "GET", "path": "/api/v1/lineage/table/{fqn}",
         "description": "获取表的上下游血缘关系图"},
        {"name": "list_teams", "display_name": "团队列表", "method": "GET", "path": "/api/v1/teams",
         "description": "获取所有团队和成员信息"},
        {"name": "get_data_quality", "display_name": "数据质量", "method": "GET", "path": "/api/v1/dataQuality/testSuites",
         "description": "获取数据质量测试套件和结果"},
    ],
}

DATAHUB = {
    "name": "DataHub",
        "category": "governance",
    "description": "LinkedIn 开源的 DataHub 元数据平台（12k+ Stars）。支持数据发现、血缘追踪、"
                   "数据治理。通过 GraphQL API 查询元数据、标签、所有者、血缘关系。",
    "base_url": "http://your-datahub:8080",
    "auth_type": "bearer",
    "credential_template": {"fields": [
        {"key": "token", "label": "API Token", "type": "password", "required": True,
         "help_text": "在 DataHub Settings > Access Tokens 中生成"},
    ]},
    "apis": [
        {"name": "search_entities", "display_name": "搜索实体", "method": "POST", "path": "/api/graphql",
         "description": "通过 GraphQL 搜索数据集、仪表盘、Pipeline 等实体"},
        {"name": "get_entity_detail", "display_name": "实体详情", "method": "POST", "path": "/api/graphql",
         "description": "获取实体的 Schema、描述、标签、所有者信息"},
        {"name": "get_lineage", "display_name": "数据血缘", "method": "POST", "path": "/api/graphql",
         "description": "获取实体的上下游血缘关系"},
        {"name": "list_datasets", "display_name": "数据集列表", "method": "GET", "path": "/openapi/entities/v1/list/dataset",
         "description": "获取所有数据集列表"},
    ],
}

ATLAS = {
    "name": "Apache Atlas",
        "category": "governance",
    "description": "Apache Atlas 数据治理与元数据管理框架（Hadoop 生态）。支持元数据类型定义、"
                   "血缘追踪、数据分类、策略管理。通过 REST API 查询元数据和血缘关系。",
    "base_url": "http://your-atlas:21000",
    "auth_type": "basic",
    "credential_template": {"fields": [
        {"key": "username", "label": "用户名", "type": "text", "required": True, "help_text": "Atlas 管理员用户名"},
        {"key": "password", "label": "密码", "type": "password", "required": True, "help_text": "Atlas 管理员密码"},
    ]},
    "apis": [
        {"name": "search_entities", "display_name": "搜索实体", "method": "GET", "path": "/api/atlas/v2/search/basic",
         "description": "按关键字搜索 Hive 表、HDFS 路径、Kafka Topic 等元数据实体"},
        {"name": "get_entity", "display_name": "获取实体", "method": "GET", "path": "/api/atlas/v2/entity/guid/{guid}",
         "description": "获取实体的完整元数据信息"},
        {"name": "get_lineage", "display_name": "数据血缘", "method": "GET", "path": "/api/atlas/v2/lineage/{guid}",
         "description": "获取实体的上下游血缘关系"},
        {"name": "list_types", "display_name": "类型列表", "method": "GET", "path": "/api/atlas/v2/types",
         "description": "获取 Atlas 中注册的所有元数据类型"},
        {"name": "create_entity", "display_name": "创建实体", "method": "POST", "path": "/api/atlas/v2/entity",
         "description": "创建新的元数据实体"},
    ],
}

RANGER = {
    "name": "Apache Ranger",
        "category": "governance",
    "description": "Apache Ranger 数据安全框架。提供细粒度的访问控制策略，支持 HDFS/Hive/HBase/Kafka 等组件"
                   "的权限管理。通过 REST API 查看和管理安全策略。",
    "base_url": "http://your-ranger:6080",
    "auth_type": "basic",
    "credential_template": {"fields": [
        {"key": "username", "label": "用户名", "type": "text", "required": True, "help_text": "Ranger 管理员用户名"},
        {"key": "password", "label": "密码", "type": "password", "required": True, "help_text": "Ranger 管理员密码"},
    ]},
    "apis": [
        {"name": "list_policies", "display_name": "策略列表", "method": "GET", "path": "/service/public/v2/api/policy",
         "description": "获取所有安全策略列表"},
        {"name": "get_policy", "display_name": "策略详情", "method": "GET", "path": "/service/public/v2/api/policy/{id}",
         "description": "获取指定策略的详细规则"},
        {"name": "list_services", "display_name": "服务列表", "method": "GET", "path": "/service/public/v2/api/service",
         "description": "获取受保护的服务（HDFS/Hive/HBase 等）"},
        {"name": "audit_events", "display_name": "审计事件", "method": "GET", "path": "/service/public/v2/api/audit",
         "description": "查询访问审计事件"},
    ],
}

# ── 七、BI 与监控 ─────────────────────────────────────────────────────

SUPERSET = {
    "name": "Apache Superset",
        "category": "bi",
    "description": "Apache Superset 数据可视化平台（66k+ Stars）。支持 SQL IDE、丰富的图表类型、"
                   "仪表盘、数据集管理。通过 REST API 管理图表、仪表盘和数据源。",
    "base_url": "http://your-superset:8088",
    "auth_type": "token",
    "credential_template": {"fields": [
        {"key": "token", "label": "API Token", "type": "password", "required": True,
         "help_text": "在 Superset Settings > API Tokens 中生成"},
    ]},
    "apis": [
        {"name": "list_dashboards", "display_name": "仪表盘列表", "method": "GET", "path": "/api/v1/dashboard/",
         "description": "获取所有仪表盘列表"},
        {"name": "get_dashboard", "display_name": "仪表盘详情", "method": "GET", "path": "/api/v1/dashboard/{id}",
         "description": "获取仪表盘中的图表布局和配置"},
        {"name": "list_charts", "display_name": "图表列表", "method": "GET", "path": "/api/v1/chart/",
         "description": "获取所有图表列表及类型"},
        {"name": "list_datasets", "display_name": "数据集列表", "method": "GET", "path": "/api/v1/dataset/",
         "description": "获取所有数据集及其关联的数据库"},
        {"name": "list_databases", "display_name": "数据库连接", "method": "GET", "path": "/api/v1/database/",
         "description": "获取已注册的数据库连接列表"},
        {"name": "execute_sql", "display_name": "执行 SQL", "method": "POST", "path": "/api/v1/sqllab/execute/",
         "description": "在 SQL IDE 中执行查询"},
    ],
}

GRAFANA = {
    "name": "Grafana",
        "category": "bi",
    "description": "Grafana 可观测性平台（68k+ Stars）。支持时序数据监控、日志分析、告警管理。"
                   "通过 REST API 管理仪表盘、数据源、告警规则。是大数据监控的标配工具。",
    "base_url": "http://your-grafana:3000",
    "auth_type": "bearer",
    "credential_template": {"fields": [
        {"key": "token", "label": "API Key", "type": "password", "required": True,
         "help_text": "在 Grafana Configuration > API Keys 中创建"},
    ]},
    "apis": [
        {"name": "health_check", "display_name": "健康检查", "method": "GET", "path": "/api/health",
         "description": "检查 Grafana 服务状态和版本"},
        {"name": "list_dashboards", "display_name": "仪表盘列表", "method": "GET", "path": "/api/search",
         "description": "搜索所有仪表盘"},
        {"name": "get_dashboard", "display_name": "仪表盘详情", "method": "GET", "path": "/api/dashboards/uid/{uid}",
         "description": "获取仪表盘完整配置（面板、变量、数据源）"},
        {"name": "list_datasources", "display_name": "数据源列表", "method": "GET", "path": "/api/datasources",
         "description": "获取所有已配置的数据源"},
        {"name": "list_alerts", "display_name": "告警列表", "method": "GET", "path": "/api/v1/provisioning/alert-rules",
         "description": "获取所有告警规则"},
        {"name": "get_alert_history", "display_name": "告警历史", "method": "GET", "path": "/api/v1/alerts",
         "description": "获取告警历史记录"},
    ],
}

# ── 汇总 ─────────────────────────────────────────────────────────────

ALL_BIGDATA_PRESETS = [
    # 一、数据开发与计算引擎
    DINKY, SPARK, FLINK_NATIVE, TRINO, DORIS, STARROCKS, CLICKHOUSE, HIVE,
    # 二、任务调度与工作流
    DOLPHIN_SCHEDULER, AIRFLOW,
    # 三、数据存储
    HDFS, HBASE, KAFKA, MINIO,
    # 四、资源管理
    YARN, KUBERNETES,
    # 五、数据集成
    SEATUNNEL, NIFI, DATAX,
    # 六、数据治理与元数据
    OPENMETADATA, DATAHUB, ATLAS, RANGER,
    # 七、BI 与监控
    SUPERSET, GRAFANA,
]
