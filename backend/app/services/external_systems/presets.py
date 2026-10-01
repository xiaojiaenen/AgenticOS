"""预设外部系统种子数据与幂等 seed 逻辑。"""

from __future__ import annotations

import json
import logging

from sqlalchemy import select

from app.db.models import ExternalApiModel, ExternalApiParamModel, ExternalSystemModel

logger = logging.getLogger(__name__)


def seed_preset_external_systems() -> None:
    """Seed preset external systems on startup (idempotent).

    每次启动检查并添加缺失的预设，已存在的不会重复添加。
    """
    from app.db.session import create_db_session

    PRESETS = [
        {
            "name": "OpenSpider",
            "description": "OpenSpider 爬虫管理平台 - 爬虫生命周期管理、数据采集、定时调度",
            "category": "devops",
            "base_url": "http://localhost:8000",
            "auth_type": "jwt_login",
            "credential_template": {"fields": [
                {"key": "username", "label": "用户名", "type": "text", "required": True, "help_text": "OpenSpider 账户用户名"},
                {"key": "password", "label": "密码", "type": "password", "required": True, "help_text": "OpenSpider 账户密码"},
            ]},
            "jwt_login_url": "/auth/login/json",
            "jwt_refresh_url": "/auth/refresh",
            "jwt_request_body_template": '{"username": "{username}", "password": "{password}"}',
            "jwt_response_token_path": "access_token",
            "jwt_response_expires_path": "expires_in",
            "jwt_refresh_body_template": '{"refresh_token": "{refresh_token}"}',
            "apis": [
                {"name": "list_spiders", "display_name": "获取爬虫列表", "method": "GET", "path": "/spiders", "description": "列出当前用户可见的爬虫"},
                {"name": "get_spider", "display_name": "获取爬虫详情", "method": "GET", "path": "/spiders/{name}", "description": "获取单个爬虫的详细信息",
                 "params": [{"name": "name", "param_type": "path", "data_type": "string", "required": True, "description": "爬虫名称", "param_source": "llm_extract"}]},
                {"name": "start_spider", "display_name": "启动爬虫", "method": "POST", "path": "/spiders/{spider_id}/start", "description": "启动指定爬虫",
                 "params": [{"name": "spider_id", "param_type": "path", "data_type": "integer", "required": True, "description": "爬虫 ID", "param_source": "llm_extract"}]},
                {"name": "stop_spider", "display_name": "停止爬虫", "method": "POST", "path": "/spiders/{spider_id}/stop", "description": "停止正在运行的爬虫",
                 "params": [{"name": "spider_id", "param_type": "path", "data_type": "integer", "required": True, "description": "爬虫 ID", "param_source": "llm_extract"}]},
                {"name": "pause_spider", "display_name": "暂停爬虫", "method": "POST", "path": "/spiders/{spider_id}/pause", "description": "暂停爬虫，保留断点",
                 "params": [{"name": "spider_id", "param_type": "path", "data_type": "integer", "required": True, "description": "爬虫 ID", "param_source": "llm_extract"}]},
                {"name": "resume_spider", "display_name": "恢复爬虫", "method": "POST", "path": "/spiders/{spider_id}/resume", "description": "从断点恢复爬虫运行",
                 "params": [{"name": "spider_id", "param_type": "path", "data_type": "integer", "required": True, "description": "爬虫 ID", "param_source": "llm_extract"}]},
                {"name": "delete_spider", "display_name": "删除爬虫", "method": "DELETE", "path": "/spiders/{spider_id}", "description": "删除爬虫",
                 "params": [{"name": "spider_id", "param_type": "path", "data_type": "integer", "required": True, "description": "爬虫 ID", "param_source": "llm_extract"}]},
                {"name": "upload_spider", "display_name": "上传爬虫文件", "method": "POST", "path": "/spiders/upload", "description": "上传 .py 爬虫文件，自动注册"},
                {"name": "list_tasks", "display_name": "获取任务列表", "method": "GET", "path": "/tasks", "description": "查询任务列表，支持按爬虫和状态筛选"},
                {"name": "get_task", "display_name": "获取任务详情", "method": "GET", "path": "/tasks/{task_id}", "description": "获取单个任务的详细信息",
                 "params": [{"name": "task_id", "param_type": "path", "data_type": "integer", "required": True, "description": "任务 ID", "param_source": "llm_extract"}]},
                {"name": "get_task_logs", "display_name": "获取任务日志", "method": "GET", "path": "/tasks/{task_id}/logs", "description": "获取指定任务的运行日志",
                 "params": [{"name": "task_id", "param_type": "path", "data_type": "integer", "required": True, "description": "任务 ID", "param_source": "llm_extract"}]},
                {"name": "get_spider_data", "display_name": "查询爬虫数据", "method": "GET", "path": "/spiders/{spider_id}/data", "description": "分页查询爬虫采集的数据",
                 "params": [{"name": "spider_id", "param_type": "path", "data_type": "integer", "required": True, "description": "爬虫 ID", "param_source": "llm_extract"}]},
                {"name": "export_spider_data", "display_name": "导出爬虫数据", "method": "GET", "path": "/spiders/{spider_id}/export", "description": "导出爬虫数据，支持 JSON/JSONL/CSV",
                 "params": [{"name": "spider_id", "param_type": "path", "data_type": "integer", "required": True, "description": "爬虫 ID", "param_source": "llm_extract"}]},
                {"name": "list_schedules", "display_name": "获取调度列表", "method": "GET", "path": "/schedules", "description": "列出所有定时调度"},
                {"name": "create_schedule", "display_name": "创建调度", "method": "POST", "path": "/schedules", "description": "创建新的定时调度任务"},
                {"name": "update_schedule", "display_name": "修改调度", "method": "PUT", "path": "/schedules/{schedule_id}", "description": "修改调度的 cron 表达式和参数",
                 "params": [{"name": "schedule_id", "param_type": "path", "data_type": "integer", "required": True, "description": "调度 ID", "param_source": "llm_extract"}]},
                {"name": "delete_schedule", "display_name": "删除调度", "method": "DELETE", "path": "/schedules/{schedule_id}", "description": "删除定时调度",
                 "params": [{"name": "schedule_id", "param_type": "path", "data_type": "integer", "required": True, "description": "调度 ID", "param_source": "llm_extract"}]},
                {"name": "enable_schedule", "display_name": "启用调度", "method": "POST", "path": "/schedules/{schedule_id}/enable", "description": "启用已禁用的调度",
                 "params": [{"name": "schedule_id", "param_type": "path", "data_type": "integer", "required": True, "description": "调度 ID", "param_source": "llm_extract"}]},
                {"name": "disable_schedule", "display_name": "禁用调度", "method": "POST", "path": "/schedules/{schedule_id}/disable", "description": "禁用调度",
                 "params": [{"name": "schedule_id", "param_type": "path", "data_type": "integer", "required": True, "description": "调度 ID", "param_source": "llm_extract"}]},
            ],
        },
        {
            "name": "Dinky",
            "description": "Dinky 实时计算平台 - 基于 Apache Flink 的数据开发、作业管理、运维监控。"
                           "通过 OpenAPI 提供 Flink 作业全生命周期管理能力。",
            "category": "compute",
            "base_url": "http://your-dinky-host:8888",
            "auth_type": "bearer",
            "credential_template": {"fields": [
                {"key": "token", "label": "API Token", "type": "password", "required": True,
                 "help_text": "在 Dinky 系统管理 → 令牌管理 中创建 API Token",
                 "help_url": "https://dinky.org.cn/docs/next/openapi/openapi_overview"},
            ]},
            "apis": [
                # ── 系统 ──
                {"name": "version", "display_name": "获取版本", "method": "GET", "path": "/openapi/version",
                 "description": "获取 Dinky 服务版本号"},
                # ── 任务提交与管理 ──
                {"name": "submit_task", "display_name": "提交任务", "method": "POST", "path": "/openapi/submitTask",
                 "description": "提交 Flink 任务到集群执行（支持 SQL 和 JAR）",
                 "params": [
                     {"name": "id", "param_type": "body", "data_type": "integer", "required": True, "description": "Dinky 任务 ID", "param_source": "llm_extract"},
                     {"name": "isOnline", "param_type": "body", "data_type": "boolean", "required": False, "description": "是否上线（仅允许一个作业运行）", "param_source": "llm_extract"},
                     {"name": "savePointPath", "param_type": "body", "data_type": "string", "required": False, "description": "SavePoint 路径（从检查点恢复）", "param_source": "llm_extract"},
                     {"name": "variables", "param_type": "body", "data_type": "object", "required": False, "description": "变量键值对", "param_source": "llm_extract"},
                 ]},
                {"name": "restart_task", "display_name": "重启任务", "method": "GET", "path": "/openapi/restartTask",
                 "description": "从指定 SavePoint 路径重启 Flink 任务",
                 "params": [
                     {"name": "id", "param_type": "query", "data_type": "integer", "required": True, "description": "任务 ID", "param_source": "llm_extract"},
                     {"name": "savePointPath", "param_type": "query", "data_type": "string", "required": False, "description": "SavePoint 路径", "param_source": "llm_extract"},
                 ]},
                {"name": "cancel_job", "display_name": "取消 Flink Job", "method": "GET", "path": "/openapi/cancel",
                 "description": "取消正在运行的 Flink 作业",
                 "params": [
                     {"name": "id", "param_type": "query", "data_type": "integer", "required": True, "description": "任务 ID", "param_source": "llm_extract"},
                     {"name": "withSavePoint", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否携带 SavePoint，默认 false", "param_source": "llm_extract"},
                     {"name": "forceCancel", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否强制取消，默认 true", "param_source": "llm_extract"},
                 ]},
                # ── SQL 分析 ──
                {"name": "explain_sql", "display_name": "解释 SQL", "method": "POST", "path": "/openapi/explainSql",
                 "description": "解释 Flink SQL 语句的执行计划，不实际执行",
                 "params": [
                     {"name": "statement", "param_type": "body", "data_type": "string", "required": True, "description": "Flink SQL 语句", "param_source": "llm_extract"},
                     {"name": "clusterName", "param_type": "body", "data_type": "string", "required": False, "description": "集群实例名称", "param_source": "llm_extract"},
                     {"name": "databaseName", "param_type": "body", "data_type": "string", "required": False, "description": "数据库名称", "param_source": "llm_extract"},
                     {"name": "envId", "param_type": "body", "data_type": "integer", "required": False, "description": "环境 ID", "param_source": "llm_extract"},
                     {"name": "fragment", "param_type": "body", "data_type": "boolean", "required": False, "description": "是否为片段模式", "param_source": "llm_extract"},
                     {"name": "variables", "param_type": "body", "data_type": "object", "required": False, "description": "变量键值对", "param_source": "llm_extract"},
                 ]},
                {"name": "get_job_plan", "display_name": "获取执行计划", "method": "POST", "path": "/openapi/getJobPlan",
                 "description": "获取 Flink 作业的执行计划（Job Graph）",
                 "params": [
                     {"name": "statement", "param_type": "body", "data_type": "string", "required": True, "description": "Flink SQL 语句", "param_source": "llm_extract"},
                     {"name": "clusterName", "param_type": "body", "data_type": "string", "required": False, "description": "集群实例名称", "param_source": "llm_extract"},
                     {"name": "parallelism", "param_type": "body", "data_type": "integer", "required": False, "description": "并行度", "param_source": "llm_extract"},
                     {"name": "fragment", "param_type": "body", "data_type": "boolean", "required": False, "description": "是否为片段模式", "param_source": "llm_extract"},
                 ]},
                {"name": "get_stream_graph", "display_name": "获取 Stream Graph", "method": "POST", "path": "/openapi/getStreamGraph",
                 "description": "获取 Flink 作业的 StreamGraph DAG 图",
                 "params": [
                     {"name": "statement", "param_type": "body", "data_type": "string", "required": True, "description": "Flink SQL 语句", "param_source": "llm_extract"},
                     {"name": "clusterName", "param_type": "body", "data_type": "string", "required": False, "description": "集群实例名称", "param_source": "llm_extract"},
                     {"name": "parallelism", "param_type": "body", "data_type": "integer", "required": False, "description": "并行度", "param_source": "llm_extract"},
                     {"name": "fragment", "param_type": "body", "data_type": "boolean", "required": False, "description": "是否为片段模式", "param_source": "llm_extract"},
                 ]},
                {"name": "export_sql", "display_name": "导出 SQL", "method": "GET", "path": "/openapi/exportSql",
                 "description": "导出指定任务的 Flink SQL 语句",
                 "params": [{"name": "id", "param_type": "query", "data_type": "integer", "required": True, "description": "任务 ID", "param_source": "llm_extract"}]},
                # ── SavePoint ──
                {"name": "savepoint", "display_name": "触发 Savepoint", "method": "POST", "path": "/openapi/savepoint",
                 "description": "为运行中的 Flink 作业触发 Savepoint（通过查询参数）",
                 "params": [
                     {"name": "taskId", "param_type": "query", "data_type": "integer", "required": True, "description": "Dinky 任务 ID", "param_source": "llm_extract"},
                     {"name": "savePointType", "param_type": "query", "data_type": "string", "required": True, "description": "SavePoint 类型：TRIGGER/STOP/CANCEL", "param_source": "llm_extract"},
                 ]},
                {"name": "savepoint_task", "display_name": "任务级 Savepoint", "method": "POST", "path": "/openapi/savepointTask",
                 "description": "以任务维度触发 Savepoint（通过请求体）",
                 "params": [
                     {"name": "taskId", "param_type": "body", "data_type": "integer", "required": True, "description": "Dinky 任务 ID", "param_source": "llm_extract"},
                     {"name": "type", "param_type": "body", "data_type": "string", "required": False, "description": "SavePoint 类型：trigger/stop/cancel，默认 trigger", "param_source": "llm_extract"},
                 ]},
                # ── 作业实例 ──
                {"name": "get_job_instance", "display_name": "获取作业实例", "method": "GET", "path": "/openapi/getJobInstance",
                 "description": "根据 Job Instance ID 获取作业实例详情",
                 "params": [{"name": "id", "param_type": "query", "data_type": "integer", "required": True, "description": "Job Instance ID", "param_source": "llm_extract"}]},
                {"name": "get_job_instance_by_task_id", "display_name": "按任务查实例", "method": "GET", "path": "/openapi/getJobInstanceByTaskId",
                 "description": "根据任务 ID 获取作业实例详情",
                 "params": [{"name": "id", "param_type": "query", "data_type": "integer", "required": True, "description": "Dinky 任务 ID", "param_source": "llm_extract"}]},
                {"name": "get_job_instance_list", "display_name": "作业实例列表", "method": "POST", "path": "/openapi/getJobInstanceList",
                 "description": "分页查询作业实例列表（ProTable 格式）",
                 "params": [
                     {"name": "pageSize", "param_type": "body", "data_type": "integer", "required": False, "description": "每页大小", "param_source": "llm_extract"},
                     {"name": "current", "param_type": "body", "data_type": "integer", "required": False, "description": "当前页码", "param_source": "llm_extract"},
                 ]},
                # ── 血缘 ──
                {"name": "get_task_lineage", "display_name": "获取任务血缘", "method": "GET", "path": "/openapi/getTaskLineage",
                 "description": "获取指定任务的数据血缘关系",
                 "params": [{"name": "id", "param_type": "query", "data_type": "integer", "required": True, "description": "任务 ID", "param_source": "llm_extract"}]},
                # ── 日志与运维 ──
                {"name": "get_job_manager_log", "display_name": "JobManager 日志", "method": "GET", "path": "/api/jobInstance/getJobManagerLog",
                 "description": "获取 JobManager 的运行日志，用于排查作业启动失败、资源申请异常等问题",
                 "params": [{"name": "address", "param_type": "query", "data_type": "string", "required": True, "description": "JobManager 地址（如 10.0.0.1:8081）", "param_source": "llm_extract"}]},
                {"name": "get_job_manager_stdout", "display_name": "JobManager StdOut", "method": "GET", "path": "/api/jobInstance/getJobManagerStdOut",
                 "description": "获取 JobManager 的标准输出，用于查看启动日志和系统输出",
                 "params": [{"name": "address", "param_type": "query", "data_type": "string", "required": True, "description": "JobManager 地址", "param_source": "llm_extract"}]},
                {"name": "get_job_manager_thread_dump", "display_name": "JM 线程 Dump", "method": "GET", "path": "/api/jobInstance/getJobManagerThreadDump",
                 "description": "获取 JobManager 线程快照，用于排查死锁、阻塞等问题",
                 "params": [{"name": "address", "param_type": "query", "data_type": "string", "required": True, "description": "JobManager 地址", "param_source": "llm_extract"}]},
                {"name": "get_task_manager_list", "display_name": "TaskManager 列表", "method": "GET", "path": "/api/jobInstance/getTaskManagerList",
                 "description": "获取所有 TaskManager 节点列表",
                 "params": [{"name": "address", "param_type": "query", "data_type": "string", "required": True, "description": "JobManager 地址", "param_source": "llm_extract"}]},
                {"name": "get_task_manager_log", "display_name": "TaskManager 日志", "method": "GET", "path": "/api/jobInstance/getTaskManagerLog",
                 "description": "获取指定 TaskManager 的运行日志，用于排查算子异常、OOM 等问题",
                 "params": [
                     {"name": "address", "param_type": "query", "data_type": "string", "required": True, "description": "JobManager 地址", "param_source": "llm_extract"},
                     {"name": "containerId", "param_type": "query", "data_type": "string", "required": True, "description": "TaskManager 容器 ID", "param_source": "llm_extract"},
                 ]},
                {"name": "get_job_metrics", "display_name": "作业指标", "method": "GET", "path": "/api/jobInstance/getJobMetricsItems",
                 "description": "获取 Flink 作业的运行指标（吞吐量、延迟、背压等）",
                 "params": [
                     {"name": "address", "param_type": "query", "data_type": "string", "required": True, "description": "JobManager 地址", "param_source": "llm_extract"},
                     {"name": "jobId", "param_type": "query", "data_type": "string", "required": True, "description": "Flink Job ID", "param_source": "llm_extract"},
                     {"name": "verticeId", "param_type": "query", "data_type": "string", "required": True, "description": "算子顶点 ID", "param_source": "llm_extract"},
                 ]},
            ],
        },
        {
            "name": "DolphinScheduler",
            "category": "scheduler",
            "description": "Apache DolphinScheduler 分布式工作流调度平台。支持可视化 DAG 编排、30+ 任务类型、定时调度、运维监控。",
            "base_url": "http://your-ds-host:12345/dolphinscheduler",
            "auth_type": "api_key",
            "credential_template": {"fields": [
                {"key": "key", "label": "Token", "type": "password", "required": True,
                 "help_text": "在 DolphinScheduler 安全中心 → 令牌管理 中创建 API Token",
                 "help_url": "https://dolphinscheduler.apache.org/zh-cn/docs/latest/user_guide/token"},
                {"key": "header_name", "label": "Header 名称", "type": "text", "required": False, "placeholder": "token"},
            ]},
            "apis": [
                # ── 项目 ──
                {"name": "queryAllProjectList", "display_name": "获取项目列表", "method": "GET", "path": "/v2/projects/list",
                 "description": "获取所有项目列表"},
                {"name": "createProject", "display_name": "创建项目", "method": "POST", "path": "/v2/projects",
                 "description": "创建新项目",
                 "params": [
                     {"name": "projectName", "param_type": "body", "data_type": "string", "required": True, "description": "项目名称", "param_source": "llm_extract"},
                     {"name": "description", "param_type": "body", "data_type": "string", "required": False, "description": "项目描述", "param_source": "llm_extract"},
                 ]},
                {"name": "queryProjectByCode", "display_name": "获取项目详情", "method": "GET", "path": "/v2/projects/{code}",
                 "description": "根据项目 Code 获取项目详情",
                 "params": [{"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "项目 Code", "param_source": "llm_extract"}]},
                {"name": "updateProject", "display_name": "更新项目", "method": "PUT", "path": "/v2/projects/{code}",
                 "description": "更新项目信息",
                 "params": [
                     {"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "项目 Code", "param_source": "llm_extract"},
                     {"name": "projectName", "param_type": "body", "data_type": "string", "required": True, "description": "项目名称", "param_source": "llm_extract"},
                     {"name": "description", "param_type": "body", "data_type": "string", "required": False, "description": "项目描述", "param_source": "llm_extract"},
                 ]},
                {"name": "deleteProject", "display_name": "删除项目", "method": "DELETE", "path": "/v2/projects/{code}",
                 "description": "删除指定项目",
                 "params": [{"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "项目 Code", "param_source": "llm_extract"}]},
                # ── 工作流 ──
                {"name": "filterWorkflows", "display_name": "搜索工作流", "method": "POST", "path": "/v2/workflows/query",
                 "description": "按条件搜索/过滤工作流定义",
                 "params": [
                     {"name": "pageSize", "param_type": "body", "data_type": "integer", "required": True, "description": "每页大小", "param_source": "llm_extract"},
                     {"name": "pageNo", "param_type": "body", "data_type": "integer", "required": True, "description": "页码", "param_source": "llm_extract"},
                     {"name": "projectName", "param_type": "body", "data_type": "string", "required": False, "description": "项目名称", "param_source": "llm_extract"},
                     {"name": "workflowName", "param_type": "body", "data_type": "string", "required": False, "description": "工作流名称", "param_source": "llm_extract"},
                     {"name": "releaseState", "param_type": "body", "data_type": "string", "required": False, "description": "上线状态：ONLINE/OFFLINE", "param_source": "llm_extract"},
                 ]},
                {"name": "createWorkflow", "display_name": "创建工作流", "method": "POST", "path": "/v2/workflows",
                 "description": "创建新的工作流定义",
                 "params": [
                     {"name": "name", "param_type": "body", "data_type": "string", "required": True, "description": "工作流名称", "param_source": "llm_extract"},
                     {"name": "projectCode", "param_type": "body", "data_type": "integer", "required": True, "description": "项目 Code", "param_source": "llm_extract"},
                     {"name": "description", "param_type": "body", "data_type": "string", "required": False, "description": "描述", "param_source": "llm_extract"},
                     {"name": "releaseState", "param_type": "body", "data_type": "string", "required": False, "description": "上线状态：ONLINE/OFFLINE，默认 OFFLINE", "param_source": "llm_extract"},
                     {"name": "executionType", "param_type": "body", "data_type": "string", "required": False, "description": "执行类型：PARALLEL/SERIAL_WAIT/SERIAL_DISCARD/SERIAL_PRIORITY", "param_source": "llm_extract"},
                     {"name": "timeout", "param_type": "body", "data_type": "integer", "required": False, "description": "超时时间（秒）", "param_source": "llm_extract"},
                 ]},
                {"name": "getWorkflow", "display_name": "获取工作流详情", "method": "GET", "path": "/v2/workflows/{code}",
                 "description": "获取工作流定义详情（含任务节点）",
                 "params": [{"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "工作流 Code", "param_source": "llm_extract"}]},
                {"name": "updateWorkflow", "display_name": "更新工作流", "method": "PUT", "path": "/v2/workflows/{code}",
                 "description": "更新工作流定义",
                 "params": [
                     {"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "工作流 Code", "param_source": "llm_extract"},
                     {"name": "name", "param_type": "body", "data_type": "string", "required": False, "description": "工作流名称", "param_source": "llm_extract"},
                     {"name": "description", "param_type": "body", "data_type": "string", "required": False, "description": "描述", "param_source": "llm_extract"},
                     {"name": "releaseState", "param_type": "body", "data_type": "string", "required": False, "description": "上线状态：ONLINE/OFFLINE", "param_source": "llm_extract"},
                     {"name": "executionType", "param_type": "body", "data_type": "string", "required": False, "description": "执行类型：PARALLEL/SERIAL_WAIT/SERIAL_DISCARD/SERIAL_PRIORITY", "param_source": "llm_extract"},
                     {"name": "timeout", "param_type": "body", "data_type": "integer", "required": False, "description": "超时时间（秒）", "param_source": "llm_extract"},
                 ]},
                {"name": "deleteWorkflow", "display_name": "删除工作流", "method": "DELETE", "path": "/v2/workflows/{code}",
                 "description": "删除工作流定义",
                 "params": [{"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "工作流 Code", "param_source": "llm_extract"}]},
                # ── 流程实例 ──
                {"name": "queryWorkflowInstanceListPaging", "display_name": "查询流程实例", "method": "GET", "path": "/v2/workflow-instances",
                 "description": "分页查询工作流执行实例列表",
                 "params": [
                     {"name": "searchVal", "param_type": "query", "data_type": "string", "required": False, "description": "搜索关键字", "param_source": "llm_extract"},
                     {"name": "pageNo", "param_type": "query", "data_type": "integer", "required": False, "description": "页码，默认 1", "param_source": "llm_extract"},
                     {"name": "pageSize", "param_type": "query", "data_type": "integer", "required": False, "description": "每页大小，默认 10", "param_source": "llm_extract"},
                     {"name": "stateType", "param_type": "query", "data_type": "string", "required": False, "description": "状态类型：SUCCESS/FAILURE/STOP/KILL 等", "param_source": "llm_extract"},
                     {"name": "startDate", "param_type": "query", "data_type": "string", "required": False, "description": "开始日期（yyyy-MM-dd HH:mm:ss）", "param_source": "llm_extract"},
                     {"name": "endDate", "param_type": "query", "data_type": "string", "required": False, "description": "结束日期（yyyy-MM-dd HH:mm:ss）", "param_source": "llm_extract"},
                 ]},
                {"name": "queryWorkflowInstanceById", "display_name": "获取实例详情", "method": "GET", "path": "/v2/workflow-instances/{workflowInstanceId}",
                 "description": "获取工作流实例的详细信息",
                 "params": [{"name": "workflowInstanceId", "param_type": "path", "data_type": "integer", "required": True, "description": "流程实例 ID", "param_source": "llm_extract"}]},
                {"name": "execute", "display_name": "执行操作", "method": "POST", "path": "/v2/workflow-instances/{workflowInstanceId}/execute/{executeType}",
                 "description": "对流程实例执行操作",
                 "params": [
                     {"name": "workflowInstanceId", "param_type": "path", "data_type": "integer", "required": True, "description": "流程实例 ID", "param_source": "llm_extract"},
                     {"name": "executeType", "param_type": "path", "data_type": "string", "required": True, "description": "执行类型：NONE/REPEAT_RUNNING/RECOVER_SUSPENDED_PROCESS/START_FAILURE_TASK_PROCESS/STOP/PAUSE/EXECUTE_TASK", "param_source": "llm_extract"},
                 ]},
                {"name": "deleteWorkflowInstance", "display_name": "删除实例", "method": "DELETE", "path": "/v2/workflow-instances/{workflowInstanceId}",
                 "description": "删除工作流执行实例",
                 "params": [{"name": "workflowInstanceId", "param_type": "path", "data_type": "integer", "required": True, "description": "流程实例 ID", "param_source": "llm_extract"}]},
                # ── 任务定义 ──
                {"name": "filterTaskDefinition", "display_name": "搜索任务定义", "method": "POST", "path": "/v2/tasks/query",
                 "description": "按条件搜索/过滤任务定义",
                 "params": [
                     {"name": "pageSize", "param_type": "body", "data_type": "integer", "required": True, "description": "每页大小", "param_source": "llm_extract"},
                     {"name": "pageNo", "param_type": "body", "data_type": "integer", "required": True, "description": "页码", "param_source": "llm_extract"},
                     {"name": "projectName", "param_type": "body", "data_type": "string", "required": False, "description": "项目名称", "param_source": "llm_extract"},
                     {"name": "name", "param_type": "body", "data_type": "string", "required": False, "description": "任务名称", "param_source": "llm_extract"},
                     {"name": "taskType", "param_type": "body", "data_type": "string", "required": False, "description": "任务类型：SHELL/SQL/SPARK/FLINK 等", "param_source": "llm_extract"},
                 ]},
                {"name": "createTaskDefinition", "display_name": "创建任务", "method": "POST", "path": "/v2/tasks",
                 "description": "创建新的任务定义",
                 "params": [
                     {"name": "workflowCode", "param_type": "body", "data_type": "integer", "required": True, "description": "所属工作流 Code", "param_source": "llm_extract"},
                     {"name": "name", "param_type": "body", "data_type": "string", "required": True, "description": "任务名称", "param_source": "llm_extract"},
                     {"name": "description", "param_type": "body", "data_type": "string", "required": True, "description": "任务描述", "param_source": "llm_extract"},
                     {"name": "taskType", "param_type": "body", "data_type": "string", "required": True, "description": "任务类型：SHELL/SQL/SPARK/FLINK 等", "param_source": "llm_extract"},
                     {"name": "taskParams", "param_type": "body", "data_type": "string", "required": True, "description": "任务参数（JSON 字符串）", "param_source": "llm_extract"},
                     {"name": "flag", "param_type": "body", "data_type": "string", "required": False, "description": "是否启用：YES/NO，默认 YES", "param_source": "llm_extract"},
                     {"name": "taskPriority", "param_type": "body", "data_type": "string", "required": False, "description": "优先级：HIGHEST/HIGH/MEDIUM/LOW/LOWEST", "param_source": "llm_extract"},
                     {"name": "workerGroup", "param_type": "body", "data_type": "string", "required": False, "description": "Worker 组，默认 default", "param_source": "llm_extract"},
                     {"name": "failRetryTimes", "param_type": "body", "data_type": "integer", "required": False, "description": "失败重试次数，默认 0", "param_source": "llm_extract"},
                     {"name": "failRetryInterval", "param_type": "body", "data_type": "integer", "required": False, "description": "重试间隔（分钟）", "param_source": "llm_extract"},
                     {"name": "timeout", "param_type": "body", "data_type": "integer", "required": False, "description": "超时时间（秒）", "param_source": "llm_extract"},
                     {"name": "upstreamTasksCodes", "param_type": "body", "data_type": "string", "required": False, "description": "上游任务 Code（逗号分隔）", "param_source": "llm_extract"},
                 ]},
                {"name": "getTaskDefinition", "display_name": "获取任务详情", "method": "GET", "path": "/v2/tasks/{code}",
                 "description": "获取任务定义详情",
                 "params": [{"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "任务 Code", "param_source": "llm_extract"}]},
                {"name": "updateTaskDefinition", "display_name": "更新任务", "method": "PUT", "path": "/v2/tasks/{code}",
                 "description": "更新任务定义",
                 "params": [
                     {"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "任务 Code", "param_source": "llm_extract"},
                     {"name": "workflowCode", "param_type": "body", "data_type": "integer", "required": True, "description": "所属工作流 Code", "param_source": "llm_extract"},
                     {"name": "name", "param_type": "body", "data_type": "string", "required": False, "description": "任务名称", "param_source": "llm_extract"},
                     {"name": "description", "param_type": "body", "data_type": "string", "required": False, "description": "任务描述", "param_source": "llm_extract"},
                     {"name": "taskType", "param_type": "body", "data_type": "string", "required": False, "description": "任务类型", "param_source": "llm_extract"},
                     {"name": "taskParams", "param_type": "body", "data_type": "string", "required": False, "description": "任务参数（JSON 字符串）", "param_source": "llm_extract"},
                     {"name": "flag", "param_type": "body", "data_type": "string", "required": False, "description": "是否启用：YES/NO", "param_source": "llm_extract"},
                     {"name": "taskPriority", "param_type": "body", "data_type": "string", "required": False, "description": "优先级", "param_source": "llm_extract"},
                     {"name": "workerGroup", "param_type": "body", "data_type": "string", "required": False, "description": "Worker 组", "param_source": "llm_extract"},
                     {"name": "failRetryTimes", "param_type": "body", "data_type": "integer", "required": False, "description": "失败重试次数", "param_source": "llm_extract"},
                     {"name": "timeout", "param_type": "body", "data_type": "integer", "required": False, "description": "超时时间（秒）", "param_source": "llm_extract"},
                     {"name": "upstreamTasksCodes", "param_type": "body", "data_type": "string", "required": False, "description": "上游任务 Code（逗号分隔）", "param_source": "llm_extract"},
                 ]},
                {"name": "deleteTaskDefinition", "display_name": "删除任务", "method": "DELETE", "path": "/v2/tasks/{code}",
                 "description": "删除任务定义",
                 "params": [{"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "任务 Code", "param_source": "llm_extract"}]},
                # ── 任务实例 ──
                {"name": "queryTaskListPaging", "display_name": "查询任务实例", "method": "GET", "path": "/v2/projects/{projectCode}/task-instances",
                 "description": "分页查询任务执行实例列表",
                 "params": [
                     {"name": "projectCode", "param_type": "path", "data_type": "integer", "required": True, "description": "项目 Code", "param_source": "llm_extract"},
                     {"name": "searchVal", "param_type": "query", "data_type": "string", "required": False, "description": "搜索关键字", "param_source": "llm_extract"},
                     {"name": "pageNo", "param_type": "query", "data_type": "integer", "required": False, "description": "页码，默认 1", "param_source": "llm_extract"},
                     {"name": "pageSize", "param_type": "query", "data_type": "integer", "required": False, "description": "每页大小，默认 10", "param_source": "llm_extract"},
                     {"name": "stateType", "param_type": "query", "data_type": "string", "required": False, "description": "状态类型：SUCCESS/FAILURE/STOP 等", "param_source": "llm_extract"},
                     {"name": "taskName", "param_type": "query", "data_type": "string", "required": False, "description": "任务实例名", "param_source": "llm_extract"},
                     {"name": "startDate", "param_type": "query", "data_type": "string", "required": False, "description": "开始日期", "param_source": "llm_extract"},
                     {"name": "endDate", "param_type": "query", "data_type": "string", "required": False, "description": "结束日期", "param_source": "llm_extract"},
                 ]},
                {"name": "queryTaskInstanceByCode", "display_name": "获取任务实例详情", "method": "POST", "path": "/v2/projects/{projectCode}/task-instances/{taskInstanceId}",
                 "description": "获取任务实例的详细信息",
                 "params": [
                     {"name": "projectCode", "param_type": "path", "data_type": "integer", "required": True, "description": "项目 Code", "param_source": "llm_extract"},
                     {"name": "taskInstanceId", "param_type": "path", "data_type": "integer", "required": True, "description": "任务实例 ID", "param_source": "llm_extract"},
                 ]},
                {"name": "stopTask", "display_name": "停止任务实例", "method": "POST", "path": "/v2/projects/{projectCode}/task-instances/{id}/stop",
                 "description": "停止正在运行的任务实例",
                 "params": [
                     {"name": "projectCode", "param_type": "path", "data_type": "integer", "required": True, "description": "项目 Code", "param_source": "llm_extract"},
                     {"name": "id", "param_type": "path", "data_type": "integer", "required": True, "description": "任务实例 ID", "param_source": "llm_extract"},
                 ]},
                {"name": "taskSavePoint", "display_name": "任务 Savepoint", "method": "POST", "path": "/v2/projects/{projectCode}/task-instances/{id}/savepoint",
                 "description": "为任务实例触发 Savepoint",
                 "params": [
                     {"name": "projectCode", "param_type": "path", "data_type": "integer", "required": True, "description": "项目 Code", "param_source": "llm_extract"},
                     {"name": "id", "param_type": "path", "data_type": "integer", "required": True, "description": "任务实例 ID", "param_source": "llm_extract"},
                 ]},
                {"name": "forceTaskSuccess", "display_name": "强制成功", "method": "POST", "path": "/v2/projects/{projectCode}/task-instances/{id}/force-success",
                 "description": "强制将任务实例标记为成功",
                 "params": [
                     {"name": "projectCode", "param_type": "path", "data_type": "integer", "required": True, "description": "项目 Code", "param_source": "llm_extract"},
                     {"name": "id", "param_type": "path", "data_type": "integer", "required": True, "description": "任务实例 ID", "param_source": "llm_extract"},
                 ]},
                # ── 调度 ──
                {"name": "filterSchedule", "display_name": "搜索定时调度", "method": "POST", "path": "/v2/schedules/filter",
                 "description": "按条件搜索定时调度配置",
                 "params": [
                     {"name": "pageSize", "param_type": "body", "data_type": "integer", "required": True, "description": "每页大小", "param_source": "llm_extract"},
                     {"name": "pageNo", "param_type": "body", "data_type": "integer", "required": True, "description": "页码", "param_source": "llm_extract"},
                     {"name": "projectName", "param_type": "body", "data_type": "string", "required": False, "description": "项目名称", "param_source": "llm_extract"},
                     {"name": "processDefinitionName", "param_type": "body", "data_type": "string", "required": False, "description": "工作流名称", "param_source": "llm_extract"},
                     {"name": "releaseState", "param_type": "body", "data_type": "string", "required": False, "description": "上线状态：ONLINE/OFFLINE", "param_source": "llm_extract"},
                 ]},
                {"name": "createSchedule", "display_name": "创建调度", "method": "POST", "path": "/v2/schedules",
                 "description": "为工作流创建定时调度",
                 "params": [
                     {"name": "processDefinitionCode", "param_type": "body", "data_type": "integer", "required": True, "description": "工作流 Code", "param_source": "llm_extract"},
                     {"name": "crontab", "param_type": "body", "data_type": "string", "required": True, "description": "Cron 表达式（如 0 0 * * * ?）", "param_source": "llm_extract"},
                     {"name": "startTime", "param_type": "body", "data_type": "string", "required": True, "description": "生效开始时间（yyyy-MM-dd HH:mm:ss）", "param_source": "llm_extract"},
                     {"name": "endTime", "param_type": "body", "data_type": "string", "required": True, "description": "生效结束时间（yyyy-MM-dd HH:mm:ss）", "param_source": "llm_extract"},
                     {"name": "timezoneId", "param_type": "body", "data_type": "string", "required": True, "description": "时区（如 Asia/Shanghai）", "param_source": "llm_extract"},
                     {"name": "failureStrategy", "param_type": "body", "data_type": "string", "required": False, "description": "失败策略：CONTINUE/END，默认 CONTINUE", "param_source": "llm_extract"},
                     {"name": "releaseState", "param_type": "body", "data_type": "string", "required": False, "description": "上线状态：ONLINE/OFFLINE，默认 OFFLINE", "param_source": "llm_extract"},
                     {"name": "warningType", "param_type": "body", "data_type": "string", "required": False, "description": "告警类型：NONE/SUCCESS/FAILURE/ALL", "param_source": "llm_extract"},
                     {"name": "processInstancePriority", "param_type": "body", "data_type": "string", "required": False, "description": "优先级：HIGHEST/HIGH/MEDIUM/LOW/LOWEST", "param_source": "llm_extract"},
                     {"name": "workerGroup", "param_type": "body", "data_type": "string", "required": False, "description": "Worker 组", "param_source": "llm_extract"},
                     {"name": "tenantCode", "param_type": "body", "data_type": "string", "required": False, "description": "租户编码", "param_source": "llm_extract"},
                 ]},
                {"name": "getSchedule", "display_name": "获取调度详情", "method": "GET", "path": "/v2/schedules/{id}",
                 "description": "获取定时调度的详细配置",
                 "params": [{"name": "id", "param_type": "path", "data_type": "integer", "required": True, "description": "调度 ID", "param_source": "llm_extract"}]},
                {"name": "updateSchedule", "display_name": "更新调度", "method": "PUT", "path": "/v2/schedules/{id}",
                 "description": "更新定时调度配置",
                 "params": [
                     {"name": "id", "param_type": "path", "data_type": "integer", "required": True, "description": "调度 ID", "param_source": "llm_extract"},
                     {"name": "crontab", "param_type": "body", "data_type": "string", "required": True, "description": "Cron 表达式", "param_source": "llm_extract"},
                     {"name": "startTime", "param_type": "body", "data_type": "string", "required": True, "description": "生效开始时间", "param_source": "llm_extract"},
                     {"name": "endTime", "param_type": "body", "data_type": "string", "required": True, "description": "生效结束时间", "param_source": "llm_extract"},
                     {"name": "timezoneId", "param_type": "body", "data_type": "string", "required": True, "description": "时区", "param_source": "llm_extract"},
                     {"name": "failureStrategy", "param_type": "body", "data_type": "string", "required": False, "description": "失败策略：CONTINUE/END", "param_source": "llm_extract"},
                     {"name": "releaseState", "param_type": "body", "data_type": "string", "required": False, "description": "上线状态：ONLINE/OFFLINE", "param_source": "llm_extract"},
                     {"name": "warningType", "param_type": "body", "data_type": "string", "required": False, "description": "告警类型：NONE/SUCCESS/FAILURE/ALL", "param_source": "llm_extract"},
                     {"name": "processInstancePriority", "param_type": "body", "data_type": "string", "required": False, "description": "优先级", "param_source": "llm_extract"},
                     {"name": "workerGroup", "param_type": "body", "data_type": "string", "required": False, "description": "Worker 组", "param_source": "llm_extract"},
                 ]},
                {"name": "deleteSchedule", "display_name": "删除调度", "method": "DELETE", "path": "/v2/schedules/{id}",
                 "description": "删除定时调度",
                 "params": [{"name": "id", "param_type": "path", "data_type": "integer", "required": True, "description": "调度 ID", "param_source": "llm_extract"}]},
                # ── 队列 ──
                {"name": "queryList", "display_name": "获取队列列表", "method": "GET", "path": "/v2/queues/list",
                 "description": "获取所有队列列表"},
                # ── 任务关系 ──
                {"name": "createTaskRelation", "display_name": "创建任务关系", "method": "POST", "path": "/v2/relations",
                 "description": "创建工作流中的任务依赖关系",
                 "params": [
                     {"name": "workflowCode", "param_type": "body", "data_type": "integer", "required": True, "description": "工作流 Code", "param_source": "llm_extract"},
                     {"name": "preTaskCode", "param_type": "body", "data_type": "integer", "required": True, "description": "上游任务 Code", "param_source": "llm_extract"},
                     {"name": "postTaskCode", "param_type": "body", "data_type": "integer", "required": True, "description": "下游任务 Code", "param_source": "llm_extract"},
                     {"name": "projectCode", "param_type": "body", "data_type": "integer", "required": False, "description": "项目 Code", "param_source": "llm_extract"},
                 ]},
                {"name": "updateUpstreamTaskDefinition", "display_name": "更新上游依赖", "method": "PUT", "path": "/v2/relations/{code}",
                 "description": "更新任务的上游依赖关系",
                 "params": [
                     {"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "下游任务 Code", "param_source": "llm_extract"},
                     {"name": "pageSize", "param_type": "body", "data_type": "integer", "required": True, "description": "每页大小", "param_source": "llm_extract"},
                     {"name": "pageNo", "param_type": "body", "data_type": "integer", "required": True, "description": "页码", "param_source": "llm_extract"},
                     {"name": "workflowCode", "param_type": "body", "data_type": "integer", "required": False, "description": "工作流 Code", "param_source": "llm_extract"},
                     {"name": "upstreams", "param_type": "body", "data_type": "string", "required": True, "description": "上游任务 Code 列表（逗号分隔）", "param_source": "llm_extract"},
                 ]},
                {"name": "deleteTaskRelation", "display_name": "删除任务关系", "method": "DELETE", "path": "/v2/relations/{code-pair}",
                 "description": "删除任务间的依赖关系",
                 "params": [{"name": "code-pair", "param_type": "path", "data_type": "string", "required": True, "description": "任务关系 Code 对", "param_source": "llm_extract"}]},
                # ── 统计 ──
                {"name": "queryWorkflowStatesCounts", "display_name": "工作流状态统计", "method": "GET", "path": "/v2/statistics/workflows/states/count",
                 "description": "查询所有工作流的状态统计"},
            ],
        },
        {
            "name": "Apache Doris FE",
            "category": "compute",
            "description": "Apache Doris Frontend HTTP API。提供集群管理、SQL 执行、查询分析、节点运维等能力。默认端口 8030。",
            "base_url": "http://your-fe-host:8030",
            "auth_type": "basic",
            "credential_template": {"fields": [
                {"key": "username", "label": "用户名", "type": "text", "required": True, "help_text": "Doris FE 用户名（需在 fe.conf 中启用 enable_all_http_auth=true）"},
                {"key": "password", "label": "密码", "type": "password", "required": True, "help_text": "Doris FE 密码"},
            ]},
            "apis": [
                # ── 集群概览 ──
                {"name": "health", "display_name": "健康检查", "method": "GET", "path": "/api/health",
                 "description": "检查 FE 健康状态，返回在线 BE 节点数"},
                {"name": "cluster_overview", "display_name": "集群概览", "method": "GET", "path": "/rest/v2/api/cluster_overview",
                 "description": "获取集群统计：数据库数、表数、BE 数、磁盘使用等"},
                {"name": "cluster_conn_info", "display_name": "连接信息", "method": "GET", "path": "/rest/v2/manager/cluster/cluster_info/conn_info",
                 "description": "获取集群 HTTP 和 MySQL 连接地址"},
                {"name": "fe_version", "display_name": "FE 版本", "method": "GET", "path": "/api/fe_version_info",
                 "description": "获取 FE 版本信息（构建版本、Git 哈希、构建时间）"},
                # ── 节点管理 ──
                {"name": "list_backends", "display_name": "BE 节点列表", "method": "GET", "path": "/api/backends",
                 "description": "获取所有 Backend 节点列表（IP、端口、状态）",
                 "params": [{"name": "is_alive", "param_type": "query", "data_type": "boolean", "required": False, "description": "true 仅返回存活节点，默认 false 返回全部", "param_source": "llm_extract"}]},
                {"name": "list_frontends", "display_name": "FE 节点列表", "method": "GET", "path": "/rest/v2/manager/node/frontends",
                 "description": "获取所有 Frontend 节点列表"},
                {"name": "list_brokers", "display_name": "Broker 列表", "method": "GET", "path": "/rest/v2/manager/node/brokers",
                 "description": "获取所有 Broker 节点列表"},
                {"name": "node_list", "display_name": "节点总览", "method": "GET", "path": "/rest/v2/manager/node/node_list",
                 "description": "获取集群所有节点列表"},
                {"name": "operate_be", "display_name": "操作 BE 节点", "method": "POST", "path": "/rest/v2/manager/node/{action}/be",
                 "description": "添加/删除/下线 BE 节点（action: ADD/DROP/DECOMMISSION）",
                 "params": [{"name": "action", "param_type": "path", "data_type": "string", "required": True, "description": "操作类型：ADD/DROP/DECOMMISSION", "param_source": "llm_extract"}]},
                {"name": "operate_fe", "display_name": "操作 FE 节点", "method": "POST", "path": "/rest/v2/manager/node/{action}/fe",
                 "description": "添加/删除 FE 节点（action: ADD/DROP）",
                 "params": [{"name": "action", "param_type": "path", "data_type": "string", "required": True, "description": "操作类型：ADD/DROP", "param_source": "llm_extract"}]},
                # ── SQL 执行 ──
                {"name": "execute_sql", "display_name": "执行 SQL", "method": "POST", "path": "/api/query/{ns_name}/{db_name}",
                 "description": "通过 HTTP API 执行 SQL 语句（SELECT/SHOW/INSERT 等）。"
                                "注意：ns_name 固定填 default_cluster，db_name 填目标数据库名。"
                                "示例路径：/api/query/default_cluster/mydb",
                 "params": [
                     {"name": "ns_name", "param_type": "path", "data_type": "string", "required": False, "description": "命名空间，固定填 default_cluster", "param_source": "static", "default_value": "default_cluster"},
                     {"name": "db_name", "param_type": "path", "data_type": "string", "required": True, "description": "目标数据库名（如 ods、dwd、information_schema）", "param_source": "llm_extract"},
                     {"name": "stmt", "param_type": "body", "data_type": "string", "required": True, "description": "要执行的 SQL 语句", "param_source": "llm_extract"},
                 ]},
                # ── 查询分析 ──
                {"name": "current_queries", "display_name": "当前查询", "method": "GET", "path": "/rest/v2/manager/query/current_queries",
                 "description": "获取当前正在运行的查询列表",
                 "params": [{"name": "is_all_node", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否查询所有 FE 节点，默认 true", "param_source": "llm_extract"}]},
                {"name": "query_info", "display_name": "查询详情", "method": "GET", "path": "/rest/v2/manager/query/query_info",
                 "description": "获取查询信息，支持按 query_id 或关键字搜索",
                 "params": [
                     {"name": "query_id", "param_type": "query", "data_type": "string", "required": False, "description": "指定查询 ID", "param_source": "llm_extract"},
                     {"name": "search", "param_type": "query", "data_type": "string", "required": False, "description": "搜索关键字", "param_source": "llm_extract"},
                     {"name": "is_all_node", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否查询所有 FE，默认 true", "param_source": "llm_extract"},
                 ]},
                {"name": "query_sql", "display_name": "查询 SQL", "method": "GET", "path": "/rest/v2/manager/query/sql/{query_id}",
                 "description": "获取指定查询执行的 SQL 语句",
                 "params": [{"name": "query_id", "param_type": "path", "data_type": "string", "required": True, "description": "查询 ID", "param_source": "llm_extract"}]},
                {"name": "query_profile_text", "display_name": "Profile 文本", "method": "GET", "path": "/rest/v2/manager/query/profile/text/{query_id}",
                 "description": "获取查询 Profile 文本格式（用于性能分析）",
                 "params": [{"name": "query_id", "param_type": "path", "data_type": "string", "required": True, "description": "查询 ID", "param_source": "llm_extract"}]},
                {"name": "query_profile_graph", "display_name": "Profile 图", "method": "GET", "path": "/rest/v2/manager/query/profile/graph/{query_id}",
                 "description": "获取查询 Profile 图形化执行树",
                 "params": [{"name": "query_id", "param_type": "path", "data_type": "string", "required": True, "description": "查询 ID", "param_source": "llm_extract"}]},
                {"name": "kill_query", "display_name": "取消查询", "method": "POST", "path": "/rest/v2/manager/query/kill/{query_id}",
                 "description": "取消正在执行的查询",
                 "params": [{"name": "query_id", "param_type": "path", "data_type": "string", "required": True, "description": "查询 ID", "param_source": "llm_extract"}]},
                {"name": "query_stats", "display_name": "查询统计", "method": "GET", "path": "/api/query_stats/{catalog_name}",
                 "description": "获取指定 Catalog 的查询统计信息",
                 "params": [
                     {"name": "catalog_name", "param_type": "path", "data_type": "string", "required": True, "description": "Catalog 名（Doris 内表用 default_cluster）", "param_source": "llm_extract"},
                     {"name": "summary", "param_type": "query", "data_type": "boolean", "required": False, "description": "true 仅返回摘要，false 返回详细统计", "param_source": "llm_extract"},
                 ]},
                # ── 表与数据 ──
                {"name": "table_schema", "display_name": "表结构", "method": "GET", "path": "/api/{db}/{table}/_schema",
                 "description": "获取指定表的 Schema 信息（列名、类型等）",
                 "params": [
                     {"name": "db", "param_type": "path", "data_type": "string", "required": True, "description": "数据库名", "param_source": "llm_extract"},
                     {"name": "table", "param_type": "path", "data_type": "string", "required": True, "description": "表名", "param_source": "llm_extract"},
                 ]},
                {"name": "get_ddl", "display_name": "获取 DDL", "method": "GET", "path": "/api/_get_ddl",
                 "description": "获取表的建表语句（DDL）",
                 "params": [
                     {"name": "db", "param_type": "query", "data_type": "string", "required": True, "description": "数据库名", "param_source": "llm_extract"},
                     {"name": "table", "param_type": "query", "data_type": "string", "required": True, "description": "表名", "param_source": "llm_extract"},
                 ]},
                {"name": "show_data", "display_name": "数据量", "method": "GET", "path": "/api/show_data",
                 "description": "获取数据库的数据量（字节）",
                 "params": [{"name": "db", "param_type": "query", "data_type": "string", "required": False, "description": "指定数据库名，不指定返回总量", "param_source": "llm_extract"}]},
                {"name": "show_table_data", "display_name": "表数据量", "method": "GET", "path": "/api/show_table_data",
                 "description": "获取各表的数据量（字节），支持按库/表筛选",
                 "params": [
                     {"name": "db", "param_type": "query", "data_type": "string", "required": False, "description": "指定数据库名", "param_source": "llm_extract"},
                     {"name": "table", "param_type": "query", "data_type": "string", "required": False, "description": "指定表名", "param_source": "llm_extract"},
                     {"name": "single_replica", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否返回单副本数据量", "param_source": "llm_extract"},
                 ]},
                {"name": "query_plan", "display_name": "查询计划", "method": "POST", "path": "/api/{db}/{table}/_query_plan",
                 "description": "获取 SQL 语句的查询执行计划",
                 "params": [
                     {"name": "db", "param_type": "path", "data_type": "string", "required": True, "description": "数据库名", "param_source": "llm_extract"},
                     {"name": "table", "param_type": "path", "data_type": "string", "required": True, "description": "表名", "param_source": "llm_extract"},
                     {"name": "sql", "param_type": "body", "data_type": "string", "required": True, "description": "要分析的 SQL 语句", "param_source": "llm_extract"},
                 ]},
                # ── 加载任务 ──
                {"name": "load_info", "display_name": "加载任务详情", "method": "GET", "path": "/api/{db}/_load_info",
                 "description": "获取指定 Label 的数据加载任务详情",
                 "params": [
                     {"name": "db", "param_type": "path", "data_type": "string", "required": True, "description": "数据库名", "param_source": "llm_extract"},
                     {"name": "label", "param_type": "query", "data_type": "string", "required": True, "description": "加载任务 Label", "param_source": "llm_extract"},
                 ]},
                # ── 会话 ──
                {"name": "session_info", "display_name": "当前会话", "method": "GET", "path": "/rest/v1/session",
                 "description": "获取当前 FE 的会话信息"},
                {"name": "all_sessions", "display_name": "所有会话", "method": "GET", "path": "/rest/v1/session/all",
                 "description": "获取所有 FE 的会话信息"},
                {"name": "connection_info", "display_name": "连接详情", "method": "GET", "path": "/api/connection",
                 "description": "根据连接 ID 获取当前执行的查询 ID",
                 "params": [{"name": "connection_id", "param_type": "query", "data_type": "string", "required": True, "description": "连接 ID（通过 MySQL show processlist 获取）", "param_source": "llm_extract"}]},
                # ── 配置 ──
                {"name": "get_fe_config", "display_name": "FE 配置", "method": "GET", "path": "/rest/v1/config/fe/",
                 "description": "获取当前 FE 配置信息"},
                {"name": "set_config", "display_name": "修改配置", "method": "GET", "path": "/api/_set_config",
                 "description": "修改 FE 配置项（通过 query 参数传 key=value）",
                 "params": [
                     {"name": "persist", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否持久化，默认 false", "param_source": "llm_extract"},
                     {"name": "reset_persist", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否清除原有持久化配置，默认 true", "param_source": "llm_extract"},
                 ]},
                {"name": "get_config_info", "display_name": "节点配置", "method": "POST", "path": "/rest/v2/manager/node/configuration_info",
                 "description": "获取 FE/BE 节点的配置信息",
                 "params": [
                     {"name": "type", "param_type": "query", "data_type": "string", "required": True, "description": "节点类型：fe/be", "param_source": "llm_extract"},
                     {"name": "conf_name", "param_type": "body", "data_type": "string", "required": False, "description": "指定配置项名称列表", "param_source": "llm_extract"},
                     {"name": "node", "param_type": "body", "data_type": "string", "required": False, "description": "指定节点列表", "param_source": "llm_extract"},
                 ]},
                {"name": "set_fe_config_v2", "display_name": "修改 FE 配置", "method": "POST", "path": "/rest/v2/manager/node/set_config/fe",
                 "description": "批量修改 FE 节点配置（支持指定节点、持久化）"},
                {"name": "set_be_config", "display_name": "修改 BE 配置", "method": "POST", "path": "/rest/v2/manager/node/set_config/be",
                 "description": "批量修改 BE 节点配置"},
                # ── 运维 ──
                {"name": "runtime_info", "display_name": "运行时信息", "method": "GET", "path": "/api/show_runtime_info",
                 "description": "获取 FE JVM 运行时信息（内存、线程）"},
                {"name": "colocate_info", "display_name": "Colocate 信息", "method": "GET", "path": "/api/colocate",
                 "description": "获取 Colocate Group 信息（表亲和性分组）",
                 "params": [
                     {"name": "db_id", "param_type": "query", "data_type": "integer", "required": False, "description": "指定数据库 ID", "param_source": "llm_extract"},
                     {"name": "group_id", "param_type": "query", "data_type": "integer", "required": False, "description": "指定 Group ID", "param_source": "llm_extract"},
                 ]},
            ],
        },
        {
            "name": "Apache Doris BE",
            "category": "compute",
            "description": "Apache Doris Backend HTTP API。提供 Tablet 管理、Compaction、RPC 诊断、日志查看等运维能力。默认端口 8040。",
            "base_url": "http://your-be-host:8040",
            "auth_type": "basic",
            "credential_template": {"fields": [
                {"key": "username", "label": "用户名", "type": "text", "required": True, "help_text": "Doris BE 用户名（需在 be.conf 中启用 enable_all_http_auth=true）"},
                {"key": "password", "label": "密码", "type": "password", "required": True, "help_text": "Doris BE 密码"},
            ]},
            "apis": [
                # ── BE 节点管理 ──
                {"name": "be_health", "display_name": "BE 健康检查", "method": "GET", "path": "/api/health",
                 "description": "检查 BE 节点存活状态"},
                {"name": "be_version", "display_name": "BE 版本", "method": "GET", "path": "/api/be_version_info",
                 "description": "获取 BE 版本信息"},
                {"name": "be_config", "display_name": "BE 配置", "method": "GET", "path": "/api/show_config",
                 "description": "获取 BE 配置项列表"},
                {"name": "be_set_config", "display_name": "修改 BE 配置", "method": "POST", "path": "/api/update_config",
                 "description": "修改 BE 配置项（通过 query 参数传 key=value）",
                 "params": [
                     {"name": "persist", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否持久化，默认 false", "param_source": "llm_extract"},
                 ]},
                {"name": "be_metrics", "display_name": "BE 指标", "method": "GET", "path": "/metrics",
                 "description": "获取 BE 指标信息（兼容 Prometheus 格式）",
                 "params": [
                     {"name": "type", "param_type": "query", "data_type": "string", "required": False, "description": "输出格式：core（仅核心项）/json，默认 all", "param_source": "llm_extract"},
                     {"name": "with_tablet", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否输出 Tablet 相关指标，默认 false", "param_source": "llm_extract"},
                 ]},
                # ── Compaction ──
                {"name": "compaction_status", "display_name": "Compaction 状态", "method": "GET", "path": "/api/compaction/run_status",
                 "description": "查看 BE 节点整体 Compaction 状态",
                 "params": [{"name": "tablet_id", "param_type": "query", "data_type": "integer", "required": False, "description": "指定 Tablet ID 查看单个 Tablet 状态", "param_source": "llm_extract"}]},
                {"name": "compaction_show", "display_name": "Tablet Compaction", "method": "GET", "path": "/api/compaction/show",
                 "description": "查看指定 Tablet 的 Compaction 状态",
                 "params": [{"name": "tablet_id", "param_type": "query", "data_type": "integer", "required": True, "description": "Tablet ID", "param_source": "llm_extract"}]},
                {"name": "compaction_run", "display_name": "触发 Compaction", "method": "POST", "path": "/api/compaction/run",
                 "description": "手动触发 Tablet Compaction",
                 "params": [
                     {"name": "tablet_id", "param_type": "query", "data_type": "integer", "required": False, "description": "Tablet ID", "param_source": "llm_extract"},
                     {"name": "table_id", "param_type": "query", "data_type": "integer", "required": False, "description": "Table ID（compact_type=full 时有效）", "param_source": "llm_extract"},
                     {"name": "compact_type", "param_type": "query", "data_type": "string", "required": True, "description": "压缩类型：base/cumulative/full", "param_source": "llm_extract"},
                 ]},
                # ── Tablet 管理 ──
                {"name": "tablet_info", "display_name": "Tablet 信息", "method": "GET", "path": "/tablets_json",
                 "description": "获取 BE 上的 Tablet 列表",
                 "params": [{"name": "limit", "param_type": "query", "data_type": "string", "required": False, "description": "输出数量限制，默认 1000，all 输出全部", "param_source": "llm_extract"}]},
                {"name": "tablet_distribution", "display_name": "Tablet 分布", "method": "GET", "path": "/api/tablets_distribution",
                 "description": "查看 Tablet 在各磁盘间的分布情况",
                 "params": [
                     {"name": "group_by", "param_type": "query", "data_type": "string", "required": True, "description": "分组方式（仅支持 partition）", "param_source": "llm_extract"},
                     {"name": "partition_id", "param_type": "query", "data_type": "integer", "required": False, "description": "指定分区 ID，不指定返回全部", "param_source": "llm_extract"},
                 ]},
                {"name": "tablet_meta", "display_name": "Tablet 元数据", "method": "GET", "path": "/api/meta/header/{tablet_id}",
                 "description": "获取指定 Tablet 的元数据头信息",
                 "params": [{"name": "tablet_id", "param_type": "path", "data_type": "integer", "required": True, "description": "Tablet ID", "param_source": "llm_extract"}]},
                {"name": "tablet_checksum", "display_name": "Tablet 校验", "method": "GET", "path": "/api/checksum",
                 "description": "计算 Tablet 的校验和",
                 "params": [
                     {"name": "tablet_id", "param_type": "query", "data_type": "integer", "required": True, "description": "Tablet ID", "param_source": "llm_extract"},
                     {"name": "version", "param_type": "query", "data_type": "integer", "required": True, "description": "版本号", "param_source": "llm_extract"},
                     {"name": "schema_hash", "param_type": "query", "data_type": "integer", "required": True, "description": "Schema Hash", "param_source": "llm_extract"},
                 ]},
                {"name": "tablet_snapshot", "display_name": "创建快照", "method": "GET", "path": "/api/snapshot",
                 "description": "为 Tablet 创建快照",
                 "params": [
                     {"name": "tablet_id", "param_type": "query", "data_type": "integer", "required": True, "description": "Tablet ID", "param_source": "llm_extract"},
                     {"name": "schema_hash", "param_type": "query", "data_type": "integer", "required": True, "description": "Schema Hash", "param_source": "llm_extract"},
                 ]},
                {"name": "tablet_reload", "display_name": "重载 Tablet", "method": "GET", "path": "/api/reload_tablet",
                 "description": "重新加载 Tablet 数据",
                 "params": [
                     {"name": "tablet_id", "param_type": "query", "data_type": "integer", "required": True, "description": "Tablet ID", "param_source": "llm_extract"},
                     {"name": "schema_hash", "param_type": "query", "data_type": "integer", "required": True, "description": "Schema Hash", "param_source": "llm_extract"},
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "数据文件路径", "param_source": "llm_extract"},
                 ]},
                {"name": "tablet_restore", "display_name": "恢复 Tablet", "method": "POST", "path": "/api/restore_tablet",
                 "description": "从回收站恢复 Tablet 数据",
                 "params": [
                     {"name": "tablet_id", "param_type": "query", "data_type": "integer", "required": True, "description": "Tablet ID", "param_source": "llm_extract"},
                     {"name": "schema_hash", "param_type": "query", "data_type": "integer", "required": True, "description": "Schema Hash", "param_source": "llm_extract"},
                 ]},
                {"name": "tablet_migration", "display_name": "Tablet 迁移", "method": "GET", "path": "/api/tablet_migration",
                 "description": "提交或查看 Tablet 迁移任务",
                 "params": [
                     {"name": "goal", "param_type": "query", "data_type": "string", "required": True, "description": "操作：run（提交迁移）/status（查看状态）", "param_source": "llm_extract"},
                     {"name": "tablet_id", "param_type": "query", "data_type": "integer", "required": True, "description": "Tablet ID", "param_source": "llm_extract"},
                     {"name": "schema_hash", "param_type": "query", "data_type": "integer", "required": True, "description": "Schema Hash", "param_source": "llm_extract"},
                     {"name": "disk", "param_type": "query", "data_type": "string", "required": True, "description": "目标磁盘路径", "param_source": "llm_extract"},
                 ]},
                {"name": "check_segment_lost", "display_name": "Segment 检查", "method": "GET", "path": "/api/check_tablet_segment_lost",
                 "description": "检查所有丢失 Segment 的 Tablet",
                 "params": [{"name": "repair", "param_type": "query", "data_type": "boolean", "required": False, "description": "true 将异常 Tablet 设为 SHUTDOWN 以便 FE 自动修复，false 仅返回列表", "param_source": "llm_extract"}]},
                {"name": "pad_rowset", "display_name": "补齐 Rowset", "method": "POST", "path": "/api/pad_rowset",
                 "description": "为空缺版本补齐空 Rowset（修复副本异常）",
                 "params": [
                     {"name": "tablet_id", "param_type": "query", "data_type": "integer", "required": True, "description": "Tablet ID", "param_source": "llm_extract"},
                     {"name": "start_version", "param_type": "query", "data_type": "integer", "required": True, "description": "起始版本", "param_source": "llm_extract"},
                     {"name": "end_version", "param_type": "query", "data_type": "integer", "required": True, "description": "结束版本", "param_source": "llm_extract"},
                 ]},
                # ── RPC ──
                {"name": "check_rpc", "display_name": "检查 RPC 通道", "method": "GET", "path": "/api/check_rpc_channel/{host}/{port}/{size}",
                 "description": "检查与指定节点的 RPC 连接缓存是否可用",
                 "params": [
                     {"name": "host", "param_type": "path", "data_type": "string", "required": True, "description": "目标主机", "param_source": "llm_extract"},
                     {"name": "port", "param_type": "path", "data_type": "integer", "required": True, "description": "BRPC 端口", "param_source": "llm_extract"},
                     {"name": "size", "param_type": "path", "data_type": "integer", "required": True, "description": "负载大小（字节，1~1024000）", "param_source": "llm_extract"},
                 ]},
                {"name": "reset_rpc", "display_name": "重置 RPC 缓存", "method": "GET", "path": "/api/reset_rpc_channel/{endpoints}",
                 "description": "重置 BRPC 连接缓存（all 或指定 endpoint 列表）",
                 "params": [{"name": "endpoints", "param_type": "path", "data_type": "string", "required": True, "description": "all 或 host1:port1,host2:port2", "param_source": "llm_extract"}]},
                # ── 日志 ──
                {"name": "load_error_log", "display_name": "加载错误日志", "method": "GET", "path": "/api/_load_error_log",
                 "description": "下载数据加载错误日志",
                 "params": [
                     {"name": "file", "param_type": "query", "data_type": "string", "required": True, "description": "日志文件路径", "param_source": "llm_extract"},
                     {"name": "token", "param_type": "query", "data_type": "string", "required": True, "description": "认证令牌", "param_source": "llm_extract"},
                 ]},
                {"name": "adjust_vlog", "display_name": "调整 VLOG 级别", "method": "POST", "path": "/api/glog/adjust",
                 "description": "动态调整 BE 模块的 VLOG 日志级别",
                 "params": [
                     {"name": "module", "param_type": "query", "data_type": "string", "required": True, "description": "模块名（对应 BE 无后缀文件名）", "param_source": "llm_extract"},
                     {"name": "level", "param_type": "query", "data_type": "integer", "required": True, "description": "VLOG 级别（1~10，-1 关闭）", "param_source": "llm_extract"},
                 ]},
            ],
        },
        {
            "name": "HDFS",
            "category": "storage",
            "description": "Hadoop 分布式文件系统。通过 WebHDFS REST API 提供文件的浏览、读取、写入、删除等操作。"
                           "默认端口 9870（NameNode Web UI）。",
            "base_url": "http://your-namenode:9870",
            "auth_type": "basic",
            "credential_template": {"fields": [
                {"key": "username", "label": "HDFS 用户", "type": "text", "required": True,
                 "help_text": "HDFS 操作用户名（如 hdfs、hive 等）",
                 "help_url": "https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/WebHDFS.html"},
            ]},
            "apis": [
                # ── 文件读写 ──
                {"name": "open", "display_name": "读取文件", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "读取文件内容（重定向到 DataNode）",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "文件路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：OPEN", "param_source": "static", "default_value": "OPEN"},
                     {"name": "offset", "param_type": "query", "data_type": "integer", "required": False, "description": "起始字节位置", "param_source": "llm_extract"},
                     {"name": "length", "param_type": "query", "data_type": "integer", "required": False, "description": "读取字节数", "param_source": "llm_extract"},
                 ]},
                {"name": "create", "display_name": "创建文件", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "创建并写入文件（两步式：先获取 DataNode 地址，再上传数据）",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "文件路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：CREATE", "param_source": "static", "default_value": "CREATE"},
                     {"name": "overwrite", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否覆盖已有文件", "param_source": "llm_extract"},
                     {"name": "replication", "param_type": "query", "data_type": "integer", "required": False, "description": "副本数", "param_source": "llm_extract"},
                     {"name": "blocksize", "param_type": "query", "data_type": "integer", "required": False, "description": "块大小（字节）", "param_source": "llm_extract"},
                     {"name": "permission", "param_type": "query", "data_type": "string", "required": False, "description": "权限（如 644）", "param_source": "llm_extract"},
                 ]},
                {"name": "append", "display_name": "追加内容", "method": "POST", "path": "/webhdfs/v1/{path}",
                 "description": "向文件追加数据（两步式）",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "文件路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：APPEND", "param_source": "static", "default_value": "APPEND"},
                 ]},
                {"name": "concat", "display_name": "合并文件", "method": "POST", "path": "/webhdfs/v1/{path}",
                 "description": "将多个源文件合并到目标文件",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目标文件路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：CONCAT", "param_source": "static", "default_value": "CONCAT"},
                     {"name": "sources", "param_type": "query", "data_type": "string", "required": True, "description": "源文件路径（逗号分隔）", "param_source": "llm_extract"},
                 ]},
                {"name": "truncate", "display_name": "截断文件", "method": "POST", "path": "/webhdfs/v1/{path}",
                 "description": "将文件截断到指定长度",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "文件路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：TRUNCATE", "param_source": "static", "default_value": "TRUNCATE"},
                     {"name": "newlength", "param_type": "query", "data_type": "integer", "required": True, "description": "截断后的长度（字节）", "param_source": "llm_extract"},
                 ]},
                # ── 目录操作 ──
                {"name": "mkdirs", "display_name": "创建目录", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "创建目录（支持递归创建）",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：MKDIRS", "param_source": "static", "default_value": "MKDIRS"},
                     {"name": "permission", "param_type": "query", "data_type": "string", "required": False, "description": "权限（默认 755）", "param_source": "llm_extract"},
                 ]},
                {"name": "rename", "display_name": "重命名", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "重命名文件或目录",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "原路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：RENAME", "param_source": "static", "default_value": "RENAME"},
                     {"name": "destination", "param_type": "query", "data_type": "string", "required": True, "description": "新路径", "param_source": "llm_extract"},
                 ]},
                {"name": "delete", "display_name": "删除", "method": "DELETE", "path": "/webhdfs/v1/{path}",
                 "description": "删除文件或目录",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：DELETE", "param_source": "static", "default_value": "DELETE"},
                     {"name": "recursive", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否递归删除", "param_source": "llm_extract"},
                 ]},
                # ── 文件/目录信息 ──
                {"name": "list_status", "display_name": "列出目录", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "列出目录下的文件和子目录",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：LISTSTATUS", "param_source": "static", "default_value": "LISTSTATUS"},
                 ]},
                {"name": "file_status", "display_name": "文件状态", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取文件/目录的元信息（类型、大小、副本数、权限等）",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETFILESTATUS", "param_source": "static", "default_value": "GETFILESTATUS"},
                 ]},
                {"name": "content_summary", "display_name": "目录汇总", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取目录汇总信息（总大小、文件数、目录数）",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETCONTENTSUMMARY", "param_source": "static", "default_value": "GETCONTENTSUMMARY"},
                 ]},
                {"name": "file_checksum", "display_name": "文件校验", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取文件校验和",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "文件路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETFILECHECKSUM", "param_source": "static", "default_value": "GETFILECHECKSUM"},
                 ]},
                {"name": "fs_status", "display_name": "文件系统状态", "method": "GET", "path": "/webhdfs/v1/",
                 "description": "获取文件系统状态（已用/剩余/总容量）",
                 "params": [
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETSTATUS", "param_source": "static", "default_value": "GETSTATUS"},
                 ]},
                {"name": "home_directory", "display_name": "用户主目录", "method": "GET", "path": "/webhdfs/v1/",
                 "description": "获取当前用户的主目录",
                 "params": [
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETHOMEDIRECTORY", "param_source": "static", "default_value": "GETHOMEDIRECTORY"},
                 ]},
                # ── 权限管理 ──
                {"name": "set_permission", "display_name": "设置权限", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "设置文件/目录权限",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：SETPERMISSION", "param_source": "static", "default_value": "SETPERMISSION"},
                     {"name": "permission", "param_type": "query", "data_type": "string", "required": True, "description": "权限（如 755、777）", "param_source": "llm_extract"},
                 ]},
                {"name": "set_owner", "display_name": "设置所有者", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "设置文件/目录的所有者和组",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：SETOWNER", "param_source": "static", "default_value": "SETOWNER"},
                     {"name": "owner", "param_type": "query", "data_type": "string", "required": False, "description": "新所有者", "param_source": "llm_extract"},
                     {"name": "group", "param_type": "query", "data_type": "string", "required": False, "description": "新组", "param_source": "llm_extract"},
                 ]},
                {"name": "set_replication", "display_name": "设置副本数", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "设置文件的副本因子",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "文件路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：SETREPLICATION", "param_source": "static", "default_value": "SETREPLICATION"},
                     {"name": "replication", "param_type": "query", "data_type": "integer", "required": True, "description": "副本数", "param_source": "llm_extract"},
                 ]},
                # ── 存储策略 ──
                {"name": "all_storage_policies", "display_name": "所有存储策略", "method": "GET", "path": "/webhdfs/v1",
                 "description": "获取所有存储策略（COLD/WARM/HOT/ONE_SSD/ALL_SSD 等）",
                 "params": [
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETALLSTORAGEPOLICY", "param_source": "static", "default_value": "GETALLSTORAGEPOLICY"},
                 ]},
                {"name": "set_storage_policy", "display_name": "设置存储策略", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "设置文件/目录的存储策略",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：SETSTORAGEPOLICY", "param_source": "static", "default_value": "SETSTORAGEPOLICY"},
                     {"name": "storagepolicy", "param_type": "query", "data_type": "string", "required": True, "description": "策略名（如 HOT、COLD）", "param_source": "llm_extract"},
                 ]},
                # ── 快照 ──
                {"name": "create_snapshot", "display_name": "创建快照", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "为目录创建快照",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：CREATESNAPSHOT", "param_source": "static", "default_value": "CREATESNAPSHOT"},
                     {"name": "snapshotname", "param_type": "query", "data_type": "string", "required": False, "description": "快照名称", "param_source": "llm_extract"},
                 ]},
                {"name": "delete_snapshot", "display_name": "删除快照", "method": "DELETE", "path": "/webhdfs/v1/{path}",
                 "description": "删除目录的指定快照",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：DELETESNAPSHOT", "param_source": "static", "default_value": "DELETESNAPSHOT"},
                     {"name": "snapshotname", "param_type": "query", "data_type": "string", "required": True, "description": "快照名称", "param_source": "llm_extract"},
                 ]},
                {"name": "snapshot_diff", "display_name": "快照差异", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取两个快照之间的差异",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETSNAPSHOTDIFF", "param_source": "static", "default_value": "GETSNAPSHOTDIFF"},
                     {"name": "oldsnapshotname", "param_type": "query", "data_type": "string", "required": True, "description": "源快照名", "param_source": "llm_extract"},
                     {"name": "snapshotname", "param_type": "query", "data_type": "string", "required": True, "description": "目标快照名", "param_source": "llm_extract"},
                 ]},
                {"name": "list_status_batch", "display_name": "分页列目录", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "分页列出目录内容（适合大目录）",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：LISTSTATUS_BATCH", "param_source": "static", "default_value": "LISTSTATUS_BATCH"},
                     {"name": "startAfter", "param_type": "query", "data_type": "string", "required": False, "description": "上一批最后一条的 pathSuffix", "param_source": "llm_extract"},
                 ]},
                {"name": "quota_usage", "display_name": "配额使用", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取目录的配额使用情况",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETQUOTAUSAGE", "param_source": "static", "default_value": "GETQUOTAUSAGE"},
                 ]},
                {"name": "set_quota", "display_name": "设置配额", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "设置目录的命名空间和存储空间配额",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：SETQUOTA", "param_source": "static", "default_value": "SETQUOTA"},
                     {"name": "namespacequota", "param_type": "query", "data_type": "integer", "required": True, "description": "命名空间配额", "param_source": "llm_extract"},
                     {"name": "storagespacequota", "param_type": "query", "data_type": "integer", "required": False, "description": "存储空间配额", "param_source": "llm_extract"},
                 ]},
                {"name": "trash_root", "display_name": "回收站路径", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取指定路径的回收站根目录",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETTRASHROOT", "param_source": "static", "default_value": "GETTRASHROOT"},
                 ]},
                {"name": "set_times", "display_name": "设置时间", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "设置文件/目录的访问和修改时间",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：SETTIMES", "param_source": "static", "default_value": "SETTIMES"},
                     {"name": "modificationtime", "param_type": "query", "data_type": "integer", "required": False, "description": "修改时间（毫秒）", "param_source": "llm_extract"},
                     {"name": "accesstime", "param_type": "query", "data_type": "integer", "required": False, "description": "访问时间（毫秒）", "param_source": "llm_extract"},
                 ]},
                # ── ACL ──
                {"name": "set_acl", "display_name": "设置 ACL", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "替换整个 ACL",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：SETACL", "param_source": "static", "default_value": "SETACL"},
                     {"name": "aclspec", "param_type": "query", "data_type": "string", "required": True, "description": "ACL 规范字符串", "param_source": "llm_extract"},
                 ]},
                {"name": "get_acl_status", "display_name": "获取 ACL", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取文件/目录的 ACL 状态",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETACLSTATUS", "param_source": "static", "default_value": "GETACLSTATUS"},
                 ]},
                {"name": "modify_acl", "display_name": "修改 ACL", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "修改现有 ACL 条目",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：MODIFYACLENTRIES", "param_source": "static", "default_value": "MODIFYACLENTRIES"},
                     {"name": "aclspec", "param_type": "query", "data_type": "string", "required": True, "description": "ACL 规范字符串", "param_source": "llm_extract"},
                 ]},
                {"name": "remove_acl_entries", "display_name": "删除 ACL 条目", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "删除指定的 ACL 条目",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：REMOVEACLENTRIES", "param_source": "static", "default_value": "REMOVEACLENTRIES"},
                     {"name": "aclspec", "param_type": "query", "data_type": "string", "required": True, "description": "ACL 规范字符串", "param_source": "llm_extract"},
                 ]},
                {"name": "remove_default_acl", "display_name": "删除默认 ACL", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "删除目录的所有默认 ACL 条目",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：REMOVEDEFAULTACL", "param_source": "static", "default_value": "REMOVEDEFAULTACL"},
                 ]},
                {"name": "remove_acl", "display_name": "删除所有 ACL", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "删除文件/目录的所有 ACL（访问和默认）",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：REMOVEACL", "param_source": "static", "default_value": "REMOVEACL"},
                 ]},
                {"name": "check_access", "display_name": "检查权限", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "检查当前用户是否有指定的访问权限",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：CHECKACCESS", "param_source": "static", "default_value": "CHECKACCESS"},
                     {"name": "fsaction", "param_type": "query", "data_type": "string", "required": True, "description": "访问动作（如 r、w、x、rw）", "param_source": "llm_extract"},
                 ]},
                # ── XAttr ──
                {"name": "set_xattr", "display_name": "设置扩展属性", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "设置文件/目录的扩展属性",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：SETXATTR", "param_source": "static", "default_value": "SETXATTR"},
                     {"name": "xattr.name", "param_type": "query", "data_type": "string", "required": True, "description": "属性名", "param_source": "llm_extract"},
                     {"name": "xattr.value", "param_type": "query", "data_type": "string", "required": True, "description": "属性值", "param_source": "llm_extract"},
                 ]},
                {"name": "get_xattrs", "display_name": "获取扩展属性", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取文件/目录的扩展属性",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETXATTRS", "param_source": "static", "default_value": "GETXATTRS"},
                     {"name": "xattr.name", "param_type": "query", "data_type": "string", "required": False, "description": "属性名（不指定返回全部）", "param_source": "llm_extract"},
                 ]},
                {"name": "list_xattrs", "display_name": "列出扩展属性", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "列出文件/目录的所有扩展属性名",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：LISTXATTRS", "param_source": "static", "default_value": "LISTXATTRS"},
                 ]},
                {"name": "remove_xattr", "display_name": "删除扩展属性", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "删除文件/目录的扩展属性",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：REMOVEXATTR", "param_source": "static", "default_value": "REMOVEXATTR"},
                     {"name": "xattr.name", "param_type": "query", "data_type": "string", "required": True, "description": "属性名", "param_source": "llm_extract"},
                 ]},
                # ── 纠删码 ──
                {"name": "get_ec_policies", "display_name": "EC 策略列表", "method": "GET", "path": "/webhdfs/v1/",
                 "description": "获取所有纠删码策略及其状态",
                 "params": [
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETECPOLICIES", "param_source": "static", "default_value": "GETECPOLICIES"},
                 ]},
                {"name": "set_ec_policy", "display_name": "设置 EC 策略", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "为目录设置纠删码策略",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：SETECPOLICY", "param_source": "static", "default_value": "SETECPOLICY"},
                     {"name": "ecpolicy", "param_type": "query", "data_type": "string", "required": True, "description": "EC 策略名（如 RS-6-3-1024k）", "param_source": "llm_extract"},
                 ]},
                {"name": "get_ec_policy", "display_name": "获取 EC 策略", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取目录的纠删码策略",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETECPOLICY", "param_source": "static", "default_value": "GETECPOLICY"},
                 ]},
                {"name": "unset_ec_policy", "display_name": "取消 EC 策略", "method": "POST", "path": "/webhdfs/v1/{path}",
                 "description": "取消目录的纠删码策略",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：UNSETECPOLICY", "param_source": "static", "default_value": "UNSETECPOLICY"},
                 ]},
                # ── 更多快照 ──
                {"name": "allow_snapshot", "display_name": "允许快照", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "标记目录为可快照",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：ALLOWSNAPSHOT", "param_source": "static", "default_value": "ALLOWSNAPSHOT"},
                 ]},
                {"name": "disallow_snapshot", "display_name": "禁止快照", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "取消目录的可快照标记",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：DISALLOWSNAPSHOT", "param_source": "static", "default_value": "DISALLOWSNAPSHOT"},
                 ]},
                {"name": "rename_snapshot", "display_name": "重命名快照", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "重命名快照",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：RENAMESNAPSHOT", "param_source": "static", "default_value": "RENAMESNAPSHOT"},
                     {"name": "oldsnapshotname", "param_type": "query", "data_type": "string", "required": True, "description": "原快照名", "param_source": "llm_extract"},
                     {"name": "snapshotname", "param_type": "query", "data_type": "string", "required": True, "description": "新快照名", "param_source": "llm_extract"},
                 ]},
                {"name": "snapshot_list", "display_name": "快照列表", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取目录的所有快照列表",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETSNAPSHOTLIST", "param_source": "static", "default_value": "GETSNAPSHOTLIST"},
                 ]},
                {"name": "snapshottable_dirs", "display_name": "可快照目录", "method": "GET", "path": "/webhdfs/v1/",
                 "description": "获取所有可快照的目录列表",
                 "params": [
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETSNAPSHOTTABLEDIRECTORYLIST", "param_source": "static", "default_value": "GETSNAPSHOTTABLEDIRECTORYLIST"},
                 ]},
                # ── 其他 ──
                {"name": "server_defaults", "display_name": "服务端默认值", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取服务端默认配置（副本数、块大小、校验类型等）",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETSERVERDEFAULTS", "param_source": "static", "default_value": "GETSERVERDEFAULTS"},
                 ]},
                {"name": "symlink_target", "display_name": "符号链接目标", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取符号链接的目标路径",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "符号链接路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETLINKTARGET", "param_source": "static", "default_value": "GETLINKTARGET"},
                 ]},
                {"name": "block_locations", "display_name": "块位置", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取文件的数据块位置信息",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "文件路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETFILEBLOCKLOCATIONS", "param_source": "static", "default_value": "GETFILEBLOCKLOCATIONS"},
                 ]},
            ],
        },
        {
            "name": "YARN ResourceManager",
            "category": "resource",
            "description": "Hadoop YARN 资源管理器。通过 ResourceManager REST API 监控集群资源、管理应用程序、查看节点状态。"
                           "默认端口 8088。",
            "base_url": "http://your-rm-host:8088",
            "auth_type": "basic",
            "credential_template": {"fields": [
                {"key": "username", "label": "用户名", "type": "text", "required": False, "help_text": "YARN 用户名（无认证可留空）"},
                {"key": "password", "label": "密码", "type": "password", "required": False, "help_text": "YARN 密码（无认证可留空）"},
            ]},
            "apis": [
                # ── 集群信息 ──
                {"name": "cluster_info", "display_name": "集群信息", "method": "GET", "path": "/ws/v1/cluster/info",
                 "description": "获取 YARN 集群基本信息：HA 状态、RM 版本、Hadoop 版本"},
                {"name": "cluster_metrics", "display_name": "集群资源指标", "method": "GET", "path": "/ws/v1/cluster/metrics",
                 "description": "获取集群资源使用概况：总/已用内存、VCores、节点数、应用数"},
                {"name": "scheduler_info", "display_name": "调度器信息", "method": "GET", "path": "/ws/v1/cluster/scheduler",
                 "description": "获取调度器配置和队列资源分配情况"},
                # ── 节点管理 ──
                {"name": "list_nodes", "display_name": "节点列表", "method": "GET", "path": "/ws/v1/cluster/nodes",
                 "description": "获取所有 NodeManager 节点状态、资源、健康状况"},
                {"name": "get_node", "display_name": "节点详情", "method": "GET", "path": "/ws/v1/cluster/nodes/{nodeId}",
                 "description": "获取指定节点的详细资源和运行中容器信息",
                 "params": [{"name": "nodeId", "param_type": "path", "data_type": "string", "required": True, "description": "节点 ID", "param_source": "llm_extract"}]},
                # ── 应用管理 ──
                {"name": "list_apps", "display_name": "应用列表", "method": "GET", "path": "/ws/v1/cluster/apps",
                 "description": "获取应用列表，支持按状态、用户、队列筛选",
                 "params": [
                     {"name": "states", "param_type": "query", "data_type": "string", "required": False, "description": "应用状态（逗号分隔：RUNNING,FINISHED,FAILED,KILLED）", "param_source": "llm_extract"},
                     {"name": "user", "param_type": "query", "data_type": "string", "required": False, "description": "用户名筛选", "param_source": "llm_extract"},
                     {"name": "queue", "param_type": "query", "data_type": "string", "required": False, "description": "队列名筛选", "param_source": "llm_extract"},
                     {"name": "limit", "param_type": "query", "data_type": "integer", "required": False, "description": "返回数量限制", "param_source": "llm_extract"},
                 ]},
                {"name": "get_app", "display_name": "应用详情", "method": "GET", "path": "/ws/v1/cluster/apps/{appId}",
                 "description": "获取应用详细信息：状态、资源占用、运行时间、诊断信息",
                 "params": [{"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"}]},
                {"name": "kill_app", "display_name": "终止应用", "method": "PUT", "path": "/ws/v1/cluster/apps/{appId}/state",
                 "description": "终止指定应用（发送 KILL 命令）",
                 "params": [
                     {"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"},
                     {"name": "state", "param_type": "body", "data_type": "string", "required": True, "description": "目标状态：KILLED", "param_source": "llm_extract"},
                 ]},
                {"name": "get_app_attempts", "display_name": "应用尝试列表", "method": "GET", "path": "/ws/v1/cluster/apps/{appId}/appattempts",
                 "description": "获取应用的所有尝试（重试记录）",
                 "params": [{"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"}]},
                {"name": "move_app", "display_name": "移动应用队列", "method": "PUT", "path": "/ws/v1/cluster/apps/{appId}/queue",
                 "description": "将应用移动到另一个队列",
                 "params": [
                     {"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"},
                     {"name": "queue", "param_type": "body", "data_type": "string", "required": True, "description": "目标队列名", "param_source": "llm_extract"},
                 ]},
                {"name": "update_priority", "display_name": "更新优先级", "method": "PUT", "path": "/ws/v1/cluster/apps/{appId}/priority",
                 "description": "修改应用的优先级",
                 "params": [
                     {"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"},
                     {"name": "priority", "param_type": "body", "data_type": "integer", "required": True, "description": "新优先级值", "param_source": "llm_extract"},
                 ]},
                # ── 统计 ──
                {"name": "app_statistics", "display_name": "应用统计", "method": "GET", "path": "/ws/v1/cluster/appstatistics",
                 "description": "获取应用统计数据（按状态和类型分组）"},
                # ── 容器 ──
                {"name": "list_containers", "display_name": "容器列表", "method": "GET", "path": "/ws/v1/cluster/apps/{appId}/appattempts/{appAttemptId}/containers",
                 "description": "获取应用尝试的容器列表",
                 "params": [
                     {"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"},
                     {"name": "appAttemptId", "param_type": "path", "data_type": "string", "required": True, "description": "尝试 ID", "param_source": "llm_extract"},
                 ]},
                {"name": "get_container", "display_name": "容器详情", "method": "GET", "path": "/ws/v1/cluster/apps/{appId}/appattempts/{appAttemptId}/containers/{containerId}",
                 "description": "获取容器的详细信息",
                 "params": [
                     {"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"},
                     {"name": "appAttemptId", "param_type": "path", "data_type": "string", "required": True, "description": "尝试 ID", "param_source": "llm_extract"},
                     {"name": "containerId", "param_type": "path", "data_type": "string", "required": True, "description": "容器 ID", "param_source": "llm_extract"},
                 ]},
                {"name": "signal_container", "display_name": "发送信号", "method": "POST", "path": "/ws/v1/cluster/apps/{appId}/appattempts/{appAttemptId}/containers/{containerId}/signal",
                 "description": "向容器发送信号",
                 "params": [
                     {"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"},
                     {"name": "appAttemptId", "param_type": "path", "data_type": "string", "required": True, "description": "尝试 ID", "param_source": "llm_extract"},
                     {"name": "containerId", "param_type": "path", "data_type": "string", "required": True, "description": "容器 ID", "param_source": "llm_extract"},
                     {"name": "signal", "param_type": "body", "data_type": "string", "required": True, "description": "信号类型（如 OUTPUT_THREAD_DUMP）", "param_source": "llm_extract"},
                 ]},
                # ── 超时管理 ──
                {"name": "get_app_timeouts", "display_name": "应用超时", "method": "GET", "path": "/ws/v1/cluster/apps/{appId}/timeouts",
                 "description": "获取应用的所有超时配置",
                 "params": [{"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"}]},
                {"name": "update_app_timeout", "display_name": "更新超时", "method": "PUT", "path": "/ws/v1/cluster/apps/{appId}/timeouts/{type}",
                 "description": "更新应用的超时值",
                 "params": [
                     {"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"},
                     {"name": "type", "param_type": "path", "data_type": "string", "required": True, "description": "超时类型", "param_source": "llm_extract"},
                 ]},
                # ── 应用提交 ──
                {"name": "new_application", "display_name": "创建应用", "method": "POST", "path": "/ws/v1/cluster/apps/new-application",
                 "description": "创建新应用，返回 applicationId"},
                {"name": "submit_application", "display_name": "提交应用", "method": "POST", "path": "/ws/v1/cluster/apps",
                 "description": "提交新应用"},
                # ── 节点资源 ──
                {"name": "update_node_resource", "display_name": "更新节点资源", "method": "POST", "path": "/ws/v1/cluster/nodes/{nodeId}/resource",
                 "description": "更新节点的资源配置",
                 "params": [
                     {"name": "nodeId", "param_type": "path", "data_type": "string", "required": True, "description": "节点 ID", "param_source": "llm_extract"},
                 ]},
                # ── 调度器配置 ──
                {"name": "get_scheduler_conf", "display_name": "调度器配置", "method": "GET", "path": "/ws/v1/cluster/scheduler-conf",
                 "description": "获取调度器配置"},
                {"name": "update_scheduler_conf", "display_name": "修改调度器配置", "method": "PUT", "path": "/ws/v1/cluster/scheduler-conf",
                 "description": "修改调度器配置"},
                {"name": "scheduler_activities", "display_name": "调度活动", "method": "GET", "path": "/ws/v1/cluster/scheduler/activities",
                 "description": "获取调度器活动信息"},
                # ── 预约 ──
                {"name": "list_reservations", "display_name": "预约列表", "method": "GET", "path": "/ws/v1/cluster/reservation/list",
                 "description": "列出所有预约"},
                {"name": "create_reservation", "display_name": "创建预约", "method": "POST", "path": "/ws/v1/cluster/reservation/create",
                 "description": "创建预约定义"},
                {"name": "submit_reservation", "display_name": "提交预约", "method": "POST", "path": "/ws/v1/cluster/reservation/submit",
                 "description": "提交预约"},
                {"name": "update_reservation", "display_name": "更新预约", "method": "PUT", "path": "/ws/v1/cluster/reservation/update",
                 "description": "更新预约"},
                {"name": "delete_reservation", "display_name": "删除预约", "method": "DELETE", "path": "/ws/v1/cluster/reservation/delete",
                 "description": "删除预约"},
                # ── 委托令牌 ──
                {"name": "create_delegation_token", "display_name": "创建令牌", "method": "POST", "path": "/ws/v1/cluster/delegation-token",
                 "description": "创建委托令牌"},
                {"name": "cancel_delegation_token", "display_name": "取消令牌", "method": "POST", "path": "/ws/v1/cluster/delegation-token/cancel",
                 "description": "取消委托令牌"},
            ],
        },
        {
            "name": "YARN NodeManager",
            "category": "resource",
            "description": "YARN NodeManager REST API。提供容器日志查看、节点状态、应用管理等能力。"
                           "默认端口 8042。每个 NodeManager 节点独立部署，需要单独配置地址。",
            "base_url": "http://your-nm-host:8042",
            "auth_type": "basic",
            "credential_template": {"fields": [
                {"key": "username", "label": "用户名", "type": "text", "required": False, "help_text": "NodeManager 用户名（无认证可留空）"},
                {"key": "password", "label": "密码", "type": "password", "required": False, "help_text": "NodeManager 密码（无认证可留空）"},
            ]},
            "apis": [
                {"name": "node_info", "display_name": "节点信息", "method": "GET", "path": "/ws/v1/node/info",
                 "description": "获取 NodeManager 节点信息：主机名、内存/VCores、健康状态、版本"},
                {"name": "list_apps", "display_name": "应用列表", "method": "GET", "path": "/ws/v1/node/apps",
                 "description": "获取该节点上运行的应用列表",
                 "params": [
                     {"name": "state", "param_type": "query", "data_type": "string", "required": False, "description": "应用状态筛选", "param_source": "llm_extract"},
                     {"name": "user", "param_type": "query", "data_type": "string", "required": False, "description": "用户名筛选", "param_source": "llm_extract"},
                 ]},
                {"name": "get_app", "display_name": "应用详情", "method": "GET", "path": "/ws/v1/node/apps/{appid}",
                 "description": "获取该节点上指定应用的详细信息",
                 "params": [{"name": "appid", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"}]},
                {"name": "list_containers", "display_name": "容器列表", "method": "GET", "path": "/ws/v1/node/containers",
                 "description": "获取该节点上所有容器列表"},
                {"name": "get_container", "display_name": "容器详情", "method": "GET", "path": "/ws/v1/node/containers/{containerid}",
                 "description": "获取指定容器的详细信息",
                 "params": [{"name": "containerid", "param_type": "path", "data_type": "string", "required": True, "description": "容器 ID", "param_source": "llm_extract"}]},
                {"name": "get_container_logs", "display_name": "容器日志", "method": "GET", "path": "/ws/v1/node/containers/{containerid}/logs",
                 "description": "获取容器的日志内容（stdout/stderr/syslog）",
                 "params": [
                     {"name": "containerid", "param_type": "path", "data_type": "string", "required": True, "description": "容器 ID", "param_source": "llm_extract"},
                     {"name": "filename", "param_type": "query", "data_type": "string", "required": False, "description": "日志文件名（stdout/stderr/syslog），默认 syslog", "param_source": "llm_extract"},
                     {"name": "start", "param_type": "query", "data_type": "integer", "required": False, "description": "起始字节偏移量", "param_source": "llm_extract"},
                     {"name": "end", "param_type": "query", "data_type": "integer", "required": False, "description": "结束字节偏移量", "param_source": "llm_extract"},
                 ]},
                {"name": "list_auxiliary_services", "display_name": "辅助服务", "method": "GET", "path": "/ws/v1/node/auxiliaryservices",
                 "description": "获取辅助服务列表"},
            ],
        },
    ]

    from app.db.models import UserModel

    with create_db_session() as db:
        existing = {s.name for s in db.execute(select(ExternalSystemModel)).scalars().all()}
        # 查找一个有效 user 作为 created_by（优先 id=1，否则取第一个用户，否则 None）
        admin_user = db.get(UserModel, 1) or db.execute(select(UserModel).limit(1)).scalar_one_or_none()
        created_by = admin_user.id if admin_user else None
        created_count = 0
        updated_count = 0
        for preset in PRESETS:
            if preset["name"] in existing:
                # 更新已有系统的分类和 API 参数
                sys = db.scalar(select(ExternalSystemModel).where(ExternalSystemModel.name == preset["name"]))
                if not sys:
                    continue
                # 同步分类（始终更新，确保与预设一致）
                preset_cat = preset.get("category", "other")
                if sys.category != preset_cat:
                    sys.category = preset_cat
                    updated_count += 1
                # 同步 API 参数：删除旧参数，从预设重建
                preset_apis = {a["name"]: a for a in preset.get("apis", [])}
                for api in db.execute(
                    select(ExternalApiModel).where(ExternalApiModel.system_id == sys.id)
                ).scalars().all():
                    api_def = preset_apis.get(api.name)
                    if api_def:
                        # 更新路径、方法、审批
                        api.path = api_def["path"]
                        api.method = api_def["method"]
                        api.description = api_def.get("description", "")
                        api.display_name = api_def["display_name"]
                        api.requires_approval = api_def["method"] in ("POST", "PUT", "DELETE", "PATCH")
                        # 删除旧参数，重建
                        db.query(ExternalApiParamModel).filter(ExternalApiParamModel.api_id == api.id).delete()
                        for p in api_def.get("params", []):
                            db.add(ExternalApiParamModel(
                                api_id=api.id,
                                name=p["name"],
                                param_type=p["param_type"],
                                data_type=p.get("data_type", "string"),
                                required=p.get("required", False),
                                description=p.get("description", ""),
                                default_value=p.get("default_value"),
                                param_source=p.get("param_source", "static"),
                                label=p.get("label"),
                            ))
                continue
            system = ExternalSystemModel(
                name=preset["name"],
                description=preset["description"],
                category=preset.get("category", "other"),
                base_url=preset["base_url"],
                auth_type=preset["auth_type"],
                credential_template_json=json.dumps(preset.get("credential_template", {})),
                published=True,
                headers_json="{}",
                created_by=created_by,
                jwt_login_url=preset.get("jwt_login_url"),
                jwt_refresh_url=preset.get("jwt_refresh_url"),
                jwt_request_body_template=preset.get("jwt_request_body_template"),
                jwt_response_token_path=preset.get("jwt_response_token_path"),
                jwt_response_expires_path=preset.get("jwt_response_expires_path"),
                jwt_response_token_header=preset.get("jwt_response_token_header"),
                login_token_source=preset.get("login_token_source"),
                login_inject_mode=preset.get("login_inject_mode"),
                login_inject_header_name=preset.get("login_inject_header_name"),
                jwt_refresh_body_template=preset.get("jwt_refresh_body_template"),
            )
            db.add(system)
            db.flush()
            for api_def in preset.get("apis", []):
                api = ExternalApiModel(
                    system_id=system.id,
                    name=api_def["name"],
                    display_name=api_def["display_name"],
                    description=api_def.get("description", ""),
                    method=api_def["method"],
                    path=api_def["path"],
                    requires_approval=api_def["method"] in ("POST", "PUT", "DELETE", "PATCH"),
                    timeout_seconds=30,
                )
                db.add(api)
                db.flush()
                # 创建 API 参数
                for p in api_def.get("params", []):
                    db.add(ExternalApiParamModel(
                        api_id=api.id,
                        name=p["name"],
                        param_type=p["param_type"],
                        data_type=p.get("data_type", "string"),
                        required=p.get("required", False),
                        description=p.get("description", ""),
                        default_value=p.get("default_value"),
                        param_source=p.get("param_source", "static"),
                        label=p.get("label"),
                    ))
            created_count += 1
        if created_count > 0 or updated_count > 0:
            db.commit()
            if created_count > 0:
                logger.info("Seeded %d preset external systems", created_count)
            if updated_count > 0:
                logger.info("Updated category for %d existing external systems", updated_count)
