"""短链入口：``/s/<code>`` → 作品真实地址。

独立于 ``/api/v1/website`` 前缀 —— nginx 把 ``/s/`` 直接反代到后端根路径，
所以这里的路由必须是 ``/s/{code}``。放独立文件也避免与业务端点混在一起。

两类作品共用同一套短码空间：

- **网站**：302 到 nginx 静态目录（公开）或带签名的后端端点（私密）。
- **文件型作品**（PPT / 文档 / 表格）：302 到下载端点；未上架的短码
  给出明确原因，而不是静默 404。
"""

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.db.models import WebsiteDeployModel
from app.services.website_deploy_service import WebsiteDeployService

router = APIRouter(tags=["短链"])
_deploy_service = WebsiteDeployService()


def _resolve_published_item(code: str):
    """文件型作品短码 → **预览页**（HTML），未找到返回 None。

    为什么不是 302 到下载端点：docx / xlsx / pptx 浏览器无法原生内联渲染，
    直接跳过去要么触发下载、要么白屏，用户看到的就是"点开没反应/404"。
    这里返回一个真正的预览页：标题、类型、作者、下载按钮，以及能渲染的就
    内嵌渲染（PPT 走平台已有的 SVG 预览，文档/表格给出下载入口）。

    与网站的区别：网站 302 到静态目录（浏览器能直接渲染 HTML）；文件型
    必须由我们出一张页面来承接。
    """
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

    return _render_preview_page(row)


def _render_preview_page(row) -> HTMLResponse:
    """文件型作品的预览页。

    三种产物能力不同，处理方式也不同：
    - **文档**导出的是 .html —— 可以直接内嵌 iframe 完整渲染，和网站一样。
    - **PPT / 表格**是二进制 Office 格式，浏览器不能原生显示。
      给出封面信息 + 明确的下载按钮（PPT 另给平台内的幻灯片预览链接）。

    样式用系统字体与中性灰阶，不引外部资源 —— 这个页面在 nginx 里是公开的，
    任何外链都可能被内网环境阻断。
    """
    from html import escape

    from app.services.published_item_service import KIND_DOCUMENT, KIND_LABELS, KIND_PPT

    kind = row.kind
    label = KIND_LABELS.get(kind, kind)
    title = escape(row.title or label)
    download_url = f"/api/v1/published-items/{row.id}/download?download=1"
    inline_url = f"/api/v1/published-items/{row.id}/download"

    # 文档是 HTML：直接铺满视口渲染，体验最接近"打开就是内容"
    if kind == KIND_DOCUMENT:
        body = f"""
    <iframe src="{inline_url}" title="{title}" style="position:fixed;inset:0;width:100%;height:100%;border:0;background:#fff"></iframe>
    <a class="fab" href="{download_url}" download>下载原文件</a>"""
        title_bar = ""
    else:
        hint = (
            "PPT 是二进制格式，浏览器无法直接显示。"
            if kind == KIND_PPT
            else "表格是二进制格式，浏览器无法直接显示。"
        )
        body = f"""
    <main class="card">
      <div class="badge">{escape(label)}</div>
      <h1>{title}</h1>
      <p class="hint">{hint}请下载后用本地应用打开；如需在线查看，请回到 AgenticOS 的对话里打开该产物。</p>
      <a class="btn" href="{download_url}" download>下载 {escape(label)}</a>
    </main>"""
        title_bar = ""

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100vh;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    background: #fafafa; color: #18181b;
    display: flex; align-items: center; justify-content: center; padding: 24px;
  }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #09090b; color: #fafafa; }}
    .card {{ background: #18181b; border-color: #27272a; }}
    .hint {{ color: #a1a1aa; }}
    .btn {{ background: #fafafa; color: #18181b; }}
    .fab {{ background: #ffffffe6; color: #18181b; }}
  }}
  .card {{
    max-width: 520px; width: 100%; background: #fff;
    border: 1px solid #e4e4e7; border-radius: 16px; padding: 32px;
    box-shadow: 0 1px 2px rgb(0 0 0 / 0.04);
  }}
  .badge {{
    display: inline-block; font-size: 12px; font-weight: 600;
    padding: 3px 10px; border-radius: 999px;
    background: #f4f4f5; color: #52525b; margin-bottom: 14px;
  }}
  h1 {{ font-size: 20px; line-height: 1.4; margin: 0 0 10px; font-weight: 600; }}
  .hint {{ font-size: 14px; line-height: 1.7; color: #71717a; margin: 0 0 22px; }}
  .btn {{
    display: inline-flex; align-items: center; gap: 8px;
    background: #18181b; color: #fafafa; text-decoration: none;
    font-size: 14px; font-weight: 500; padding: 10px 18px; border-radius: 8px;
  }}
  .btn:hover {{ opacity: .9; }}
  .fab {{
    position: fixed; right: 20px; bottom: 20px; z-index: 10;
    display: inline-flex; align-items: center;
    background: #18181be6; color: #fafafa; text-decoration: none;
    font-size: 13px; font-weight: 500; padding: 9px 16px; border-radius: 999px;
    backdrop-filter: blur(8px); box-shadow: 0 4px 16px rgb(0 0 0 / .16);
  }}
</style>
</head>
<body>{title_bar}{body}</body>
</html>"""
    return HTMLResponse(html)


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
        # 空 suffix（访问 /s/<code>/）要显式补 index.html：
        # nginx 的 `alias` + `try_files $uri/` 组合在不同版本上对"目录 → index"
        # 的行为不一致（有的直接 404），显式指向文件最稳。非空 suffix
        # （/s/<code>/assets/x.js）原样透传。
        target = f"/sites/{row.project_slug}/{suffix or 'index.html'}"
    else:
        token_q = f"?t={t}" if t else ""
        target = f"/api/v1/website/site/{row.project_slug}/{suffix}{token_q}"
    return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)
