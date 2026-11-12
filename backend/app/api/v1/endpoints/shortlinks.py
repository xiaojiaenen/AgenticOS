"""短链入口：``/s/<code>`` → 作品真实地址。

独立于 ``/api/v1/website`` 前缀 —— nginx 把 ``/s/`` 直接反代到后端根路径，
所以这里的路由必须是 ``/s/{code}``。放独立文件也避免与业务端点混在一起。

两类作品共用同一套短码空间：

- **网站**：302 到 nginx 静态目录（公开）或带签名的后端端点（私密）。
- **文件型作品**（PPT / 文档 / 表格）：302 到下载端点；未上架的短码
  给出明确原因，而不是静默 404。
"""

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select

from app.db.models import WebsiteDeployModel
from app.services.website_deploy_service import WebsiteDeployService

router = APIRouter(tags=["短链"])
_deploy_service = WebsiteDeployService()


def _resolve_published_item(code: str):
    """文件型作品短码 → 302 到下载端点。未找到返回 None。"""
    from app.db.models import PublishedItemModel

    with _deploy_service.session_factory() as db:
        row = db.scalars(
            select(PublishedItemModel)
            .where(PublishedItemModel.short_code == code)
            .limit(1)
        ).first()

    if row is None:
        return None
    if row.status != "deployed":
        detail_map = {
            "cancelled": "该作品已由作者取消发布",
            "pending": "该作品等待管理员审批",
            "rejected": "该作品未通过审批",
            "failed": "该作品导出失败",
        }
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail_map.get(row.status, "该作品当前不可访问"),
        )

    from fastapi.responses import RedirectResponse

    return RedirectResponse(
        url=f"/api/v1/published-items/{row.id}/download",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/s/{code}")
@router.get("/s/{code}/{rel_path:path}")
def resolve_short_link(
    code: str,
    rel_path: str = "",
    t: str | None = Query(None, description="私密站点访问令牌"),
    request: Request = None,  # type: ignore[assignment]
):
    """短链入口：``/s/<code>`` → 对应作品的真实访问地址。

    对外只暴露短码，不泄漏 uid/session/版本。公开站点 302 到
    nginx 静态目录；私密站点 302 到带签名校验的后端端点（令牌原样透传）。
    短码失效（已取消/被新版本顶替）时返回 404 并说明原因。
    """
    from fastapi.responses import RedirectResponse

    published = _resolve_published_item(code)
    if published is not None:
        return published

    with _deploy_service.session_factory() as db:
        row = db.scalars(
            select(WebsiteDeployModel)
            .where(WebsiteDeployModel.short_code == code)
            .order_by(WebsiteDeployModel.updated_at.desc())
            .limit(1)
        ).first()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="链接不存在或已失效")
    if row.status != "deployed":
        # 已取消 / 待重新审批（旧版下架）/ 失败：明确告知而不是静默 404
        detail_map = {
            "cancelled": "该网站已由作者取消部署",
            "superseded": "该网站已提交新版本，等待重新审批",
            "pending": "该网站等待管理员审批",
            "rejected": "该网站未通过审批",
            "failed": "该网站部署失败",
        }
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail_map.get(row.status, "该网站当前不可访问"),
        )

    suffix = (rel_path or "").lstrip("/")
    if row.visibility == "public":
        target = f"/sites/{row.project_slug}/{suffix}"
    else:
        token_q = f"?t={t}" if t else ""
        target = f"/api/v1/website/site/{row.project_slug}/{suffix}{token_q}"
    return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)
