"""反馈广场服务（GitHub-Issue 式，仅登录用户可见）。

设计要点：
- 默认 public 全员可见；private 仅提交者 + 管理员可见（列表/详情都过滤）。
- 投票一人一帖一票（唯一约束），vote_count 反规范化便于排序。
- 状态流转 open→confirmed→in_progress→resolved→shipped→closed，
  每次变更自动写一条 is_system 评论，形成公开时间线。
- 统计看板给管理员/领导看成果：本周新增/解决、平均解决时长、解决率。
"""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.timezone import app_now
from app.db.models import (
    FeedbackCommentModel,
    FeedbackIssueModel,
    FeedbackVoteModel,
    UserModel,
)
from app.db.session import create_db_session
from app.schemas.feedback import (
    FeedbackCommentCreateRequest,
    FeedbackCreateRequest,
    FeedbackStatusUpdateRequest,
)

# 状态机：允许的直接迁移（管理员可跨级，但记录系统评论）
_TERMINAL = {"resolved", "shipped", "closed"}
_STATUS_LABEL = {
    "open": "待处理",
    "confirmed": "已确认",
    "in_progress": "处理中",
    "resolved": "已解决",
    "shipped": "已上线",
    "closed": "已关闭",
}


class FeedbackService:
    def __init__(self, session_factory: Callable[[], Session] = create_db_session) -> None:
        self.session_factory = session_factory

    # ── 序列化 ──────────────────────────────────────────────
    @staticmethod
    def _author(user: UserModel | None) -> dict | None:
        if user is None:
            return None
        return {"id": user.id, "name": user.name, "role": user.role}

    def _serialize_issue(
        self, db: Session, row: FeedbackIssueModel, viewer_id: int, my_votes: set[int]
    ) -> dict:
        author = db.get(UserModel, row.user_id)
        resolver = db.get(UserModel, row.resolved_by) if row.resolved_by else None
        try:
            context = json.loads(row.context_json or "{}")
        except (TypeError, ValueError):
            context = {}
        return {
            "id": row.id,
            "type": row.type,
            "title": row.title,
            "body": row.body,
            "status": row.status,
            "priority": row.priority,
            "visibility": row.visibility,
            "author": self._author(author),
            "vote_count": row.vote_count,
            "comment_count": row.comment_count,
            "my_vote": row.id in my_votes,
            "context": context,
            "resolution_note": row.resolution_note,
            "shipped_version": row.shipped_version,
            "resolved_by": self._author(resolver),
            "resolved_at": row.resolved_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def _visible_filter(self, viewer: UserModel):
        """public 全员可见；private 仅本人或管理员。"""
        if viewer.role == "admin":
            return None
        return or_(
            FeedbackIssueModel.visibility == "public",
            FeedbackIssueModel.user_id == viewer.id,
        )

    def _my_vote_ids(self, db: Session, viewer_id: int, issue_ids: list[int]) -> set[int]:
        if not issue_ids:
            return set()
        rows = db.scalars(
            select(FeedbackVoteModel.issue_id).where(
                FeedbackVoteModel.user_id == viewer_id,
                FeedbackVoteModel.issue_id.in_(issue_ids),
            )
        ).all()
        return set(rows)

    # ── 列表 ────────────────────────────────────────────────
    def list_issues(
        self,
        viewer: UserModel,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        type_: str | None = None,
        search: str | None = None,
        sort: str = "votes",
        mine: bool = False,
    ) -> dict:
        with self.session_factory() as db:
            stmt = select(FeedbackIssueModel)
            vis = self._visible_filter(viewer)
            if vis is not None:
                stmt = stmt.where(vis)
            if mine:
                stmt = stmt.where(FeedbackIssueModel.user_id == viewer.id)
            if status:
                stmt = stmt.where(FeedbackIssueModel.status == status)
            if type_:
                stmt = stmt.where(FeedbackIssueModel.type == type_)
            if search:
                like = f"%{search.strip()}%"
                stmt = stmt.where(
                    or_(FeedbackIssueModel.title.like(like), FeedbackIssueModel.body.like(like))
                )
            total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

            if sort == "newest":
                stmt = stmt.order_by(FeedbackIssueModel.created_at.desc(), FeedbackIssueModel.id.desc())
            elif sort == "active":
                stmt = stmt.order_by(FeedbackIssueModel.updated_at.desc(), FeedbackIssueModel.id.desc())
            else:  # votes
                stmt = stmt.order_by(
                    FeedbackIssueModel.vote_count.desc(),
                    FeedbackIssueModel.created_at.desc(),
                    FeedbackIssueModel.id.desc(),
                )
            rows = db.scalars(
                stmt.offset((page - 1) * page_size).limit(page_size)
            ).all()
            my_votes = self._my_vote_ids(db, viewer.id, [r.id for r in rows])
            items = [self._serialize_issue(db, r, viewer.id, my_votes) for r in rows]
            return {"items": items, "total": int(total), "page": page, "page_size": page_size}

    # ── 详情 ────────────────────────────────────────────────
    def get_issue(self, issue_id: int, viewer: UserModel) -> dict | None:
        with self.session_factory() as db:
            row = db.get(FeedbackIssueModel, issue_id)
            if row is None:
                return None
            if row.visibility == "private" and viewer.role != "admin" and row.user_id != viewer.id:
                return None
            my_votes = self._my_vote_ids(db, viewer.id, [row.id])
            issue = self._serialize_issue(db, row, viewer.id, my_votes)
            comments = db.scalars(
                select(FeedbackCommentModel)
                .where(FeedbackCommentModel.issue_id == issue_id)
                .order_by(FeedbackCommentModel.created_at.asc(), FeedbackCommentModel.id.asc())
            ).all()
            comment_items = []
            for c in comments:
                comment_items.append({
                    "id": c.id,
                    "issue_id": c.issue_id,
                    "author": self._author(db.get(UserModel, c.user_id)) if c.user_id else None,
                    "body": c.body,
                    "is_official": c.is_official,
                    "is_system": c.is_system,
                    "created_at": c.created_at,
                })
            return {"issue": issue, "comments": comment_items}

    # ── 创建 ────────────────────────────────────────────────
    def create_issue(self, req: FeedbackCreateRequest, author: UserModel) -> dict:
        with self.session_factory() as db:
            # 上下文脱敏：只保留白名单字段，避免前端塞入敏感数据
            allowed = {"page", "session_id", "mode", "model", "trace_id", "user_agent"}
            context = {k: str(v)[:500] for k, v in (req.context or {}).items() if k in allowed and v}
            row = FeedbackIssueModel(
                user_id=author.id,
                type=req.type,
                title=req.title,
                body=req.body,
                visibility=req.visibility,
                context_json=json.dumps(context, ensure_ascii=False),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._serialize_issue(db, row, author.id, set())

    # ── 投票 ────────────────────────────────────────────────
    def toggle_vote(self, issue_id: int, viewer: UserModel) -> dict:
        with self.session_factory() as db:
            row = db.get(FeedbackIssueModel, issue_id)
            if row is None:
                raise LookupError("反馈不存在")
            if row.visibility == "private" and viewer.role != "admin" and row.user_id != viewer.id:
                raise PermissionError("无权操作该反馈")
            existing = db.scalar(
                select(FeedbackVoteModel).where(
                    FeedbackVoteModel.issue_id == issue_id,
                    FeedbackVoteModel.user_id == viewer.id,
                )
            )
            if existing:
                db.delete(existing)
                row.vote_count = max(0, row.vote_count - 1)
                voted = False
            else:
                db.add(FeedbackVoteModel(issue_id=issue_id, user_id=viewer.id))
                row.vote_count += 1
                voted = True
            db.commit()
            return {"voted": voted, "vote_count": row.vote_count}

    # ── 评论 ────────────────────────────────────────────────
    def add_comment(
        self, issue_id: int, req: FeedbackCommentCreateRequest, author: UserModel, *, official: bool = False
    ) -> dict:
        with self.session_factory() as db:
            row = db.get(FeedbackIssueModel, issue_id)
            if row is None:
                raise LookupError("反馈不存在")
            if row.visibility == "private" and author.role != "admin" and row.user_id != author.id:
                raise PermissionError("无权评论该反馈")
            comment = FeedbackCommentModel(
                issue_id=issue_id,
                user_id=author.id,
                body=req.body,
                is_official=official and author.role == "admin",
            )
            db.add(comment)
            row.comment_count += 1
            row.updated_at = app_now()
            db.commit()
            db.refresh(comment)
            return {
                "id": comment.id,
                "issue_id": issue_id,
                "author": self._author(author),
                "body": comment.body,
                "is_official": comment.is_official,
                "is_system": False,
                "created_at": comment.created_at,
            }

    # ── 管理员状态流转 ──────────────────────────────────────
    def update_status(
        self, issue_id: int, req: FeedbackStatusUpdateRequest, admin: UserModel
    ) -> dict:
        with self.session_factory() as db:
            row = db.get(FeedbackIssueModel, issue_id)
            if row is None:
                raise LookupError("反馈不存在")
            old = row.status
            row.status = req.status
            if req.priority:
                row.priority = req.priority
            if req.resolution_note is not None:
                row.resolution_note = req.resolution_note
            if req.shipped_version is not None:
                row.shipped_version = req.shipped_version
            if req.status in _TERMINAL and row.resolved_at is None:
                row.resolved_at = app_now()
                row.resolved_by = admin.id
            row.updated_at = app_now()
            # 系统评论：公开记录状态变更，形成时间线
            if old != req.status:
                label_old = _STATUS_LABEL.get(old, old)
                label_new = _STATUS_LABEL.get(req.status, req.status)
                note = f"状态由「{label_old}」变更为「{label_new}」"
                if req.shipped_version:
                    note += f"，上线版本 {req.shipped_version}"
                db.add(FeedbackCommentModel(
                    issue_id=issue_id, user_id=admin.id, body=note, is_system=True,
                ))
                row.comment_count += 1
            db.commit()
            db.refresh(row)
            my_votes = self._my_vote_ids(db, admin.id, [row.id])
            return self._serialize_issue(db, row, admin.id, my_votes)

    def delete_issue(self, issue_id: int) -> bool:
        with self.session_factory() as db:
            row = db.get(FeedbackIssueModel, issue_id)
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True

    # ── 统计看板 ────────────────────────────────────────────
    def stats(self, viewer: UserModel) -> dict:
        with self.session_factory() as db:
            stmt = select(FeedbackIssueModel)
            vis = self._visible_filter(viewer)
            if vis is not None:
                stmt = stmt.where(vis)
            rows = db.scalars(stmt).all()
            now = app_now()
            week_ago = now - timedelta(days=7)
            counts = {s: 0 for s in _STATUS_LABEL}
            resolved_week = 0
            created_week = 0
            resolve_hours: list[float] = []
            for r in rows:
                counts[r.status] = counts.get(r.status, 0) + 1
                if r.created_at and r.created_at >= week_ago:
                    created_week += 1
                if r.resolved_at:
                    if r.resolved_at >= week_ago:
                        resolved_week += 1
                    if r.created_at:
                        resolve_hours.append((r.resolved_at - r.created_at).total_seconds() / 3600)
            total = len(rows)
            done = counts["resolved"] + counts["shipped"] + counts["closed"]
            return {
                "total": total,
                "open": counts["open"] + counts["confirmed"],
                "in_progress": counts["in_progress"],
                "resolved": counts["resolved"],
                "shipped": counts["shipped"],
                "closed": counts["closed"],
                "resolved_this_week": resolved_week,
                "created_this_week": created_week,
                "avg_resolve_hours": round(sum(resolve_hours) / len(resolve_hours), 1) if resolve_hours else None,
                "resolve_rate": round(done / total, 3) if total else 0.0,
            }
