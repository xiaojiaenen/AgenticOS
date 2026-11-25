"""TECH-DEBT-2026-09：agent 服务包拆分后新模块的直接单测。

覆盖：
- factory：中间件栈构建 / 工具注册表构建 / 并发补丁应用
- artifacts：项目 slug 推断（WEBSITES_DIR 注入临时目录）
- prompts：资源文件目录注入文案渲染
- service 门面：公共 API re-export 完整性
- session_storage：save_session_meta 单事务合并
"""



from app.core.config import get_settings
from app.services.agent_profile_service import RuntimeAgentProfile


def _make_profile(**overrides) -> RuntimeAgentProfile:
    defaults = dict(
        profile_id=None,
        name="general",
        slug="general",
        response_mode="general",
        system_prompt="test",
        builtin_tools=("calc", "time"),
        approval_tools=(),
        signature="",
        skills=(),
    )
    defaults.update(overrides)
    return RuntimeAgentProfile(**defaults)


class TestAgentFactoryMiddlewareStack:
    """factory.py：中间件栈构建。"""

    def _make_factory(self):
        from app.services.agent.factory import AgentFactory
        from app.services.approval_manager import ApprovalManager
        from cachetools import TTLCache

        class _FactoryHarness(AgentFactory):
            def __init__(self) -> None:
                # model_copy：避免污染全局 lru_cache 的共享 Settings 单例
                self.settings = get_settings().model_copy()
                self.approval_manager = ApprovalManager(timeout_seconds=1)
                self._agents = TTLCache(maxsize=2, ttl=60)

        return _FactoryHarness()

    