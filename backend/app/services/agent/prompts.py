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

# 注入段的边界标记（不可见字符序列，不会出现在正常文本里）。
# 用途：区分「用户说的话」与「系统塞给模型的目录文档」，
# 落库/回显前据此剥离，避免用户刷新后看到自己"发了一大段资源速查"。
WEBSITE_CATALOG_MARKER = "\n\u2063[[WEBSITE_CATALOG]]\u2063\n"


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
    """Inject template structure overview and theme guide for website mode.

    注入段用 ``WEBSITE_CATALOG_MARKER`` 包住：这段是**模型上下文**，
    不是用户说的话。落库/回显前用 ``strip_injected_catalog`` 剥掉，
    否则用户刷新会话会看到自己"发了一大段资源速查文档"。
    """
    template_info, theme_count = await asyncio.to_thread(scan_website_catalog)

    body = _load_catalog("website_catalog.md").format(
        template_info="\n".join(template_info),
        theme_count=theme_count,
    )
    return f"{message}{WEBSITE_CATALOG_MARKER}\n{body}\n{WEBSITE_CATALOG_MARKER}"


def strip_injected_catalog(text: str) -> str:
    """剥掉注入的目录文档段，只留用户原始输入（落库/回显用）。

    两代格式都要处理：
    - 新格式：带 ``WEBSITE_CATALOG_MARKER`` 边界（可靠切分）；
    - 旧格式（历史数据）：标记之前是直接 ``message + catalog`` 拼接，
      只能按目录文档的固定开头特征识别并截断。历史消息不改库，
      只在读取时剥离 —— 用户不该看到自己"发了一大段资源速查"。
    """
    if not text:
        return text
    if WEBSITE_CATALOG_MARKER in text:
        head, _, _rest = text.partition(WEBSITE_CATALOG_MARKER)
        return head.rstrip()

    # 旧格式：目录文档以「## Website 模式资源速查」等标题开头
    for marker_head in _LEGACY_CATALOG_HEADS:
        idx = text.find(marker_head)
        if idx > 0:
            return _trim_trailing_sep(text[:idx])
    return text


def _trim_trailing_sep(text: str) -> str:
    """去掉剥离后残留的分隔线（注入原文是 ``message + "\\n---\\n\\n## …"``，
    截断在标题前会把 ``\\n---`` 留在末尾，用户就看见一个孤零零的 ``---``）。"""
    trimmed = text.rstrip()
    while trimmed.endswith("---"):
        trimmed = trimmed[:-3].rstrip()
    return trimmed


# 历史注入文档的固定开头（见 resources/prompt_catalogs/website_catalog.md）
_LEGACY_CATALOG_HEADS: tuple[str, ...] = (
    "\n---\n\n## Website 模式资源速查",
    "## Website 模式资源速查",
    "\n---\n\n### 设计主题（",
    "### 设计主题（",
)


_MEMORY_START = "## 用户记忆（来自历史对话，自动蒸馏）"
_MEMORY_END = "（以上记忆自动注入，回答时自然参考即可，不必显式引用）"

def strip_memory_context(text: str) -> str:
    """剥掉注入的用户记忆块，只留用户原始输入（回显用）。"""
    if not text or not text.startswith(_MEMORY_START):
        return text
    end = text.find(_MEMORY_END)
    if end < 0:
        return text
    end += len(_MEMORY_END)
    rest = text[end:]
    rest = rest.lstrip("\n")
    if rest.startswith("---"):
        rest = rest[3:]
    return rest.lstrip("\n")
