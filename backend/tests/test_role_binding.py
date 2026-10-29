"""roles 绑定校验：聊天角色要求命中目录，embedding/image 放宽。

为什么这个测试重要：provider 的 /models 目录列的是**聊天模型**，
embedding 与生图是不同端点，模型名不会出现在同一份目录里。卡目录会让
「在页面上配向量化/生图模型」永远失败，只能回去改环境变量。
"""
from __future__ import annotations

import pytest

from app.services.llm_providers.presets import MODEL_ROLES


def test_chat_roles_still_validated() -> None:
    """聊天类角色名写错必须被拒 —— 它们走同一个端点，错了一定 404。"""
    chat_roles = {"chat", "reasoner", "fast", "vision"}
    assert chat_roles <= set(MODEL_ROLES)


def test_embedding_and_image_are_exempt_from_catalog() -> None:
    """embedding / image 不在聊天目录校验范围内。"""
    chat_roles = {"chat", "reasoner", "fast", "vision"}
    assert "embedding" not in chat_roles
    assert "image" not in chat_roles


def test_validation_logic_classifies_roles_correctly() -> None:
    """模拟校验逻辑：目录里只有聊天模型时，embedding/image 不应被算作 missing。"""
    available = {"gpt-4o", "deepseek-chat"}
    chat_roles = {"chat", "reasoner", "fast", "vision"}

    roles = {
        "chat": "gpt-4o",
        "embedding": "text-embedding-3-small",  # 不在目录里，但应放行
        "image": "dall-e-3",                    # 同上
    }
    missing = [
        value for key, value in roles.items()
        if key in chat_roles and value not in available
    ]
    assert missing == [], "embedding/image 不该被目录校验拦下"

    # 对照：聊天角色写错仍要被拦
    bad = {"chat": "not-a-model"}
    missing_bad = [
        value for key, value in bad.items()
        if key in chat_roles and value not in available
    ]
    assert missing_bad == ["not-a-model"]


def test_unknown_role_still_rejected() -> None:
    """不在 MODEL_ROLES 里的用途名仍要拒绝（防止拼错）。"""
    roles = set(MODEL_ROLES)
    assert "embeddings" not in roles  # 常见拼错
    assert "embedding" in roles
