"""自有 Agent 核心层（wuwei 退役 A5：全新系统，不兼容 wuwei）。

模块清单：
- types: 消息/工具调用/LLM 响应/事件/会话（干净最小集合）
- tool_registry: Tool / ToolRegistry（`@registry.tool` 装饰器 API）
- gateway: openai SDK 直连网关（原三层网关语义合一）
- plugins / builtin: 插件上下文与 10 个内置工具插件（逐字移植）
- action_log: 会话级 append-only 动作日志（逐字移植）
"""
