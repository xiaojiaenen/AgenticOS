"""从 AI 提供商配置里解析 embedding / image 模型。

为什么要这层：配置散在三处 —— 全局 env（KNOWLEDGE_EMBEDDING_*）、
provider 的 roles、本地模型。用户在「AI 提供商」页面配了 embedding 角色，
就应该直接生效，而不是还要去改环境变量重启。

解析优先级（高 → 低）：

1. **本地模型**（``KNOWLEDGE_EMBEDDING_LOCAL_MODEL``）：显式配了就完全
   不走网络，最高优先级 —— 内网部署不能被 provider 配置意外覆盖。
2. **provider 的 embedding 角色**：管理员在页面上绑定的，可热改。
3. **全局 env**（``KNOWLEDGE_EMBEDDING_*``）：兼容老部署。
4. 都没有 → 返回 None，检索降级到 BM25。

provider 只提供「端点 + Key + 模型名」，维度仍由配置决定 —— 维度是
向量库的物理约束，不该让管理员随手改出不一致。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger("knowledge.embedder.resolve")


@dataclass(frozen=True)
class EmbeddingEndpoint:
    """解析出的向量化端点。"""

    base_url: str
    api_key: str
    model: str
    dimensions: int
    source: str  # local / provider:<slug> / env

    def describe(self) -> dict[str, Any]:
        """不含密钥的描述，可安全返回前端。"""
        return {
            "source": self.source,
            "base_url": self.base_url,
            "model": self.model,
            "dimensions": self.dimensions,
            "has_api_key": bool(self.api_key),
        }


def resolve_embedding_endpoint(db: Session | None = None) -> EmbeddingEndpoint | None:
    """按优先级解析向量化端点。任何一步失败都不抛异常，只往下降级。"""
    from app.core.config import get_settings
    from app.services.llm_providers.presets import ROLE_EMBEDDING

    settings = get_settings()

    # 1) 本地模型：配了就完全离线
    local_model = (settings.knowledge_embedding_local_model or "").strip()
    if local_model:
        dims = settings.knowledge_embedding_local_dimensions or settings.knowledge_embedding_dimensions
        return EmbeddingEndpoint(
            base_url="",
            api_key="",
            model=local_model,
            dimensions=dims,
            source="local",
        )

    # 2) provider 的 embedding 角色
    if db is not None:
        try:
            from app.db.models import LlmProviderModel
            from app.services.llm_providers import spec as provider_spec

            rows = list(
                db.execute(
                    select(LlmProviderModel)
                    .where(LlmProviderModel.enabled.is_(True))
                    .order_by(LlmProviderModel.is_default.desc(), LlmProviderModel.id.asc())
                ).scalars()
            )
            for row in rows:
                try:
                    resolved = provider_spec.spec_from_row(row)
                except Exception:  # noqa: BLE001 —— 单个 provider 坏不影响其他
                    logger.warning(
                        "provider %s 解析失败，跳过（该 provider 的角色不会生效）",
                        getattr(row, "slug", "?"),
                        exc_info=True,
                    )
                    continue
                extra = resolved.extra if isinstance(resolved.extra, dict) else {}
                roles = extra.get("roles") if isinstance(extra.get("roles"), dict) else {}
                model_name = str(roles.get(ROLE_EMBEDDING) or "").strip()
                if not model_name:
                    continue
                # 企业 Cookie 网关通常没有 /embeddings，跳过避免必然失败
                if resolved.provider_type == "enterprise_cookie":
                    logger.debug(
                        "provider %s 绑了 embedding 角色但类型是 enterprise_cookie，跳过",
                        resolved.slug,
                    )
                    continue
                return EmbeddingEndpoint(
                    base_url=(resolved.base_url or "").rstrip("/"),
                    api_key=resolved.api_key or "",
                    model=model_name,
                    dimensions=settings.knowledge_embedding_dimensions,
                    source=f"provider:{resolved.slug}",
                )
        except Exception:  # noqa: BLE001
            logger.warning("从 provider 解析 embedding 失败，回退到 env", exc_info=True)

    # 3) 全局 env
    api_key = (settings.knowledge_embedding_api_key or settings.openai_api_key or "").strip()
    if not api_key:
        return None
    base_url = (
        settings.knowledge_embedding_base_url or settings.openai_base_url or "https://api.openai.com/v1"
    ).rstrip("/")
    return EmbeddingEndpoint(
        base_url=base_url,
        api_key=api_key,
        model=settings.knowledge_embedding_model,
        dimensions=settings.knowledge_embedding_dimensions,
        source="env",
    )


def resolve_image_endpoint(db: Session | None = None) -> EmbeddingEndpoint | None:
    """解析生图端点（结构复用，语义不同）。

    生图没有「维度」概念，``dimensions`` 恒为 0。返回 None 表示未配置 ——
    调用方据此提示「请先在 AI 提供商页面绑定生图模型」，而不是抛错。
    """
    from app.services.llm_providers.presets import ROLE_IMAGE

    if db is None:
        return None
    try:
        from app.db.models import LlmProviderModel
        from app.services.llm_providers import spec as provider_spec

        rows = list(
            db.execute(
                select(LlmProviderModel)
                .where(LlmProviderModel.enabled.is_(True))
                .order_by(LlmProviderModel.is_default.desc(), LlmProviderModel.id.asc())
            ).scalars()
        )
        for row in rows:
            try:
                resolved = provider_spec.spec_from_row(row)
            except Exception:  # noqa: BLE001
                continue
            extra = resolved.extra if isinstance(resolved.extra, dict) else {}
            roles = extra.get("roles") if isinstance(extra.get("roles"), dict) else {}
            model_name = str(roles.get(ROLE_IMAGE) or "").strip()
            if not model_name:
                continue
            if resolved.provider_type == "enterprise_cookie":
                continue
            return EmbeddingEndpoint(
                base_url=(resolved.base_url or "").rstrip("/"),
                api_key=resolved.api_key or "",
                model=model_name,
                dimensions=0,
                source=f"provider:{resolved.slug}",
            )
    except Exception:  # noqa: BLE001
        logger.warning("解析生图端点失败", exc_info=True)
    return None
