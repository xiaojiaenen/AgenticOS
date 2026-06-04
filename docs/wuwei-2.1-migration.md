# Wuwei 2.0 → 2.1 迁移方案

## 一、破坏性变更总结

wuwei 2.1.0 **移除了整个 Hook 系统**，全面切换到 Middleware：

| 旧 API (2.0) | 新 API (2.1) | 变化 |
|-------------|-------------|------|
| `from wuwei import StorageHook` | `from wuwei.middleware import StorageMiddleware` | 类名 + 接口全变 |
| `from wuwei import HitlHook` | `from wuwei.middleware import HitlMiddleware` | 接口大改 |
| `from wuwei import ContextCompressionHook` | `from wuwei.middleware import ContextCompressionMiddleware` | 参数不同 |
| `from wuwei import SkillHook` | `from wuwei.middleware import SkillMiddleware` | 参数不同 |
| `from wuwei.runtime import ApprovalPolicy` | ❌ 已移除 | 由 middleware 内部处理 |
| `from wuwei.runtime.hooks import RuntimeHook` | `from wuwei.middleware import Middleware` | 基类更换 |
| `agent.hooks.register(...)` | `stack.add(...)` | 注册方式不同 |
| `Agent(hooks=[...])` | `Agent(middleware=MiddlewareStack())` | 参数名更换 |

**影响范围**：16 个 Python 文件引用 wuwei，其中 4 个直接受影响。

## 二、影响文件清单

| 文件 | 影响等级 | 需要改动 |
|------|---------|---------|
| `app/services/agent_service.py` | 🔴 高 | Hook 注册 → Middleware 栈构建 |
| `app/services/session_storage.py` | 🟡 中 | `AgentSession` / `Message` 路径可能变更 |
| `app/services/approval_manager.py` | 🟡 中 | `ApprovalRequest` / `ApprovalDecision` 可能变更 |
| `app/services/announcement_ai_service.py` | 🟢 低 | `LLMGateway` / `Message` 应兼容 |
| `app/tools/website_file_tools.py` | 🟡 中 | 私有导入可能变更 |
| 其余 11 个 `*_tools.py` | 🟢 低 | `ToolRegistry` / `@registry.tool()` 应兼容 |
| `tests/test_agent_service.py` | 🟡 中 | `AgentEvent` / `Message` 构造方式 |

## 三、逐模块迁移方案

### 模块 1：agent_service.py（核心，~120 行改动）

#### 3.1 Import 变更

```python
# === 旧版 (2.0) ===
from wuwei import (
    Agent, AgentEvent, ContextCompressionHook, FileSystemSkillProvider,
    HitlHook, SkillHook, SkillManager, StorageHook,
)
from wuwei.llm import LLMGateway
from wuwei.memory.context_compressor import LLMContextCompressor
from wuwei.runtime import ApprovalPolicy
from wuwei.runtime.hooks import RuntimeHook
from wuwei.tools import ToolRegistry
from wuwei.tools.builtin import register_skill_tools

# === 新版 (2.1) ===
from wuwei import Agent, AgentEvent, FileSystemSkillProvider, SkillManager
from wuwei.llm import LLMGateway
from wuwei.middleware import (
    Middleware, MiddlewareContext, MiddlewareStack,
    StorageMiddleware, HitlMiddleware, ContextCompressionMiddleware, SkillMiddleware,
)
from wuwei.tools import ToolRegistry
from wuwei.tools.builtin import register_skill_tools
```

#### 3.2 ThinkingHistoryCompatibilityHook → Middleware

```python
# === 旧版 ===
class ThinkingHistoryCompatibilityHook(RuntimeHook):
    async def before_llm(self, session, messages, tools, *, step: int, task=None):
        filtered_messages = [...]
        return filtered_messages, tools

# === 新版 ===
class ThinkingHistoryCompatibilityMiddleware(Middleware):
    """Keep provider thinking-mode histories free of local synthetic replies."""

    async def before_llm(self, ctx: MiddlewareContext) -> MiddlewareContext:
        messages = ctx.state.messages
        ctx.state.messages = [
            msg for msg in messages
            if not (
                msg.role == "assistant"
                and msg.content == MAX_STEPS_LIMIT_MESSAGE
                and not getattr(msg, 'reasoning_content', None)
                and not getattr(msg, 'tool_calls', None)
            )
        ]
        return ctx
```

