"""网站预览的带鉴权静态托管（不落 nginx，不构成部署）。

为什么要它：预览此前把 dist 里的 JS/CSS 内联成 100KB+ 的单个 HTML 字符串
塞进 iframe srcdoc。问题一串：每次拼字符串、浏览器无法缓存、相对路径
必须手工改写、内联 module 脚本不执行（曾导致白屏）。

改成静态托管后浏览器按原生方式加载，但**绝不能放到 nginx 的 /sites/**
——那是「审批通过后对外发布」的位置，放进去等于绕过审批直接公开。

所以走这条私有通道：
- URL 带短时签名（JWT，绑定 user_id + session_id + slug）；
- 服务端校验签名、校验会话归属，再从 WEBSITES_DIR/<slug>/dist 读文件；
- 相对路径天然继承 /api/v1/website/preview/<slug>/ 前缀，无需改写；
- 只在登录用户自己的会话内可用，与审批无关。
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.data_path import WEBSITES_DIR, _parse_dir_name
from app.core.security import create_access_token, decode_access_token
from app.db.models import UserModel

_logger = logging.getLogger("website.preview")

router = APIRouter(prefix="/website", tags=["website-preview"])

_PREVIEW_TTL_SECONDS = 15 * 60


def issue_preview_token(*, user_id: int, session_id: str, slug: str) -> str:
    """签发预览访问令牌（15 分钟，绑定用户 + 会话 + 项目）。"""
    return create_access_token(
        {"sub": str(user_id), "scope": "website_preview", "sid": session_id, "slug": slug},
        secret=get_settings().auth_secret_key,
        expires_in_seconds=_PREVIEW_TTL_SECONDS,
    )


def _resolve_dist_file(slug: str, rel_path: str) -> Path:
    """把请求路径解析成 dist 内的真实文件（阻断路径穿越）。"""
    if not slug or Path(slug).name != slug or slug in {".", ".."}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="非法的项目标识")
    dist_dir = (WEBSITES_DIR / slug / "dist").resolve()
    if not dist_dir.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该项目尚未构建（缺少 dist/）")

    clean = (rel_path or "").strip().lstrip("/")
    if not clean or clean.endswith("/"):
        clean = f"{clean}index.html"

    candidate = (dist_dir / clean).resolve()
    # 关键：解析后的真实路径必须仍在 dist 目录内，否则就是穿越
    try:
        candidate.relative_to(dist_dir)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="非法的资源路径") from None

    if candidate.is_dir():
        candidate = candidate / "index.html"
    if not candidate.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在")
    return candidate


@router.get("/preview/{slug}/{token}/{rel_path:path}")
def serve_preview(
    slug: str,
    token: str,
    rel_path: str,
) -> FileResponse:
    """按需返回 dist 内的单个静态文件（带签名校验）。

    令牌放在 **path 段**而不是 query：预览页面里的相对引用（
    ``./assets/index-x.js``、``../img/a.png``）要能自然继承前缀。
    若用 ``?token=...``，浏览器解析相对路径时会丢掉 query，请求落到
    ``/api/v1/website/preview/assets/...``（缺 slug）→ 404 白屏。

    这里**不校验登录态**：iframe 请求带不上 Authorization 头，鉴权完全
    靠短时签名 —— 签名绑定 user_id / session_id / slug，别人拿不到有效
    令牌，也无法把令牌挪用到别的项目上。
    """
    payload = decode_access_token(token, secret=get_settings().auth_secret_key)
    if payload is None or payload.get("scope") != "website_preview":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="预览令牌无效或已过期")
    if str(payload.get("slug")) != slug:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="预览令牌与项目不匹配")

    file_path = _resolve_dist_file(slug, rel_path)
    media_type, _encoding = mimetypes.guess_type(str(file_path))
    headers = {
        # 短时签名 + 私有内容：允许浏览器缓存但禁止共享缓存
        "Cache-Control": "private, max-age=300",
        "X-Content-Type-Options": "nosniff",
    }
    return FileResponse(file_path, media_type=media_type or "application/octet-stream", headers=headers)


def _assert_can_preview_project(slug: str, user: UserModel) -> None:
    """现签预览令牌前校验项目归属（与 website.py 的部署校验同一套规则）。

    项目目录名 ``u<uid>_s<session>_v<version>`` 自带归属：非管理员只能给
    **自己名下**的项目签预览令牌。没有这道校验的话，任何登录用户拿到别人的
    slug（项目目录就在 data/websites 下，目录名可枚举）就能签出有效令牌、
    打开别人的网站内容 —— 而 serve_preview 只验签名与 slug 匹配，分不清
    令牌是谁替谁签的。解析不出归属的目录名一律拒绝（正规项目目录都由
    ``next_version_dir`` 按此格式生成）。
    """
    parsed = _parse_dir_name(slug)
    if parsed is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="项目标识不合法，应为 u<用户ID>_s<会话>_v<版本>",
        )
    if user.role != "admin" and parsed[0] != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="没有权限预览他人的网站项目",
        )


@router.post("/preview-token")
def create_preview_token(
    slug: str = Query(..., min_length=1, max_length=120),
    session_id: str = Query(..., min_length=1, max_length=128),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """为当前用户 + 会话签发预览令牌，并返回可直接给 iframe 用的 URL。"""
    # 归属校验放在 dist 存在性检查**之前**：非法 slug 统一 400、他人项目统一
    # 403，不给"按响应码差异探测 dist 是否存在"留口子。
    _assert_can_preview_project(slug, current_user)
    if not (WEBSITES_DIR / slug / "dist").is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该项目尚未构建（缺少 dist/）")

    token = issue_preview_token(user_id=current_user.id, session_id=session_id, slug=slug)
    # 令牌在 path 段：相对引用能继承 /preview/<slug>/<token>/ 前缀
    base = f"/api/v1/website/preview/{slug}/{token}/"
    return {
        "token": token,
        "url": base,
        "expires_in": _PREVIEW_TTL_SECONDS,
    }
