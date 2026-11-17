"""文件型作品发布 API（PPT / 文档 / 表格）。

路由挂在应用根（与 shortlinks 一致），这样短链 ``/s/{code}/`` 能直接
反查两种作品类型：网站走 nginx 静态目录，文件型作品走后端下载端点。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.models import UserModel
from app.schemas.published_items import (
    PublishedItemDecisionRequest,
    PublishedItemPublishRequest,
)
from app.services import audit_service
from app.services.published_item_service import (
    KIND_MIME,
    PublishedItemService,
)

router = APIRouter(tags=["published-items"])

_service = PublishedItemService()


def _current_user(user: UserModel = Depends(get_current_user)) -> UserModel:
    return user


@router.post("/api/v1/published-items", summary="提交作品发布申请")
def request_publish(
    payload: PublishedItemPublishRequest,
    http_request: Request,
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """提交发布申请（文件型作品只能公开）。

    管理员提交时直接进入待审批队列（不自动通过）—— 保持与网站发布
    一致的审批口径，避免"管理员自己发的东西绕过审核"。
    """
    try:
        result = _service.request_publish(
            kind=payload.kind,
            session_id=payload.session_id,
            source_ref=payload.source_ref,
            user_id=user.id,
            title=payload.title,
            description=payload.description or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit_service.record_request(
        db, http_request, action="published_item.request", actor=user,
        resource_type="published_item", resource_id=result["id"],
        detail={"kind": payload.kind, "source_ref": payload.source_ref},
    )
    return result


@router.get("/api/v1/published-items", summary="我的发布记录")
def list_mine(
    user: UserModel = Depends(get_current_user),
):
    items = [i for i in _service.list_all(limit=200) if i["user_id"] == user.id]
    return {"items": items}


@router.get("/api/v1/published-items/{item_id}", summary="发布记录详情")
def get_one(item_id: int, user: UserModel = Depends(get_current_user)):
    item = _service.get(item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发布记录不存在")
    if item["user_id"] != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该发布记录")
    return item


@router.post("/api/v1/published-items/{item_id}/cancel", summary="取消发布")
def cancel(
    item_id: int,
    http_request: Request,
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """取消发布：作品从作品库下架，**源产物保留**。"""
    try:
        result = _service.cancel(item_id, by_user_id=user.id, is_admin=(user.role == "admin"))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    audit_service.record_request(
        db, http_request, action="published_item.cancel", actor=user,
        resource_type="published_item", resource_id=item_id,
    )
    return result


# ── 管理员 ────────────────────────────────────────────────────────────


@router.get("/api/v1/admin/published-items", summary="管理员：全部发布记录")
def admin_list_all(user: UserModel = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可访问")
    return {"items": _service.list_all(limit=200)}


@router.get("/api/v1/admin/published-items/pending", summary="管理员：待审批列表")
def admin_list_pending(user: UserModel = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可访问")
    return {"items": _service.list_pending()}


@router.post("/api/v1/admin/published-items/{item_id}/decision", summary="管理员：审批发布")
def admin_decide(
    item_id: int,
    payload: PublishedItemDecisionRequest,
    http_request: Request,
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可访问")
    try:
        result = _service.decide(item_id, payload.status, approved_by=user.id, reason=payload.reason)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit_service.record_request(
        db, http_request, action="published_item.decide", actor=user,
        resource_type="published_item", resource_id=item_id,
        detail={"status": payload.status},
    )

    # 审批通过 → 邮件通知作者。通知失败不影响审批结果。
    if payload.status == "approved":
        try:
            from app.db.models import UserModel as _U
            from app.services.business_notifications import _spawn, notify_published_item_approved

            author = db.get(_U, result.get("user_id")) if result.get("user_id") else None
            if author is not None and author.email:
                _spawn(
                    notify_published_item_approved(
                        user_email=author.email,
                        title=result.get("title") or "",
                        kind_label=result.get("kind_label") or result.get("kind") or "",
                        short_url=result.get("short_url"),
                        description=result.get("description"),
                    )
                )
        except Exception:  # noqa: BLE001
            pass

    return result


# ── 公开访问 ──────────────────────────────────────────────────────────


@router.get("/api/v1/published-items/gallery", summary="作品库：文件型作品")
def gallery(user: UserModel = Depends(get_current_user)):
    return {"items": _service.list_gallery(viewer_id=user.id, is_admin=user.role == "admin")}


@router.get("/api/v1/published-items/{item_id}/download", summary="下载已发布的文件")
def download(item_id: int, download: int = Query(0, ge=0, le=1)):
    """下载 / 内联预览已发布的文件。

    文件型作品只有公开版本（没有私密态），所以不需要登录态；
    但仍然要求记录处于 ``deployed``，未过审的文件拿不到。
    """
    item = _service.get(item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在")
    if item["status"] != "deployed":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品尚未发布")

    from app.db.models import PublishedItemModel
    from app.db.session import create_db_session

    with create_db_session() as db:
        row = db.get(PublishedItemModel, item_id)
        path = _service.file_path(row) if row is not None else None

    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")

    kind = item["kind"]
    media = KIND_MIME.get(kind, "application/octet-stream")
    headers = {"Cache-Control": "public, max-age=3600"}
    # 中文文件名不能直接塞进 Content-Disposition（HTTP 头是 latin-1），
    # 用 RFC 5987 的 filename*=UTF-8''...，同时给一个 ASCII 回退名。
    from urllib.parse import quote

    ascii_name = path.name.encode("ascii", "ignore").decode("ascii") or f"download{_ext_for(kind)}"
    disposition = "attachment" if download else "inline"
    headers["Content-Disposition"] = (
        f"{disposition}; filename=\"{ascii_name}\"; "
        f"filename*=UTF-8''{quote(path.name)}"
    )
    return FileResponse(path, media_type=media, headers=headers)


def _ext_for(kind: str) -> str:
    from app.services.published_item_service import KIND_EXTENSIONS

    return KIND_EXTENSIONS.get(kind, ".bin")