**接口变化**：
- 旧：`before_llm(session, messages, tools, *, step, task) → (messages, tools)`
- 新：`before_llm(ctx: MiddlewareContext) → MiddlewareContext`

#### 3.3 Hook 注册 → Middleware 栈构建

```python
# === 旧版 (_register_runtime_hooks) ===
def _register_runtime_hooks(self, agent: Agent, *, approval_tools):
    if approval_tools and self.settings.hitl_enabled:
        agent.hooks.register(HitlHook(provider=self.approval_manager, policy=ApprovalPolicy(...)))
    if self.settings.context_compression_enabled:
        agent.hooks.register(ContextCompressionHook(compressor=LLMContextCompressor(agent.llm), ...))

# === 新版 (_build_middleware_stack) ===
def _build_middleware_stack(self, profile, llm) -> MiddlewareStack:
    stack = MiddlewareStack()

    # 1. 存储中间件（替代 StorageHook）
    stack.add(StorageMiddleware(storage_path=str(DATA_DIR / "sessions")))

    # 2. HITL 审批中间件（替代 HitlHook）
    approval_tools = set(profile.approval_tools)
    if approval_tools and self.settings.hitl_enabled:
        stack.add(HitlMiddleware(
            approval_provider=self.approval_manager.request_approval_bool,
            auto_approve_tools=[],
            auto_reject_tools=[],
        ))

    # 3. 上下文压缩中间件（替代 ContextCompressionHook）
    if self.settings.context_compression_enabled:
        stack.add(ContextCompressionMiddleware(
            llm=llm,
            trigger_tokens=self.settings.context_compress_after_turns * 500,
            keep_recent=self.settings.context_keep_recent_turns,
        ))

    # 4. Skill 指令中间件（替代 SkillHook）
    if "skill" in profile.builtin_tools:
        stack.add(SkillMiddleware(skill_manager=self._build_skill_manager(profile)))

    # 5. 思考历史兼容中间件
    stack.add(ThinkingHistoryCompatibilityMiddleware())

    return stack
```

#### 3.4 Agent 构造

```python
# === 旧版 ===
agent = Agent(
    llm=LLMGateway.from_env(max_tokens=...),
    tools=self._build_tool_registry(profile),
    default_system_prompt=...,
    default_max_steps=...,
    default_parallel_tool_calls=...,
    hooks=hooks,  # List[RuntimeHook]
)
agent.hooks.register(ThinkingHistoryCompatibilityHook())

# === 新版 ===
middleware_stack = self._build_middleware_stack(profile, llm)
agent = Agent(
    llm=llm,
    tools=self._build_tool_registry(profile),
    default_system_prompt=profile.system_prompt,
    default_max_steps=self.settings.agent_max_steps,
    default_parallel_tool_calls=self.settings.agent_parallel_tool_calls,
    middleware=middleware_stack,  # MiddlewareStack
)
```

#### 3.5 移除 _register_runtime_hooks 调用

```python
# === 旧版 ===
# _get_agent() 中多处调用 agent.hooks.register(...)

# === 新版 ===
# 所有中间件在 _build_middleware_stack() 中一次性构建
# Agent 构造时传入 middleware=stack
# 移除所有 agent.hooks.register() 调用
```

### 模块 2：approval_manager.py（~20 行改动）

#### 3.6 ApprovalProvider 接口适配

新版 `HitlMiddleware` 接收 `approval_provider: Callable[[ToolCall], Awaitable[bool]]`，而不是旧版的 `ApprovalProvider` 协议。

```python
# === 旧版 ===
from wuwei.runtime import ApprovalDecision, ApprovalRequest

class ApprovalManager:
    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        ...

# === 新版 ===
class ApprovalManager:
    async def request_approval_bool(self, tool_call) -> bool:
        """适配 HitlMiddleware 的 Callable[[ToolCall], Awaitable[bool]] 接口"""
        # 将 ToolCall 转换为内部审批流程
        approved = await self._request_approval(tool_call)
        return approved
```

