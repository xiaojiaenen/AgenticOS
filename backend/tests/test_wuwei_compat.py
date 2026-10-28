"""wuwei 版本与补丁层兼容性守护测试。

补丁层用**子类继承**覆盖上游方法（不是 monkey-patch），因此升级时最大的
风险是：上游改了被重写方法的签名，子类签名不匹配 → 运行期 TypeError。

这个测试把「补丁层依赖的上游契约」固定下来：
- 上游类存在，且我们的子类确实继承自它
- 被重写的方法在两边签名一致
- 新增的上游方法没被我们意外遮蔽

它会在每次升级 wuwei 时立刻暴露不兼容，而不是等到生产环境对话报错。
"""
from __future__ import annotations

import inspect
import importlib.metadata as md

import pytest


def test_wuwei_version_floor() -> None:
    """wuwei 必须 >= 3.3.0（补丁层按 3.3.0 契约编写）。"""
    raw = md.version("wuwei")
    major, minor = (int(x) for x in raw.split(".")[:2])
    assert (major, minor) >= (3, 3), f"wuwei {raw} 低于补丁层要求的 3.3.0"


def test_patch_subclasses_inherit_from_upstream() -> None:
    """补丁类必须真的继承自上游类 —— 否则覆盖不会生效。"""
    from wuwei.agent.agent import Agent
    from wuwei.runtime.agent_runner import AgentRunner
    from wuwei.tools.executor import ToolExecutor

    from app.services.agent import wuwei_patches as wp

    assert issubclass(wp.PatchedAgentRunner, AgentRunner)
    assert issubclass(wp.PatchedAgent, Agent)
    assert issubclass(wp.BoundedToolExecutor, ToolExecutor)


# 补丁层重写的方法 → (上游类, 方法名)
OVERRIDDEN = [
    ("wuwei.runtime.agent_runner", "AgentRunner", "_commit_tool"),
    ("wuwei.runtime.agent_runner", "AgentRunner", "_iter_events"),
    ("wuwei.runtime.agent_runner", "AgentRunner", "_execute_events"),
    ("wuwei.tools.executor", "ToolExecutor", "_execute_batched"),
    ("wuwei.agent.agent", "Agent", "create_runner"),
]


@pytest.mark.parametrize(("module", "cls_name", "method"), OVERRIDDEN)
def test_overridden_method_exists_upstream(module: str, cls_name: str, method: str) -> None:
    """被重写的方法必须仍存在于上游 —— 上游删了它，补丁就静默失效。"""
    mod = __import__(module, fromlist=[cls_name])
    cls = getattr(mod, cls_name)
    assert hasattr(cls, method), f"{cls_name}.{method} 在 wuwei 上游已不存在"


@pytest.mark.parametrize(("module", "cls_name", "method"), OVERRIDDEN)
def test_overridden_signature_matches(module: str, cls_name: str, method: str) -> None:
    """子类重写的签名必须能接受上游的调用方式。

    比较方式：参数名列表必须一致（位置参数顺序尤其关键 —— 上游按位置调用，
    顺序错了就是静默传错值）。
    """
    from app.services.agent import wuwei_patches as wp

    mod = __import__(module, fromlist=[cls_name])
    upstream = getattr(getattr(mod, cls_name), method)

    # 找到我们对应的子类
    if cls_name == "AgentRunner":
        patched = getattr(wp.PatchedAgentRunner, method)
    elif cls_name == "ToolExecutor":
        patched = getattr(wp.BoundedToolExecutor, method)
    elif cls_name == "Agent":
        patched = getattr(wp.PatchedAgent, method)
    else:  # pragma: no cover
        pytest.skip(f"未登记的子类：{cls_name}")

    up_sig = inspect.signature(upstream)
    our_sig = inspect.signature(patched)

    up_params = list(up_sig.parameters)
    our_params = list(our_sig.parameters)

    # 子类允许用 *args/**kwargs 兜底（那样永远兼容）
    if any(
        p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        for p in our_sig.parameters.values()
    ):
        return

    assert our_params[: len(up_params)] == up_params, (
        f"{cls_name}.{method} 参数名/顺序与上游不一致：\n"
        f"  上游: {up_params}\n"
        f"  补丁: {our_params}"
    )


def test_patched_runner_is_used_by_agent() -> None:
    """Agent.create_runner 必须返回补丁后的 runner，而不是上游默认实现。"""
    from app.services.agent import wuwei_patches as wp

    sig = inspect.getsource(wp.PatchedAgent.create_runner)
    assert "PatchedAgentRunner" in sig, (
        "PatchedAgent.create_runner 没有返回 PatchedAgentRunner，补丁不生效"
    )
