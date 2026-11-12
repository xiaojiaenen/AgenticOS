"""Website deploy API endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin, require_feature
from pathlib import Path
from app.core.data_path import WEBSITES_DIR as _WEBSITES_DIR, _parse_dir_name
from app.core.config import get_settings
from app.db.models import UserModel
from app.schemas.website import DeployDecisionRequest, DeployRequest
from app.services import audit_service
from app.services.website_deploy_service import WebsiteDeployService

_logger = logging.getLogger("website.api")

router = APIRouter(prefix="/website", tags=["website"])

_service = WebsiteDeployService()


def _assert_can_deploy_project(project_slug: str, user: UserModel) -> None:
    """项目目录名形如 u<uid>_s<session>_v<N>；非管理员只能部署自己的项目。

    project_slug 由请求方直接提交，不校验归属就能替他人项目发起部署审批。
    顺带挡掉路径穿越（slug 必须是单一目录名）。
    """
    if user.role == "admin":
        return
    parsed = _parse_dir_name(project_slug)
    if parsed is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="项目标识不合法，应为 u<用户ID>_s<会话>_v<版本>",
        )
    if parsed[0] != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="没有权限部署他人的网站项目",
        )


@router.post("/deploy")
def request_deploy(
    body: DeployRequest,
    http_request: Request,
    user: UserModel = Depends(require_feature("write", "deploy_website")),
    db: Session = Depends(get_db),
):
    """User requests website deployment.

    鉴权分两层：功能级（这个角色能不能用「部署网站」这个功能）+
    行级（只能部署自己的项目）。前者由策略表决定，后者由目录名归属决定。
    """
    _assert_can_deploy_project(body.project_slug, user)
    deploy = _service.request_deploy(
        session_id=body.session_id,
        project_slug=body.project_slug,
        stack=body.stack,
        requested_by=user.id,
        target_domain=body.target_domain,
        visibility=body.visibility,
        title=body.title,
        description=body.description,
    )
    audit_service.record_request(
        db, http_request, action="website.deploy_request", actor=user,
        resource_type="website_deploy",
        resource_id=deploy.get("id") if isinstance(deploy, dict) else None,
        detail={"project_slug": body.project_slug, "stack": body.stack,
                "target_domain": body.target_domain},
    )
    return deploy


@router.get("/deploys")
def list_my_deploys(
    user: UserModel = Depends(get_current_user),
):
    """List deploy requests for the current user."""
    all_deploys = _service.list_all()
    return [d for d in all_deploys if d.get("requested_by") == user.id]


@router.get("/deploy/{deploy_id}")
def get_deploy(
    deploy_id: int,
    user: UserModel = Depends(get_current_user),
):
    """Get a deploy request by ID."""
    deploy = _service.get(deploy_id)
    if deploy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部署申请不存在")
    # 检查权限：只能查看自己的部署请求（管理员除外）
    if deploy.get("requested_by") != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限执行该操作")
    return deploy


@router.get("/deploy/project/{project_slug}")
def get_deploy_by_project(
    project_slug: str,
    user: UserModel = Depends(get_current_user),
):
    """Get the latest deploy for a project."""
    deploy = _service.get_by_project(project_slug)
    if deploy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部署申请不存在")
    # 检查权限：只能查看自己项目的部署请求（管理员除外），与 get_deploy 保持一致
    if deploy.get("requested_by") != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限执行该操作")
    return deploy


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------
admin_router = APIRouter(prefix="/admin/website", tags=["admin-website"])


@admin_router.get("/deploys")
def list_pending_deploys(
    admin: UserModel = Depends(require_admin),
):
    """Admin: list all pending deploy requests."""
    return _service.list_pending()


@admin_router.get("/deploys/{deploy_id}/preview")
def preview_deploy(
    deploy_id: int,
    admin: UserModel = Depends(require_admin),
):
    """Admin: 审批前看这个待部署项目长什么样。

    审批不能只看项目名和文件数 —— 管理员需要判断「这是不是该上线的东西」。
    这里返回内联资源后的自包含 HTML（与用户侧预览同一套处理：Vite 产物
    的 /assets/ 引用在 iframe srcdoc 里解析不了，必须内联）。
    """
    deploy = _service.get(deploy_id)
    if deploy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部署申请不存在")

    slug = deploy.get("project_slug") or ""
    dist_dir = _WEBSITES_DIR / slug / "dist"
    index_html = dist_dir / "index.html"
    if not index_html.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该项目的 dist/index.html 不存在，可能尚未构建或已被清理",
        )

    from app.services.agent.artifacts import ArtifactFactory

    raw = index_html.read_text(encoding="utf-8")
    return {
        "deploy_id": deploy_id,
        "project_slug": slug,
        "stack": deploy.get("stack"),
        "preview_html": ArtifactFactory._inline_dist_assets(dist_dir, raw),
        "file_count": len([f for f in dist_dir.rglob("*") if f.is_file()]),
    }


@admin_router.get("/deploys/all")
def list_all_deploys(
    admin: UserModel = Depends(require_admin),
):
    """Admin: list all deploy requests."""
    return _service.list_all()


@admin_router.get("/deploys/{deploy_id}/review")
async def review_deploy(
    deploy_id: int,
    with_ai: bool = Query(False, description="是否让模型给出风险评估"),
    admin: UserModel = Depends(require_admin),
):
    """审批审阅包：完整对话 + 源码扫描 + （可选）AI 风险意见。

    管理员判断「该不该上线」需要三样东西：用户到底提了什么需求（对话）、
    产物里有没有可疑代码（静态扫描）、以及一个不占时间的初判（AI 意见）。
    这三样在同一个响应里返回，前端一屏展示。
    """
    from app.db.models import WebsiteDeployModel
    from app.services.website_review_service import ai_review, build_review_packet

    with _service.session_factory() as db:
        deploy = db.get(WebsiteDeployModel, deploy_id)
        if deploy is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部署申请不存在")
        packet = build_review_packet(deploy)

    if with_ai:
        packet["ai"] = await ai_review(packet)
    return packet


@admin_router.post("/deploys/{deploy_id}/decision")
def decide_deploy(
    deploy_id: int,
    body: DeployDecisionRequest,
    http_request: Request,
    admin: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin: approve or reject a deploy request."""
    deploy = _service.decide(
        deploy_id=deploy_id,
        status=body.status,
        approved_by=admin.id,
        reason=body.reason,
    )
    # 审批是最需要留痕的动作之一：谁批的、批成什么、理由是什么
    audit_service.record_request(
        db, http_request, action="website.deploy_decision", actor=admin,
        resource_type="website_deploy", resource_id=deploy_id,
        result=audit_service.RESULT_ALLOW if body.status == "approved" else audit_service.RESULT_DENY,
        detail={"status": body.status, "reason": body.reason},
    )

    # 审批通过 → 邮件通知作者（附封面与访问地址）。通知失败不影响审批结果。
    if body.status == "approved":
        try:
            from app.db.models import UserModel as _U
            from app.services.business_notifications import _spawn, notify_deploy_approved

            author = db.get(_U, deploy.get("requested_by")) if deploy.get("requested_by") else None
            if author is not None and author.email:
                _spawn(
                    notify_deploy_approved(
                        user_email=author.email,
                        user_name=author.name,
                        title=deploy.get("title") or deploy.get("project_slug") or "",
                        project_slug=deploy.get("project_slug") or "",
                        visibility=deploy.get("visibility") or "private",
                        short_url=deploy.get("short_url"),
                        description=deploy.get("description"),
                    )
                )
        except Exception:  # noqa: BLE001
            pass

    return deploy