需要新增一个 `request_approval_bool` 方法，将 `ToolCall` 转换为内部审批流程。

### 模块 3：session_storage.py（~10 行改动）

```python
# === 旧版 ===
from wuwei.agent.session import AgentSession
from wuwei.llm import Message

# === 新版（需确认路径是否变更）===
from wuwei.agent.session import AgentSession  # 可能不变
from wuwei.llm import Message  # 可能不变
```

`AgentSession` 和 `Message` 的路径需要验证。

### 模块 4：website_file_tools.py（~5 行改动）

```python
# === 旧版 ===
from wuwei.tools.builtin.file_tools import _collect_files, _resolve_workspace_path, _truncate_text, DEFAULT_READ_LIMIT

# === 新版（需验证）===
# 如果私有函数路径变更，需要重新导入或自行实现
```

## 四、新增功能集成建议

### 4.1 Parsers 模块

```python
from wuwei.parsers import JsonOutputParser, PydanticOutputParser

# 可用于结构化输出解析
parser = JsonOutputParser()
result = parser.parse(llm_response)
```

**建议**：在 `announcement_ai_service.py` 中使用 `JsonOutputParser` 替代手动 `json.loads()`。

### 4.2 Plugin 模块

```python
from wuwei.plugin import PluginLoader, PluginRegistry

# 可用于动态加载工具插件
registry = PluginRegistry()
loader = PluginLoader(registry)
loader.load_from_directory("plugins/")
```

**建议**：暂不集成，待需求明确后再使用。

### 4.3 Streaming 模块

```python
from wuwei.streaming import StreamMode, StreamChunk

# 可用于更精细的流式控制
```

**建议**：暂不集成，当前 SSE 流式输出已满足需求。

### 4.4 Multi-Agent (Swarm)

```python
from wuwei import Swarm, TeamMember, SubTask

# 可用于多 Agent 协作
swarm = Swarm(members=[...])
result = await swarm.run("complex task")
```

**建议**：暂不集成，作为未来功能储备。

## 五、依赖变更

```toml
# === pyproject.toml ===
dependencies = [
    "wuwei>=2.1.0",  # 升级
    # 新增依赖（wuwei 2.1 需要）
    "markitdown>=0.1.5",  # file_tools 需要
]
```

## 六、环境变量变更

| 变量 | 影响 |
|------|------|
| `OPENAI_API_KEY` | ✅ 不变 |
| `OPENAI_BASE_URL` | ✅ 不变 |
| `OPENAI_MODEL` | ✅ 不变 |

无需新增环境变量。

## 七、迁移执行顺序

```
Phase 1: 依赖更新（5 分钟）
  ├─ 1.1 更新 pyproject.toml: wuwei>=2.1.0, 新增 markitdown
  ├─ 1.2 uv lock --upgrade-package wuwei --index-url https://pypi.org/simple
  └─ 1.3 uv sync

Phase 2: 核心迁移（2-3 小时）
  ├─ 2.1 agent_service.py: import 变更
  ├─ 2.2 ThinkingHistoryCompatibilityHook → Middleware
  ├─ 2.3 _register_runtime_hooks → _build_middleware_stack
  ├─ 2.4 Agent(hooks=...) → Agent(middleware=...)
  └─ 2.5 approval_manager.py: 适配新接口

Phase 3: 兼容性验证（30 分钟）
  ├─ 3.1 session_storage.py: 验证 AgentSession/Message 路径
  ├─ 3.2 website_file_tools.py: 验证私有函数导入
  └─ 3.3 其余工具文件: 验证 ToolRegistry 兼容性

Phase 4: 测试（30 分钟）
  ├─ 4.1 uv run pytest 全部测试
  ├─ 4.2 手动测试各 Agent 模式
  └─ 4.3 验证 SSE 流式输出
```

## 八、回滚策略

由于是破坏性更新，建议：
1. 创建分支 `feat/wuwei-2.1-migration`
2. 分阶段提交：Phase 1 先合并，Phase 2 确认 API 后再合并
3. 保留旧版兼容层（可选）：在项目中创建 `wuwei_compat.py` 适配层
