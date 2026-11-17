"""反馈广场端点（GitHub-Issue 式，仅登录用户可见）。

用户路由 ``/feedback``：列表/详情/创建/投票/评论/统计/我的。
管理路由 ``/admin/feedback``：状态流转/优先级/删除（require_admin + 审计）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.db.models import UserModel
from app.schemas.feedback import (
    FeedbackCommentCreateRequest,
    FeedbackCommentItem,
    FeedbackCreateRequest,
    FeedbackIssueDetail,
    FeedbackIssueItem,
    FeedbackIssueListResponse,
    FeedbackStatsResponse,
    FeedbackStatusUpdateRequest,
)
from app.services import audit_service
from app.services.feedback_service import FeedbackService

router = APIRouter(prefix="/feedback", tags=["Feedback"])
admin_router = APIRouter(prefix="/admin/feedback", tags=["admin-feedback"])

_service = FeedbackService()


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在或无权查看")


# ── 用户侧 ──────────────────────────────────────────────────
@router.get("/stats", response_model=FeedbackStatsResponse)
def feedback_stats(current_user: UserModel = Depends(get_current_user)) -> dict:
    return _service.stats(current_user)


@router.get("", response_model=FeedbackIssueListResponse)
def list_feedback(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    type_filter: str | None = Query(default=None, alias="type"),
    search: str | None = Query(default=None, max_length=200),
    sort: str = Query(default="votes", pattern="^(votes|newest|active)$"),
    mine: bool = Query(default=False),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    return _service.list_issues(
        current_user, page=page, page_size=page_size, status=status_filter,
        type_=type_filter, search=search, sort=sort, mine=mine,
    )


@router.post("", response_model=FeedbackIssueItem, status_code=status.HTTP_201_CREATED)
def create_feedback(
    payload: FeedbackCreateRequest,
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    return _service.create_issue(payload, current_user)


@router.get("/{issue_id}", response_model=FeedbackIssueDetail)
def get_feedback(issue_id: int, current_user: UserModel = Depends(get_current_user)) -> dict:
    result = _service.get_issue(issue_id, current_user)
    if result is None:
        raise _not_found()
    return result


@router.post("/{issue_id}/vote")
def vote_feedback(issue_id: int, current_user: UserModel = Depends(get_current_user)) -> dict:
    try:
        return _service.toggle_vote(issue_id, current_user)
    except LookupError:
        raise _not_found() from None
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/{issue_id}/comments", response_model=FeedbackCommentItem, status_code=status.HTTP_201_CREATED)
def comment_feedback(
    issue_id: int,
    payload: FeedbackCommentCreateRequest,
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    try:
        return _service.add_comment(issue_id, payload, current_user)
    except LookupError:
        raise _not_found() from None
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


# ── 管理侧 ──────────────────────────────────────────────────
@admin_router.get("/stats", response_model=FeedbackStatsResponse)
def admin_feedback_stats(_: UserModel = Depends(require_admin)) -> dict:
    # 管理员看全量（含 private）
    return _service.stats(_)


@admin_router.get("", response_model=FeedbackIssueListResponse)
def admin_list_feedback(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    type_filter: str | None = Query(default=None, alias="type"),
    search: str | None = Query(default=None, max_length=200),
    sort: str = Query(default="newest", pattern="^(votes|newest|active)$"),
    admin: UserModel = Depends(require_admin),
) -> dict:
    return _service.list_issues(
        admin, page=page, page_size=page_size, status=status_filter,
        type_=type_filter, search=search, sort=sort,
    )


@admin_router.patch("/{issue_id}", response_model=FeedbackIssueItem)
def admin_update_feedback(
    issue_id: int,
    payload: FeedbackStatusUpdateRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    admin: UserModel = Depends(require_admin),
) -> dict:
    try:
        result = _service.update_status(issue_id, payload, admin)
    except LookupError:
        raise _not_found() from None
    audit_service.record_request(
        db, http_request, action="feedback.update_status", actor=admin,
        resource_type="feedback_issue", resource_id=issue_id,
        detail={"status": payload.status, "priority": payload.priority},
    )
    return result


@admin_router.post("/{issue_id}/reply", response_model=FeedbackCommentItem, status_code=status.HTTP_201_CREATED)
def admin_reply_feedback(
    issue_id: int,
    payload: FeedbackCommentCreateRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    admin: UserModel = Depends(require_admin),
) -> dict:
    # 通知所需的作者信息：只取一次，且必须在评论写入之前（写入后行可能被改）
    _issue_author_email: str | None = None
    _issue_title = ""
    _issue_status = ""
    try:
        from app.db.models import FeedbackIssueModel, UserModel as _U
        from app.services.feedback_service import _STATUS_LABEL as _LABELS

        issue_row = db.get(FeedbackIssueModel, issue_id)
        if issue_row is not None:
            _issue_title = issue_row.title or ""
            _issue_status = _LABELS.get(issue_row.status or "", issue_row.status or "")
            author = db.get(_U, issue_row.user_id) if issue_row.user_id else None
            if author is not None and author.email:
                _issue_author_email = author.email
    except Exception:  # noqa: BLE001
        pass

    try:
        result = _service.add_comment(issue_id, payload, admin, official=True)
    except LookupError:
        raise _not_found() from None
    audit_service.record_request(
        db, http_request, action="feedback.reply", actor=admin,
        resource_type="feedback_issue", resource_id=issue_id,
    )

    # 官方回复 → 邮件通知提交者（用户自己的评论不通知，避免自己给自己发信）
    if _issue_author_email:
        try:
            from app.services.business_notifications import _spawn, notify_feedback_reply

            _spawn(
                notify_feedback_reply(
                    user_email=_issue_author_email,
                    issue_title=_issue_title,
                    reply_text=payload.body,
                    status_label=_issue_status,
                    issue_id=issue_id,
                    actor_name=admin.name,
                )
            )
        except Exception:  # noqa: BLE001 —— 通知失败不影响回复
            pass

    return result


@admin_router.delete("/{issue_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_feedback(
    issue_id: int,
    http_request: Request,
    db: Session = Depends(get_db),
    admin: UserModel = Depends(require_admin),
) -> None:
    if not _service.delete_issue(issue_id):
        raise _not_found()
    audit_service.record_request(
        db, http_request, action="feedback.delete", actor=admin,
        resource_type="feedback_issue", resource_id=issue_id,
    )