# ---------------------------------------------------------------------------
# 作品库（gallery）与私密站点访问
# ---------------------------------------------------------------------------


@router.post("/deploy/{deploy_id}/cancel")
def cancel_deploy(
    deploy_id: int,
    http_request: Request,
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """取消部署：站点下线，**源码保留**（可随时重新部署）。"""
    try:
        result = _service.cancel(
            deploy_id, by_user_id=user.id, is_admin=(user.role == "admin")
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    audit_service.record_request(
        db, http_request, action="website.deploy_cancel", actor=user,
        resource_type="website_deploy", resource_id=deploy_id,
        detail={"project_slug": result.get("project_slug")},
    )
    return result


@router.get("/cover/{slug}")
def get_cover(slug: str):
    """作品封面（部署后 Playwright 异步截图 + 压缩）。

    公开可读：封面本身不含私密内容（首屏截图），且作品库卡片要在未登录
    也能展示（例如分享给别人看自己的作品列表）。缺失时 404，前端回退占位。
    """
    from fastapi.responses import FileResponse

    from app.services.website_cover_service import cover_file

    for candidate in (cover_file(slug), cover_file(slug).with_suffix(".png")):
        if candidate.is_file():
            media = "image/webp" if candidate.suffix == ".webp" else "image/png"
            return FileResponse(candidate, media_type=media, headers={"Cache-Control": "public, max-age=3600"})
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="封面尚未生成")


@router.get("/{project_slug}/stats")
def website_stats(
    project_slug: str,
    days: int = Query(30, ge=1, le=365),
    user: UserModel = Depends(get_current_user),
):
    """作品访问统计（按天 + 按来源）。仅作品所有者与管理员可见。"""
    from sqlalchemy import select

    from app.db.models import WebsiteDeployModel

    with _service.session_factory() as db:
        row = db.scalars(
            select(WebsiteDeployModel)
            .where(WebsiteDeployModel.project_slug == project_slug)
            .order_by(WebsiteDeployModel.updated_at.desc())
            .limit(1)
        ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在")
    if row.requested_by != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该作品统计")

    from app.services.website_cover_service import view_stats

    stats = view_stats(project_slug, days=days)
    stats.update(
        {
            "project_slug": project_slug,
            "view_count": row.view_count or 0,
            "last_viewed_at": row.last_viewed_at.isoformat() if row.last_viewed_at else None,
        }
    )
    return stats


@router.get("/gallery")
def list_gallery(user: UserModel = Depends(get_current_user)):
    """作品库：已发布的作品（网站 + 文件型产物）。

    - 网站：public 所有人可见，deploy_url 指向 /sites/ 公开路径；
      private 仅部署者（和管理员）可见，附 30 天签名访问链接。
    - 文件型（PPT / 文档 / 表格）：只能公开，统一走 /s/<code>/ 短链。

    两类合并成一个列表返回（前端作品库按同一套卡片渲染），用 ``item_type``
    区分：``website`` / ``ppt`` / ``document`` / ``sheet``。
    """
    sites = _service.list_gallery(viewer_id=user.id, is_admin=user.role == "admin")
    items: list[dict[str, Any]] = []
    for site in sites:
        item = dict(site)
        item["item_type"] = "website"
        items.append(item)

    try:
        from app.services.published_item_service import PublishedItemService

        for pub in PublishedItemService().list_gallery(
            viewer_id=user.id, is_admin=user.role == "admin"
        ):
            item = dict(pub)
            item["item_type"] = pub.get("kind", "website")
            item["stack"] = pub.get("kind_label", "")
            item["deploy_url"] = pub.get("short_url")
            item["cover_url"] = pub.get("cover_url")
            items.append(item)
    except Exception:  # noqa: BLE001 —— 文件型作品读取失败不影响网站作品
        _logger.warning("作品库合并文件型作品失败", exc_info=True)

    # 统一按最近更新时间倒序
    items.sort(key=lambda i: (i.get("updated_at") or i.get("created_at") or ""), reverse=True)
    return items


@router.post("/deploy/{deploy_id}/reset-access")
def reset_private_access(
    deploy_id: int,
    user: UserModel = Depends(get_current_user),
):
    """重置私密站点的访问链接（旧链接立即失效，作品库拿到新链接）。"""
    try:
        result = _service.reset_access_token(deploy_id, requested_by=user.id, is_admin=user.role == "admin")
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部署申请不存在")
    return result


@router.get("/site/{slug}/{rel_path:path}")
def serve_private_site(
    slug: str,
    rel_path: str,
    response: Response,
    t: str | None = Query(None, description="私密站点访问令牌（30 天，部署完成时签发）"),
    request: Request = None,  # type: ignore[assignment]
):
    """私密站点静态访问（带 30 天签名；作品库里可随时重置链接）。

    公开站点直接走 nginx /sites/；私密站点必须经过这里做签名校验，
    避免落到公开路径让「私密」形同虚设。

    **为什么还要 cookie**：页面里的样式和脚本是相对路径
    （``./assets/index-xxx.css``），浏览器解析相对 URL 时会**丢掉原 URL 的
    查询串** —— 于是 ``?t=<token>`` 只对 index.html 生效，CSS/JS 全部因为
    缺 token 被 403/422 拒掉，用户看到的是没有样式的裸 HTML（这条链路曾经
    就是这么坏的）。所以首次带 ``t`` 访问时，把令牌种成该路径下的 cookie，
    后续子资源请求浏览器会自动带上，签名校验照旧生效。
    """
    from app.core.security import decode_access_token
    from fastapi.responses import FileResponse
    import mimetypes

    # 访问统计：只对入口 HTML 计数（子资源会放大 10-50 倍，没有意义）。
    # 不论公开/私密、不管从哪里点进来，都经过这里 —— 这正是「全部访问都统计」
    # 的落点。写库失败不影响响应。
    if (rel_path or "").strip().lstrip("/") in ("", "index.html", "./index.html"):
        try:
            import asyncio as _aio

            from app.services.website_cover_service import record_view

            _ref = (request.headers.get("referer") or "") if request is not None else ""
            _ua = (request.headers.get("user-agent") or "") if request is not None else ""
            _host = ""
            if _ref:
                try:
                    from urllib.parse import urlparse as _up

                    _host = _up(_ref).hostname or ""
                except Exception:  # noqa: BLE001
                    _host = ""
            _src = "gallery" if "gallery" in _ref else ("direct" if not _ref else "external")
            _aio.get_running_loop().create_task(
                _aio.to_thread(
                    record_view, slug, source=_src, referer_host=_host, user_agent=_ua
                )
            )
        except RuntimeError:
            pass
        except Exception:  # noqa: BLE001
            pass

    settings = get_settings()

    clean = (rel_path or "index.html").strip().lstrip("/")
    if not clean or clean.endswith("/"):
        clean = f"{clean}index.html"

    # 入口 HTML 必须带 t：cookie 只作为「页面内子资源」的回退。
    # 若入口也认 cookie，把链接发给别人后对方浏览器一旦种过 cookie，
    # 此后不带 token 直接敲地址也能打开，私密等于失效（测试就是这么抓到的）。
    is_entry = clean in ("index.html", "./index.html")

    token = t
    set_cookie = False
    if not token:
        if is_entry:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="缺少访问令牌：请通过作品库里的完整链接打开",
            )
        # 子资源请求：浏览器只会回传 path 匹配的 cookie
        if request is not None:
            token = request.cookies.get(f"site_token_{slug}")
        if not token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="缺少访问令牌：请通过作品库里的完整链接打开",
            )
    else:
        set_cookie = True

    payload = decode_access_token(token, secret=settings.auth_secret_key)
    if payload is None or payload.get("scope") != "website_private":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="访问链接无效或已过期")
    if str(payload.get("slug")) != slug:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="访问链接与项目不匹配")

    dist_dir = (Path(_WEBSITES_DIR) / slug / "dist").resolve()
    if not dist_dir.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="站点产物不存在")

    candidate = (dist_dir / clean).resolve()
    try:
        candidate.relative_to(dist_dir)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="非法的资源路径") from None
    if candidate.is_dir():
        candidate = candidate / "index.html"
    if not candidate.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在")

    media_type, _ = mimetypes.guess_type(str(candidate))
    result = FileResponse(
        candidate,
        media_type=media_type or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )
    if set_cookie:
        # httponly：前端 JS 不需要读它；samesite=lax 让同站导航也带得上
        result.set_cookie(
            key=f"site_token_{slug}",
            value=token,
            path=f"/api/v1/website/site/{slug}/",
            max_age=30 * 24 * 3600,
            httponly=True,
            samesite="lax",
        )
    return result
