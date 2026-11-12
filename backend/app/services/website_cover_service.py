"""作品封面截图与访问统计。

## 封面

部署完成后用一个**独立的 Playwright 进程**截首屏（1440×900，懒加载前），
缩放压缩成 WebP 存到 ``data/website-covers/<slug>.webp``。全程后台任务：
部署接口不等截图，失败只记日志（作品库回退到「无封面上」的占位样式）。

为什么不复用 llm_providers 的 Playwright：那边的浏览器实例带着企业网关的
Cookie 与代理配置，用它渲染用户站点既不安全（站点可执行脚本）也会污染
登录态。这里每次新开 incognito context，且不注入任何凭据。

## 访问统计

``record_view`` 在每次站点请求时调用（公开路径 / 私密端点 / 嵌入都算），
聚合值冗余写在 ``website_deploys`` 上，明细进 ``website_views``。
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.data_path import DATA_DIR
from app.core.timezone import app_now
from app.db.models import WebsiteDeployModel, WebsiteViewModel
from app.db.session import create_db_session

_logger = logging.getLogger("website.covers")

COVER_DIR = DATA_DIR / "website-covers"
COVER_VIEWPORT = {"width": 1440, "height": 900}
COVER_TIMEOUT_MS = 20_000


def cover_file(slug: str) -> Path:
    return COVER_DIR / f"{slug}.webp"


def _has_cover(slug: str) -> bool:
    try:
        return cover_file(slug).is_file()
    except OSError:
        return False


async def capture_cover(slug: str, url: str, *, timeout_ms: int = COVER_TIMEOUT_MS) -> bool:
    """截取站点首屏保存为封面。返回是否成功。

    在独立 incognito context 里加载（不带任何 Cookie），加载完成后等
    字体与首屏资源稳定再截，避免截到半渲染状态。
    """
    try:
        from playwright.async_api import async_playwright
    except Exception:  # noqa: BLE001 —— 未装 playwright：封面功能降级
        _logger.info("playwright 不可用，跳过封面截图: slug=%s", slug)
        return False

    COVER_DIR.mkdir(parents=True, exist_ok=True)
    target = cover_file(slug)
    tmp_png = COVER_DIR / f"{slug}.tmp.png"

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                context = await browser.new_context(
                    viewport=COVER_VIEWPORT,
                    device_scale_factor=1,
                    # 独立 context：不继承任何现有 Cookie / localStorage
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                    ),
                )
                page = await context.new_page()
                await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                # 字体与图片解码完成后再截，避免豆腐块/半张图
                try:
                    await page.evaluate("document.fonts && document.fonts.ready")
                except Exception:  # noqa: BLE001
                    pass
                await page.wait_for_timeout(600)
                await page.screenshot(path=str(tmp_png), type="png", full_page=False)
                await context.close()
            finally:
                await browser.close()

        # 压缩：优先 WebP（体积约为 PNG 的 1/8），失败回退 PNG
        try:
            from PIL import Image

            with Image.open(tmp_png) as img:
                img = img.convert("RGB")
                img.thumbnail((960, 600))
                img.save(target, "WEBP", quality=82, method=4)
            tmp_png.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001 —— 无 Pillow 时直接保留 PNG 作封面
            _logger.info("WebP 压缩不可用，保留 PNG 封面: slug=%s", slug)
            tmp_png.replace(target.with_suffix(".png"))
            target = target.with_suffix(".png")

        _logger.info("封面已生成: slug=%s file=%s size=%s", slug, target.name, target.stat().st_size)
        return True
    except Exception:  # noqa: BLE001 —— 截图失败不影响部署结果
        _logger.warning("封面截图失败: slug=%s url=%s", slug, url, exc_info=True)
        try:
            tmp_png.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def persist_cover_path(slug: str) -> None:
    """截图成功后把相对路径写回部署记录（供 _serialize 生成 cover_url）。"""
    webp = cover_file(slug)
    png = cover_file(slug).with_suffix(".png")
    found = webp if webp.is_file() else (png if png.is_file() else None)
    if found is None:
        return
    rel = str(found.relative_to(DATA_DIR)).replace("\\", "/")
    try:
        with create_db_session() as db:
            rows = db.scalars(
                select(WebsiteDeployModel).where(
                    WebsiteDeployModel.project_slug == slug,
                    WebsiteDeployModel.status == "deployed",
                )
            ).all()
            for row in rows:
                row.cover_path = rel
            db.commit()
    except Exception:  # noqa: BLE001
        _logger.warning("封面路径写库失败: slug=%s", slug, exc_info=True)


async def capture_and_store(slug: str, url: str) -> None:
    """部署完成后的后台任务：截图 → 压缩 → 写库。"""
    ok = await capture_cover(slug, url)
    if ok:
        await asyncio.to_thread(persist_cover_path, slug)


# ── 访问统计 ──────────────────────────────────────────────────────────────


def record_view(
    slug: str,
    *,
    source: str = "direct",
    referer_host: str | None = None,
    user_agent: str | None = None,
    deploy_id: int | None = None,
) -> None:
    """记录一次站点访问（同步，调用方用 to_thread 或直接调）。

    失败只记日志：统计不是请求主路径的职责，绝不能因为它让页面打不开。
    """
    try:
        with create_db_session() as db:
            row = None
            if deploy_id is not None:
                row = db.get(WebsiteDeployModel, deploy_id)
            if row is None:
                row = db.scalars(
                    select(WebsiteDeployModel)
                    .where(WebsiteDeployModel.project_slug == slug)
                    .order_by(WebsiteDeployModel.updated_at.desc())
                    .limit(1)
                ).first()
            if row is None:
                return
            row.view_count = (row.view_count or 0) + 1
            row.last_viewed_at = app_now()
            db.add(
                WebsiteViewModel(
                    deploy_id=row.id,
                    project_slug=slug,
                    source=source[:32],
                    referer_host=(referer_host or "")[:255] or None,
                    user_agent=(user_agent or "")[:255] or None,
                )
            )
            db.commit()
    except Exception:  # noqa: BLE001
        _logger.debug("访问统计写入失败: slug=%s", slug, exc_info=True)


def view_stats(slug: str, *, days: int = 30) -> dict[str, Any]:
    """按天聚合访问量（作品库详情用）。"""
    from datetime import timedelta

    since = app_now() - timedelta(days=days)
    try:
        with create_db_session() as db:
            rows = db.execute(
                select(WebsiteViewModel.created_at, WebsiteViewModel.source).where(
                    WebsiteViewModel.project_slug == slug,
                    WebsiteViewModel.created_at >= since,
                )
            ).all()
        daily: dict[str, int] = {}
        by_source: dict[str, int] = {}
        for created_at, source in rows:
            key = created_at.strftime("%Y-%m-%d") if created_at else "unknown"
            daily[key] = daily.get(key, 0) + 1
            by_source[source or "direct"] = by_source.get(source or "direct", 0) + 1
        return {
            "daily": dict(sorted(daily.items())),
            "by_source": by_source,
            "total": len(rows),
        }
    except Exception:  # noqa: BLE001
        return {"daily": {}, "by_source": {}, "total": 0}
