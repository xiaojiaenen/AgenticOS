"""知识库冲突定期巡检（跨页面配对扫描）的测试。

编译期的冲突检测是「新页 vs 旧页」单向比对，两个都已存在的页面若从没在
同一次编译里相遇（历史导入、分次上传），矛盾会永久漏掉。本文件锁定巡检的
四条不变量：

1. 同主题且语义矛盾的既有页面**能被发现**并落成待裁决审核项；
2. 判定**双向都跑**（规则不对称：只查「新页含否定 / 旧页含肯定」会漏反方向）；
3. **幂等**：同一对页面已有待裁决项时不再重复建；
4. **不误伤**：标题不像、或正文不同主题的页面对不参与比对。

另外守护「巡检不改正文」这一条：扫描结束后页面内容必须逐字不变。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.security import create_access_token, hash_password
from app.db.models import (
    KBReviewItemModel,
    KBWikiPageModel,
    KnowledgeBaseModel,
    UserModel,
)
from app.db.session import create_db_session
from app.main import app
from app.services.knowledge.conflict_scanner import (
    _bigrams,
    _candidate_pairs,
    scan_knowledge_base,
)

client = TestClient(app)

# 两页讲同一件事、结论相反：一页禁止手工删除，一页要求必须手工删除
_PAGE_A = (
    "# 缓存清理规范\n\n"
    "缓存过期后禁止手工删除缓存数据。必须先确认备份完整性，再等待自动淘汰。\n"
    "运维人员不得绕过自动过期机制直接清理缓存。\n"
)
_PAGE_B = (
    "# 缓存清理规范说明\n\n"
    "缓存过期后必须手工删除缓存数据。并且需要先确认备份完整性，再执行清理步骤。\n"
    "运维人员应当直接清理缓存以释放内存。\n"
)
# 标题相似但讲的是完全另一件事（用于验证正文重叠闸门）
_PAGE_C = (
    "# 缓存清理规范（归档废弃稿）\n\n"
    "本页记录 2019 年已下线的 Memcached 集群迁移过程。当时使用了完全不同的部署拓扑，"
    "搬迁批次按机房划分，涉及物理机柜编号与交换机端口对照表，与现行方案无任何关系。\n"
)


@pytest.fixture
def scan_env():
    suffix = uuid4().hex[:8]
    with create_db_session() as db:
        owner = UserModel(
            email=f"scan-owner-{suffix}@test.local",
            name="scan-owner",
            password_hash=hash_password("pw-123456"),
            role="admin",
        )
        db.add(owner)
        db.flush()

        kb = KnowledgeBaseModel(
            name="冲突巡检测试库",
            slug=f"kb-scan-{suffix}",
            description="",
            owner_id=owner.id,
            visibility="private",
            scope="personal",
        )
        db.add(kb)
        db.flush()

        pages = [
            KBWikiPageModel(
                knowledge_base_id=kb.id,
                title="缓存清理规范",
                slug=f"scan-a-{suffix}",
                page_type="concept",
                content=_PAGE_A,
                frontmatter_json="{}",
                sources_json="[]",
                conflicts_json="[]",
                authority_level="L1",
                is_active=True,
            ),
            KBWikiPageModel(
                knowledge_base_id=kb.id,
                title="缓存清理规范说明",
                slug=f"scan-b-{suffix}",
                page_type="concept",
                content=_PAGE_B,
                frontmatter_json="{}",
                sources_json="[]",
                conflicts_json="[]",
                authority_level="L1",
                is_active=True,
            ),
            KBWikiPageModel(
                knowledge_base_id=kb.id,
                title="缓存清理规范（归档废弃稿）",
                slug=f"scan-c-{suffix}",
                page_type="concept",
                content=_PAGE_C,
                frontmatter_json="{}",
                sources_json="[]",
                conflicts_json="[]",
                authority_level="L1",
                is_active=True,
            ),
        ]
        db.add_all(pages)
        db.flush()

        env = {
            "kb_id": kb.id,
            "owner_id": owner.id,
            "owner_email": owner.email,
            "owner_role": owner.role,
            "page_ids": [p.id for p in pages],
        }
        # 必须提交：fixture 用的是独立会话，巡检在另一个会话里读
        db.commit()
    yield env

    with create_db_session() as db:
        db.execute(delete(KBReviewItemModel).where(KBReviewItemModel.knowledge_base_id == env["kb_id"]))
        db.execute(delete(KBWikiPageModel).where(KBWikiPageModel.knowledge_base_id == env["kb_id"]))
        db.execute(delete(KnowledgeBaseModel).where(KnowledgeBaseModel.id == env["kb_id"]))
        db.execute(delete(UserModel).where(UserModel.id == env["owner_id"]))
        db.commit()


def _pending_conflicts(db, kb_id: int) -> list[KBReviewItemModel]:
    return (
        db.query(KBReviewItemModel)
        .filter(
            KBReviewItemModel.knowledge_base_id == kb_id,
            KBReviewItemModel.review_type == "conflict_resolution",
            KBReviewItemModel.status == "pending",
        )
        .all()
    )


# ---------------------------------------------------------------------------
# 核心：能发现、能双向、能幂等、不误伤
# ---------------------------------------------------------------------------


def test_scan_finds_contradiction_between_existing_pages(scan_env):
    """两个都已存在的矛盾页面（从未在同一次编译相遇）必须被发现。"""
    with create_db_session() as db:
        stats = scan_knowledge_base(db, scan_env["kb_id"])
        db.commit()

        assert stats["pages_scanned"] == 3
        assert stats["created"] == 1, f"应发现 1 处矛盾，实际 {stats}"
        assert stats["conflicts_found"] == 1

        items = _pending_conflicts(db, scan_env["kb_id"])
        assert len(items) == 1
        item = items[0]
        assert item.title.startswith("内容冲突")
        # 两页都记进关联，前端才能跳转对照
        related = item.related_page_ids_json
        assert str(scan_env["page_ids"][0]) in related
        assert str(scan_env["page_ids"][1]) in related
        # 明确标注来源，便于区分编译期产出与巡检产出
        assert "定期巡检" in item.description


def test_scan_detects_reverse_direction(scan_env):
    """规则不对称：把矛盾双方对调后仍须命中（只跑单向会漏）。"""
    with create_db_session() as db:
        # 只保留 A 与 B 两页，改造成「A 是肯定、B 是否定」的反向组合
        page_a = db.get(KBWikiPageModel, scan_env["page_ids"][0])
        page_a.content = _PAGE_B  # 肯定表述
        page_b = db.get(KBWikiPageModel, scan_env["page_ids"][1])
        page_b.content = _PAGE_A  # 否定表述
        db.commit()

        stats = scan_knowledge_base(db, scan_env["kb_id"])
        db.commit()

    assert stats["created"] == 1, f"反向组合也应命中，实际 {stats}"


def test_scan_is_idempotent(scan_env):
    """重复巡检不得把复核队列刷重复（cron 每周跑，必须幂等）。"""
    with create_db_session() as db:
        first = scan_knowledge_base(db, scan_env["kb_id"])
        db.commit()
        second = scan_knowledge_base(db, scan_env["kb_id"])
        db.commit()

        assert first["created"] == 1
        assert second["created"] == 0
        assert second["skipped_existing"] >= 1
        assert len(_pending_conflicts(db, scan_env["kb_id"])) == 1


def test_scan_skips_pages_without_content_overlap(scan_env):
    """标题像、正文毫不相干（归档废弃稿）不能算冲突。"""
    with create_db_session() as db:
        c_id = scan_env["page_ids"][2]
        pairs = _candidate_pairs(
            [
                {"id": scan_env["page_ids"][0], "title": "缓存清理规范", "page_type": "concept", "content": _PAGE_A},
                {"id": c_id, "title": "缓存清理规范（归档废弃稿）", "page_type": "concept", "content": _PAGE_C},
            ]
        )
        # 标题确实像 → 进入候选
        assert pairs == [(0, 1)]

        stats = scan_knowledge_base(db, scan_env["kb_id"])
        db.commit()
        # A/C 正文重叠过低，只有 A/B 一对通过闸门
        assert stats["pairs_checked"] == 1
        assert stats["created"] == 1


def test_scan_does_not_touch_page_content(scan_env):
    """巡检只写复核队列，绝不改正文（这是可以放心放 cron 的前提）。"""
    with create_db_session() as db:
        before = {p.id: p.content for p in db.query(KBWikiPageModel).all()}
        scan_knowledge_base(db, scan_env["kb_id"])
        db.commit()
        after = {p.id: p.content for p in db.query(KBWikiPageModel).all()}

    assert before == after


def test_scan_single_page_kb_is_noop(scan_env):
    with create_db_session() as db:
        db.query(KBWikiPageModel).filter(
            KBWikiPageModel.knowledge_base_id == scan_env["kb_id"]
        ).delete()
        db.commit()
        stats = scan_knowledge_base(db, scan_env["kb_id"])
    assert stats["pages_scanned"] == 0
    assert stats["created"] == 0


# ---------------------------------------------------------------------------
# 候选生成的中文正确性（旧 Jaccard 用空格分词，中文标题永远只有 0 或 1）
# ---------------------------------------------------------------------------


def test_bigrams_and_candidates_work_for_chinese_titles():
    assert _bigrams("Redis 缓存") == _bigrams("redis缓存")
    assert _bigrams("") == set()

    pages = [
        {"id": 1, "title": "备份与恢复规范", "page_type": "concept", "content": ""},
        {"id": 2, "title": "备份与恢复规范说明", "page_type": "concept", "content": ""},
        {"id": 3, "title": "前端构建流程", "page_type": "concept", "content": ""},
    ]
    pairs = _candidate_pairs(pages)
    assert pairs == [(0, 1)], "只有前两页标题相似，第三页不该进候选"


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


def test_scan_endpoint_requires_write_permission_and_returns_stats(scan_env):
    from app.core.config import get_settings

    settings = get_settings()
    token = create_access_token(
        {
            "sub": str(scan_env["owner_id"]),
            "email": scan_env["owner_email"],
            "role": scan_env["owner_role"],
        },
        secret=settings.auth_secret_key,
        expires_in_seconds=settings.auth_token_expire_minutes * 60,
    )
    resp = client.post(
        f"/api/v1/knowledge/bases/{scan_env['kb_id']}/conflicts/scan",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["knowledge_base_id"] == scan_env["kb_id"]
    assert body["created"] == 1
    assert "pages_scanned" in body


def test_scan_endpoint_rejects_anonymous(scan_env):
    resp = client.post(f"/api/v1/knowledge/bases/{scan_env['kb_id']}/conflicts/scan")
    assert resp.status_code in (401, 403)
