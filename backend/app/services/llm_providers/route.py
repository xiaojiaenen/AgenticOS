"""把「这次请求实际走了哪条路由」从网关对象上读出来。

## 为什么需要这个模块

token 记账有两个完全不同的维度，混在一起会让统计口径失真：

- **用量归属**：谁发起的这次对话。这是**唯一**的统计口径 —— 按用户、按会话
  聚合出来的 token 数才是「这个人用了多少」。
- **路由标签**：这次请求实际打到了哪个提供商、哪条凭据、哪个模型。这是**审计**
  维度 —— 排查「某个号挂了」「切换提供商没生效」「模型名落库不对」时才需要。

凭据是系统级共享池（见 ``credentials`` 模块），上游看到的身份由池里选中那条
决定，与会话发起人无关。所以**绝不能**把 token 算到凭据头上再去回推用户：
一个号被十个用户共用，按号统计出来的数字对谁都不成立。

本模块只负责「读出快照」，不参与任何归属决策。归属由调用方（orchestrator）
按发起请求的 ``user.id`` 决定。

## 为什么从网关对象上读，而不是从配置重新解析

管理员随时可能切换提供商或改用途绑定，重新解析拿到的是「现在的配置」，
而这次请求发出时用的是「当时的配置」—— 两者在切换瞬间会不一致，落库的
模型名就会张冠李戴。网关对象是构建时定下来的，它身上的标签才代表**实际
发出的那次请求**。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RouteSnapshot:
    """一次请求的实际路由。全部字段可为空 —— 环境变量兜底路径没有 provider 记录。"""

    provider_id: int | None = None
    provider_slug: str | None = None
    provider_name: str | None = None
    model: str | None = None
    # 只有企业 Cookie 型提供商才有凭据；API Key 型恒为 None
    credential_id: int | None = None
    account_label: str | None = None

    @property
    def is_empty(self) -> bool:
        return not any(
            (self.provider_id, self.provider_slug, self.model, self.credential_id)
        )

    def audit_fields(self) -> dict[str, Any]:
        """落库用的字段集合（列名与 ``AgentUsageEventModel`` 对齐）。"""
        return {
            "provider_id": self.provider_id,
            "provider_slug": self.provider_slug,
            "provider_name": self.provider_name,
            "credential_id": self.credential_id,
            "account_label": self.account_label,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


#: 挂在网关对象上的属性前缀。刻意用 ``_agenticos_`` 前缀，避免与上游私有属性撞名。
_ATTR = "_agenticos_route"
#: 旧埋点（v1）单独挂的两个属性，保留读取以兼容未重启的进程与既有测试。
_LEGACY_CREDENTIAL_ATTR = "_agenticos_credential_id"
_LEGACY_LABEL_ATTR = "_agenticos_account_label"


def attach_route(
    gateway: Any,
    *,
    provider_id: int | None,
    provider_slug: str | None,
    provider_name: str | None,
    model: str | None,
    credential_id: int | None = None,
    account_label: str | None = None,
) -> RouteSnapshot:
    """把路由快照挂到网关对象上，供后续记账读取。

    同时写回旧的两个属性：外部（含既有测试）有按 ``_agenticos_credential_id``
    读取的调用点，一次性删掉会静默变成 ``None``。
    """
    snapshot = RouteSnapshot(
        provider_id=provider_id,
        provider_slug=provider_slug,
        provider_name=provider_name,
        model=model,
        credential_id=credential_id,
        account_label=account_label,
    )
    try:
        setattr(gateway, _ATTR, snapshot)
        setattr(gateway, _LEGACY_CREDENTIAL_ATTR, credential_id)
        setattr(gateway, _LEGACY_LABEL_ATTR, account_label)
    except AttributeError:
        # 极端情况下网关是只读对象（__slots__），记账时退回「无路由信息」
        # 而不是把请求打死 —— 审计缺失不能影响主链路。
        pass
    return snapshot


def describe_route(target: Any) -> RouteSnapshot:
    """从 ``Agent`` 或 ``LLMGateway`` 读出路由快照。

    传错对象（比如 ``None``）返回空快照，不抛异常：调用点在记账路径上，
    审计信息缺失不该让一次已经成功的对话失败。
    """
    llm = getattr(target, "llm", None) or target
    snapshot = getattr(llm, _ATTR, None)
    if isinstance(snapshot, RouteSnapshot):
        return snapshot

    # 兼容旧埋点：只有凭据，没有提供商与模型
    credential_id = getattr(llm, _LEGACY_CREDENTIAL_ATTR, None)
    account_label = getattr(llm, _LEGACY_LABEL_ATTR, None)
    if credential_id is None and account_label is None:
        return RouteSnapshot()
    return RouteSnapshot(
        credential_id=credential_id,
        account_label=account_label,
    )


def resolve_model_name(target: Any, fallback: str | None = None) -> str | None:
    """取「这次请求实际用的模型名」，取不到才用调用方给的兜底值。"""
    snapshot = describe_route(target)
    if snapshot.model:
        return snapshot.model
    llm = getattr(target, "llm", None) or target
    adapter = getattr(llm, "adapter", None)
    model = getattr(adapter, "model", None)
    if isinstance(model, str) and model.strip():
        return model.strip()
    return fallback
