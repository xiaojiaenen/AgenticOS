"""PPT / website 模式的 prompt 目录注入文案与主题清单逻辑。

大段 prompt 文案（主题清单、快速决策表、网站工作流说明等）存放于
``app/resources/prompt_catalogs/`` 下的 md 文件，本模块用
``importlib.resources.files`` 读取（打包场景安全）。
文案内容自原 agent_service.py 原样搬运，仅将动态值改为 format 占位符。
"""

import asyncio
import datetime
import importlib.resources

from app.core.data_path import DESIGN_THEMES_DIR, WEBSITE_TEMPLATES_DIR
from app.services.ppt.theme_token_resolver import build_token_quick_ref, list_available_themes

_CATALOG_PACKAGE = "app.resources.prompt_catalogs"


def _load_catalog(name: str) -> str:
    """读取 prompt 文案模板（importlib.resources 保证 zip 包/冻结打包场景可用）。

    模板文件按 VCS 规范以单个换行结尾；原始拼接结果末尾无换行，此处去除。
    """
    text = (
        importlib.resources.files(_CATALOG_PACKAGE)
        .joinpath(name)
        .read_text(encoding="utf-8")
    )
    if text.endswith("\n"):
        text = text[:-1]
    return text


def inject_design_catalog(message: str) -> str:
    """Inject design catalog: phased skill loading + theme selection + token reference.

    分阶段加载策略：LLM 按工作流阶段依次加载技能，避免一次性注入过多规则。
    """
    token_ref = build_token_quick_ref()
    theme_count = len(list_available_themes())
    theme_list = ", ".join(sorted(list_available_themes()))

    # Deck 风格预设（8 种设计语言，帮助 LLM 选择正确的视觉组合）
    try:
        from app.services.ppt.deck_styles import build_deck_styles_text
        deck_styles_text = build_deck_styles_text()
    except Exception:
        deck_styles_text = ""

    current_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return message + _load_catalog("design_catalog.md").format(
        theme_count=theme_count,
        theme_list=theme_list,
        token_ref=token_ref,
        deck_styles_text=deck_styles_text,
        current_time=current_time,
    )


def scan_website_catalog() -> tuple[list[str], int]:
    """扫描 website 模板 package.json 与设计主题数量（同步 IO，供 to_thread 调用）。"""

    templates_dir = WEBSITE_TEMPLATES_DIR
    template_info: list[str] = []
    for stack in ("vanilla", "vue", "react"):
        pkg = templates_dir / stack / "package.json"
        if not pkg.exists():
            continue
        import json
        deps = json.loads(pkg.read_text("utf-8")).get("dependencies", {})
        dep_list = ", ".join(deps.keys()) if deps else "无"
        template_info.append(f"  **{stack}** — 依赖: {dep_list}")

    theme_dir = DESIGN_THEMES_DIR
    theme_count = len(list(theme_dir.glob("*.css"))) if theme_dir.exists() else 0
    return template_info, theme_count


async def inject_website_catalog(message: str) -> str:
    """Inject template structure overview and theme guide for website mode."""
    template_info, theme_count = await asyncio.to_thread(scan_website_catalog)

    return message + _load_catalog("website_catalog.md").format(
        template_info="\n".join(template_info),
        theme_count=theme_count,
    )
