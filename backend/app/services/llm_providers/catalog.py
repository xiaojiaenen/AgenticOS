"""提供商模型目录的读写。

目录的唯一用途是让「模型名」从一个要背的字符串，变成可选、可校验、可分组
的列表。上游给的元数据（taskType / maxTokens / 推荐采样参数）一并存下来，
因为界面上「这个模型适不适合做深度思考」这种判断只能靠它。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import LlmModelCatalogModel

logger = logging.getLogger("agenticos.llm.catalog")


def list_models(db: Session, provider_id: int) -> list[LlmModelCatalogModel]:
    return list(
        db.scalars(
            select(LlmModelCatalogModel)
            .where(LlmModelCatalogModel.provider_id == provider_id)
            .order_by(
                LlmModelCatalogModel.task_type,
                LlmModelCatalogModel.model_key,
            )
        ).all()
    )


def to_dict(row: LlmModelCatalogModel) -> dict[str, Any]:
    try:
        extra = json.loads(row.extra_json or "{}")
    except (TypeError, json.JSONDecodeError):
        extra = {}
    return {
        "id": row.id,
        "provider_id": row.provider_id,
        "model_key": row.model_key,
        "model_name": row.model_name,
        "task_type": row.task_type,
        "max_tokens": row.max_tokens,
        "extra": extra,
        "enabled": bool(row.enabled),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def upsert_models(
    db: Session, provider_id: int, items: list[dict[str, Any]]
) -> tuple[int, int]:
    """按 ``model_key`` 合并。

    返回 ``(新增数, 更新数)``。重复发现是常态（每次点「同步」都跑一次），
    所以必须是幂等的 —— 直接 delete + insert 会让模型 id 变化，进而让
    ``roles`` 里已经绑定的名字失去关联（虽然按 name 绑定其实不受影响，
    但界面上正在编辑的行会被刷掉）。
    """
    existing = {
        row.model_key: row
        for row in db.scalars(
            select(LlmModelCatalogModel).where(LlmModelCatalogModel.provider_id == provider_id)
        ).all()
    }

    added = 0
    updated = 0
    for item in items:
        key = str(item.get("model_key") or "").strip()
        name = str(item.get("model_name") or "").strip() or key
        if not key:
            continue
        row = existing.get(key)
        if row is None:
            row = LlmModelCatalogModel(
                provider_id=provider_id,
                model_key=key,
                model_name=name,
                task_type=str(item.get("task_type") or ""),
                max_tokens=item.get("max_tokens"),
                extra_json=json.dumps(item.get("extra") or {}, ensure_ascii=False),
                enabled=True,
            )
            db.add(row)
            existing[key] = row
            added += 1
        else:
            row.model_name = name
            row.task_type = str(item.get("task_type") or row.task_type or "")
            if item.get("max_tokens") is not None:
                row.max_tokens = item.get("max_tokens")
            if item.get("extra"):
                row.extra_json = json.dumps(item["extra"], ensure_ascii=False)
            updated += 1

    db.flush()
    return added, updated


def delete_model(db: Session, provider_id: int, model_id: int) -> bool:
    row = db.get(LlmModelCatalogModel, model_id)
    if row is None or row.provider_id != provider_id:
        return False
    db.delete(row)
    db.flush()
    return True


def clear_models(db: Session, provider_id: int) -> int:
    result = db.execute(
        delete(LlmModelCatalogModel).where(LlmModelCatalogModel.provider_id == provider_id)
    )
    db.flush()
    return int(result.rowcount or 0)


def model_names(db: Session, provider_id: int) -> set[str]:
    return {
        row.model_name
        for row in db.scalars(
            select(LlmModelCatalogModel).where(LlmModelCatalogModel.provider_id == provider_id)
        ).all()
    }
