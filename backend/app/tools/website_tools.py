"""Website 生成工具 — copy_template / build / deploy"""

import re
import shutil
from pathlib import Path

from wuwei.tools import ToolRegistry

from app.core.data_path import (
    WEBSITES_DIR,
    WEBSITE_TEMPLATES_DIR,
    get_current_session_id,
    get_current_user_id,
    next_version_dir, _parse_dir_name,
    set_current_website_dir,
)

ALLOWED_STACKS = {"vanilla", "vue", "react"}

# npm 共享缓存目录（沙箱把 HOME 指向工作区，不显式指定的话每个项目
# 都会有一份独立缓存 → 每次构建重新下载全部依赖）
NPM_CACHE_DIR = WEBSITES_DIR / ".npm-cache"


def _npm_unavailable_reason() -> str | None:
    """探测 npm 是否可用；不可用时返回一段面向用户的说明，可用时返回 None。

    为什么单独抽一个前置检查：容器里没有 npm 时，`npm install` 会以
    退出码 127 失败，而 stderr 只有一行 `sh: npm: not found`。那行字混在
    「构建失败」的通用报错里，看起来像项目本身有问题，用户会反复改代码。
    这里把它变成一句明确的「环境缺 npm + 怎么补」。
    """
    import shutil

    npm = shutil.which("npm")
    if npm:
        return None
    return (
        "构建环境缺少 npm：当前运行环境（通常是后端容器镜像）里没有安装 Node.js/npm，"
        "因此无法执行 npm install / npm run build。\n"
        "处理办法：\n"
        "  1. 若用 Docker 部署，重建运行时镜像（deploy/Dockerfile.runtime 已加入 nodejs + npm），"
        "然后重启 backend 与 worker；\n"
        "  2. 若在宿主机直接运行，安装 Node.js 22+（含 npm）后重启后端。\n"
        "这不是项目代码的问题，无需修改 package.json 或源码。"
    )


def _detect_broken_node_modules(project_dir: Path) -> str | None:
    """探测 node_modules 里是否有被截断的原生二进制。

    上游缺陷（实测）：沙箱超时是 SIGKILL，npm 被打断时已下载的原生
    二进制留在磁盘上但**只写了一半**。npm 之后认为该包已装好而跳过重装，
    于是每次构建都在 dlopen 阶段失败：

        Error: dlopen(.../rollup-darwin-arm64.node):
          segment '__TEXT' content (fileOffset: 0x0 -> 0x1B4000)
          extends beyond end of file (length: 0x137B98)

    判断依据：``.node`` 文件是 ELF/Mach-O 可执行文件，正常至少有几十 KB；
    截断的文件会明显偏小。返回损坏文件的描述，没坏则返回 None。
    """
    node_modules = project_dir / "node_modules"
    if not node_modules.is_dir():
        return None

    # 只看顶层依赖目录里的原生模块（rollup / esbuild / swc 等），
    # 深度过深会拖慢每次构建前的检查。
    for pkg_dir in node_modules.iterdir():
        if not pkg_dir.is_dir() or pkg_dir.name.startswith("."):
            continue
        candidates = [pkg_dir]
        # @scope/pkg 形态
        if pkg_dir.name.startswith("@"):
            candidates = [p for p in pkg_dir.iterdir() if p.is_dir()]
        for pkg in candidates:
            try:
                for native in pkg.rglob("*.node"):
                    size = native.stat().st_size
                    if size < 1024:
                        rel = native.relative_to(project_dir)
                        return f"{rel}（仅 {size} 字节，明显被截断）"
            except OSError:
                continue
    return None


def _normalize_index_html(project_dir: Path) -> list[str]:
    """构建前修复 index.html 里两个高频坑，返回改动说明。

    模型改页面时几乎必犯这两条，而它们都不会让构建"失败"，只是安静地
    产出坏结果，用户看到的才是问题：

    1. **丢掉 ``type="module"``**。模板里是 ``<script type="module" src="/js/main.js">``，
       模型重写整份 HTML 时常写成 ``<script src="./js/main.js" defer>``。
       Vite 只处理 module 脚本，于是这个文件**不会被打进 dist**，线上 404、
       页面交互全失效（滚动、菜单、动画都没了）。补回 module 即可。

    2. **写成绝对路径** ``/css/style.css``、``/js/main.js``。站点部署在
       ``/sites/<project>/`` 子路径下，绝对路径会指向站点根，样式和脚本 404。
       统一改成相对路径 ``./``。
    """
    notes: list[str] = []
    index_path = project_dir / "index.html"
    if not index_path.is_file():
        return notes

    try:
        html = index_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return notes

    original = html

    # 1. 根路径资源改相对路径（跳过 //cdn 这种协议相对地址）
    html = re.sub(r'(src|href)=(["\'])/(?!/)', r"\1=\2./", html)
    if html != original:
        notes.append("把绝对路径资源改成相对路径（站点挂在 /sites/<project>/ 子路径下）")

    # 2. 本地 <script src> 补 type="module"
    def _fix_script_tags(text: str) -> tuple[str, bool]:
        changed = False

        def repl(tag_match: re.Match[str]) -> str:
            nonlocal changed
            tag = tag_match.group(0)
            src_match = re.search(r'src=(["\'])([^"\']+)\1', tag)
            if not src_match:
                return tag
            src = src_match.group(2)
            # 外部 CDN / data URI 不需要（也不该）加 module
            if re.match(r"^(https?:)?//", src) or src.startswith("data:"):
                return tag
            if re.search(r"\btype=", tag):
                return tag
            changed = True
            return tag[:-1] + ' type="module">'

        return re.sub(r"<script\b[^>]*>", repl, text), changed

    html, script_changed = _fix_script_tags(html)
    if script_changed:
        notes.append('给本地脚本补回 type="module"（否则 Vite 不打包，线上 404）')

    if html != original:
        try:
            index_path.write_text(html, encoding="utf-8")
        except OSError:
            return []

    return notes


_VANILLA_STACK = "vanilla"


def _design_themes_dir() -> Path:
    """平台设计主题目录（与 PPT 主题库同源：data/design-themes/）。"""
    from app.services.ppt.theme_token_resolver import _THEMES_DIR

    return Path(_THEMES_DIR)


def _resolve_current_project() -> Path | None:
    """当前会话定位到的网站项目目录；未设置时按 user/session 探测一次。"""
    from app.core.data_path import get_current_website_dir

    current = get_current_website_dir()
    if current and Path(current).is_dir():
        return Path(current)
    # 探测：与 check_website_project 同一规则，取该会话最新版本目录
    user_id = get_current_user_id()
    session_id = get_current_session_id()
    if not session_id or not user_id:
        return None
    prefix = f"u{user_id}_s{session_id}_v"
    candidates = [
        d for d in WEBSITES_DIR.iterdir()
        if d.is_dir() and d.name.startswith(prefix)
    ] if WEBSITES_DIR.is_dir() else []
    if not candidates:
        return None
    best = max(
        candidates,
        key=lambda d: int(d.name[len(prefix):]) if d.name[len(prefix):].isdigit() else -1,
    )
    return best if (best / "index.html").exists() or any(best.glob("**/*.html")) else None


def _find_entry_css(project_dir: Path) -> Path | None:
    """找项目的入口样式表：含 Design Tokens :root 块的 css。

    模板三件套的位置：vanilla → css/style.css；vue → src/assets/main.css；
    react → src/index.css。不写死路径 —— glob 找含 Design Tokens 注释的
    :root 块，兜底取第一个含 :root 的 css。
    """
    css_files = sorted(p for p in project_dir.rglob("*.css") if "node_modules" not in p.parts)
    for p in css_files:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "Design Tokens" in text and re.search(r":root\s*\{", text):
            return p
    for p in css_files:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if re.search(r":root\s*\{", text):
            return p
    return None


def _is_vanilla_static(project_dir: Path) -> bool:
    """vanilla 站是不是纯静态（不需要 npm 构建）。

    判据是「**浏览器能不能直接跑**」，而不是「有没有 package.json 依赖」。
    这个区别很关键：vanilla 模板本身自带 ``package.json``（只有 ``vite`` 这个
    devDependency，用来本地 dev server + 打包），但页面里一行裸模块导入都没有
    —— ``index.html`` 直接 ``<link>`` 引 css、``<script>`` 引 js，``main.js``
    全是原生 DOM 代码。这种站复制到 dist 就能托管，跑 npm 纯属浪费。

    早先按「有任何 dependencies/devDependencies 就走 npm」判定，结果
    vanilla 模板自带 vite → 永远走 npm → 内网 npm install 必挂
    （EAI_AGAIN），用户看到「构建失败」而站点其实完全不需要构建。

    真正的判据：**源码里有没有裸模块引用**（``import x from 'pkg'``）。
    有 → 浏览器无法直接解析，必须打包；没有 → 静态站。

    仍然保守处理：``detect_stack`` 判成 vanilla、有 index.html、
    且没有裸模块引用，三条同时满足才算静态站。任何一条不确定都走 npm，
    不会把需要编译的站点当静态站直接拷过去。
    """
    try:
        from app.services.website_stack import detect_stack

        if detect_stack(project_dir) != _VANILLA_STACK:
            return False
    except Exception:  # noqa: BLE001 - 探测失败一律按需要构建处理
        return False
    # 静态站必须有入口页：没有 index.html 的目录不可能是可直接
    # 托管的站点（顶层 build 也印证了这一点）。
    if not (project_dir / "index.html").is_file():
        return False

    return not _has_bare_module_import(project_dir)


# 裸模块导入：``import x from 'pkg'`` / ``import 'pkg'`` / ``export ... from 'pkg'``，
# 其中 ``pkg`` 不是相对路径也不是绝对 URL。这类文件浏览器无法直接执行，
# 必须经过打包器解析（Vite/Rollup/Webpack）。
#
# 只扫前端源码后缀：package.json / vite.config.js 里出现 import 不算数
# （那些是 Node 侧配置文件，本来就不进浏览器）。
_BARE_IMPORT_RE = re.compile(
    r"""^\s*(?:import\s[^'"]*from\s*|import\s*|export\s[^'"]*from\s*)['"]([^'"]+)['"]""",
    re.MULTILINE,
)
_BROWSER_SOURCE_SUFFIXES = {".js", ".mjs", ".jsx", ".ts", ".tsx", ".vue"}

# 构建工具配置文件：只在 Node 侧执行，产物里不会出现，不能作为「需要打包」的证据。
# 典型例子是模板自带的 ``vite.config.js``——它 ``import { defineConfig } from 'vite'``，
# 但页面本身是纯静态的。不排除它，vanilla 模板永远判不成静态站。
_NODE_ONLY_CONFIG_FILES = {
    "vite.config.js", "vite.config.ts", "vite.config.mjs",
    "webpack.config.js", "webpack.config.ts",
    "rollup.config.js", "rollup.config.ts", "rollup.config.mjs",
    "postcss.config.js", "postcss.config.cjs", "postcss.config.mjs",
    "tailwind.config.js", "tailwind.config.ts", "tailwind.config.cjs",
    "eslint.config.js", "eslint.config.mjs", ".eslintrc.js", ".eslintrc.cjs",
    "babel.config.js", "babel.config.cjs", "svelte.config.js",
    "nuxt.config.js", "nuxt.config.ts", "astro.config.mjs",
}


def _has_bare_module_import(project_dir: Path) -> bool:
    """源码里是否存在浏览器无法直接解析的裸模块导入。

    相对路径（``./x.js``）、绝对路径（``/x.js``）、URL（``https://...``）
    都不算 —— 浏览器能自己取到。只有包名（``import { ref } from 'vue'``）
    才需要打包器介入。
    """
    skip_dirs = {"dist", "node_modules", ".git"}
    for path in project_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _BROWSER_SOURCE_SUFFIXES:
            continue
        if path.name in _NODE_ONLY_CONFIG_FILES:
            continue
        try:
            rel_parts = path.relative_to(project_dir).parts
        except ValueError:
            continue
        if rel_parts and rel_parts[0] in skip_dirs:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            # 读不了就当有依赖，宁可多跑一次 npm 也不要产出坏站点
            return True
        for match in _BARE_IMPORT_RE.finditer(text):
            spec = match.group(1).strip()
            if not spec:
                continue
            if spec.startswith(("./", "../", "/", "http://", "https://", "//")):
                continue
            # 协议相对 / 带协议的（data:, blob:）浏览器都能处理
            if ":" in spec.split("/")[0]:
                continue
            return True
    return False


def _rewrite_root_asset_refs(html: str) -> str:
    """把 index.html 里**根绝对路径**的本地资源引用改写为相对路径。

    为什么必须：预览端点与短链都是**子路径**托管
    （/api/v1/website/preview/<slug>/<token>/、/sites/<slug>/、/s/<code>/302），
    AI 或模板写 ``href="/css/style.css"`` 时浏览器会打到**站点根** ——
    预览下拿到的是 AgenticOS 自己的页面，站点裸奔（只有黑底和默认蓝链接）。
    相对路径 ``css/style.css`` 在任何子路径下都能解析到 dist 内的文件。

    只动指向本地目录的引用（css/js/assets/img/images/fonts/media 开头），
    外链（https://）、锚点（#）、带协议的 data: 一律不碰。
    """
    known_dirs = r"(?:css|js|assets|img|images|fonts|media|vendor)"
    html = re.sub(
        rf'(href|src)="/({known_dirs}/[^"]*)"',
        r'\1="./\2"',
        html,
    )
    # url(...) 形式（内联 style / CSS 里的背景图）
    html = re.sub(
        rf'url\(\s*["\']?/({known_dirs}/[^"\')]+)["\']?\s*\)',
        r'url("./\1")',
        html,
    )
    return html


def _emit_static_dist(project_dir: Path) -> str:
    """把纯静态 vanilla 项目原样镜像成 dist/，跳过 npm install + build。

    产物与 Vite 构建后的结构不同（没有 hash 文件名、没有打包），但对
    预览/部署完全够用：nginx 和预览服务都只认 dist 目录里的相对文件。
    """
    dist_dir = project_dir / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir, ignore_errors=True)
    dist_dir.mkdir(parents=True, exist_ok=True)
    skip = {"dist", "node_modules", ".git"}
    copied = 0
    for src in project_dir.rglob("*"):
        rel = src.relative_to(project_dir)
        if rel.parts and rel.parts[0] in skip:
            continue
        dest = dist_dir / rel
        if src.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied += 1
    # index.html 的根绝对路径引用重写为相对（见 _rewrite_root_asset_refs
    # 的说明 —— AI 十有八九会写 /css/style.css，预览端点下必裸）。
    index_html = dist_dir / "index.html"
    if index_html.is_file():
        html = index_html.read_text(encoding="utf-8", errors="ignore")
        fixed = _rewrite_root_asset_refs(html)
        if fixed != html:
            index_html.write_text(fixed, encoding="utf-8")
    return (
        f"构建完成（vanilla 静态站，无需 npm）。\n"
        f"项目目录：{project_dir}\n"
        f"产物目录：{dist_dir}\n"
        f"产物文件（{copied} 个）：\n"
        f"（已跳过 npm install / npm run build —— 纯静态站不需要打包）"
    )


def _clean_node_modules(project_dir: Path) -> bool:
    """删除 node_modules 与 lock 文件，让下次构建从干净状态重装。"""
    removed = False
    for name in ("node_modules", "package-lock.json"):
        target = project_dir / name
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            removed = True
        elif target.exists():
            try:
                target.unlink()
                removed = True
            except OSError:
                pass
    return removed


def register_website_tools(registry: ToolRegistry) -> None:

    @registry.tool(display_name="复制网站模板")
    async def copy_template(stack: str) -> str:
        """复制基础模板到目标目录，作为新项目的起点。

        目录名自动生成，格式为 u<用户ID>_s<会话ID>_v<版本号>，无需手动指定。

        参数:
          stack: 技术栈，可选 "vanilla"、"vue"、"react"

        返回:
          操作结果描述，包含生成的目录名
        """
        if stack not in ALLOWED_STACKS:
            return f"不支持的技术栈：{stack}。可选：{', '.join(sorted(ALLOWED_STACKS))}"

        source_dir = WEBSITE_TEMPLATES_DIR / stack
        if not source_dir.exists():
            return f"模板目录不存在：{source_dir}"

        user_id = get_current_user_id()
        session_id = get_current_session_id()
        if not session_id:
            return "错误：无法获取当前会话 ID，请刷新页面重试"

        target_dir = next_version_dir(WEBSITES_DIR, user_id, session_id)
        # Should never collide since we always +1, but guard anyway
        if target_dir.exists():
            return (
                f"目标目录已存在：{target_dir}\n"
                f"如果要修改已有项目，请直接使用文件工具编辑 {target_dir} 下的文件，"
                f"或调用 check_website_project 查看所有项目。"
            )

        try:
            shutil.copytree(source_dir, target_dir)
        except OSError as e:
            return f"复制失败：{e}"

        files = sorted(
            str(p.relative_to(target_dir)).replace("\\", "/")
            for p in target_dir.rglob("*") if p.is_file()
        )
        file_list = "\n".join(f"  {f}" for f in files)

        # Set current website dir so file tools resolve relative paths here
        set_current_website_dir(str(target_dir))

        return (
            f"已复制 {stack} 模板到 {target_dir}\n"
            f"项目目录名：{target_dir.name}\n"
            f"\n项目文件：\n{file_list}\n"
            f"\n项目目录已设置，后续文件操作会自动定位到此目录。"
            f"\n下一步：使用文件工具编辑项目文件（只需提供相对路径如 css/style.css），然后调用 build_website('{target_dir.name}') 构建。"
        )
    @registry.tool(display_name="检查当前项目")
    async def check_website_project() -> str:
        """检查当前会话的网站项目是否存在。

        根据 user_id 和 session_id 查找匹配的项目目录。
        如果找到，自动设置为当前项目目录并返回信息。
        如果未找到，返回提示需要先调用 copy_template。

        返回:
          项目状态信息，包含目录名和文件数
        """
        user_id = get_current_user_id()
        session_id = get_current_session_id()
        if not session_id:
            return "错误：无法获取当前会话 ID"

        if not WEBSITES_DIR.exists():
            return "当前会话暂无项目，请调用 copy_template(stack) 创建"

        # 查找匹配 user_id + session_id 的最新版本
        candidates = []
        for d in WEBSITES_DIR.iterdir():
            if not d.is_dir():
                continue
            parsed = _parse_dir_name(d.name)
            if parsed and parsed[0] == user_id and parsed[1] == session_id:
                candidates.append((d, parsed[2]))

        if not candidates:
            return "当前会话暂无项目，请调用 copy_template(stack) 创建"

        # 取最新版本
        candidates.sort(key=lambda x: x[1], reverse=True)
        project_dir, version = candidates[0]
        file_count = len([f for f in project_dir.rglob("*") if f.is_file()])

        # 自动设置为当前项目目录
        set_current_website_dir(str(project_dir))

        has_dist = (project_dir / "dist").exists()
        status = "已构建" if has_dist else "未构建"

        return (
            f"项目已存在：{project_dir.name}\n"
            f"版本：v{version}，文件数：{file_count}，状态：{status}\n"
            f"项目目录已设置，可直接使用文件工具编辑（只需提供相对路径）。"
        )

    @registry.tool(display_name="应用设计主题")
    async def apply_design_theme(theme_name: str) -> str:
        """把平台设计主题应用到当前项目，替换入口样式表的 Design Tokens。

        主题与 PPT 主题库同源（236 个，全部经过 WCAG 对比度审计）：
        ink-wash / art-deco / ascii-art / neo-brutalism / apple / github …

        应用后页面的颜色、字体、圆角、阴影全部由 var(--token) 驱动 ——
        你不需要再自己发明颜色，只管用 var() 引用；改风格 = 换主题名。

        参数:
          theme_name: 主题名（不确切时随便传一个词，返回值会给出最接近的候选）

        返回:
          应用的变量清单 + WCAG 对比度审计 + 下一步指引
        """
        from app.services.ppt.contrast import audit_theme_tokens, parse_theme_css
        from app.services.ppt.theme_token_resolver import list_available_themes

        themes = list_available_themes()
        if not themes:
            return "错误：设计主题目录为空（data/design-themes/），请检查部署。"

        requested = (theme_name or "").strip().lower().replace("_", "-")
        if requested not in themes:
            close = [t for t in themes if requested and (requested in t or t in requested)]
            if not close:
                close = [t for t in themes if requested.split("-")[0] and requested.split("-")[0] in t]
            listing = "\n".join(f"  - {t}" for t in (close or themes)[:24])
            return (
                f"没有名为「{theme_name}」的设计主题。\n可用主题（部分）：\n{listing}\n"
                f"\n提示：主题名就是 PPT 主题选择器里的那些（apple / github / ink-wash / art-deco …），"
                f"传错会列出最接近的候选。"
            )

        theme_css_path = _design_themes_dir() / f"{requested}.css"
        tokens = parse_theme_css(theme_css_path.read_text(encoding="utf-8", errors="ignore"))
        if not tokens:
            return f"错误：主题 {requested} 的 css 没有 :root 变量块。"

        project_dir = _resolve_current_project()
        if project_dir is None:
            return (
                "错误：当前会话没有已定位的网站项目。请先调用 copy_template(stack) "
                "创建项目，或调用 check_website_project() 定位已有项目。"
            )

        entry_css = _find_entry_css(project_dir)
        if entry_css is None:
            return (
                f"错误：在 {project_dir.name} 里找不到入口样式表（含 Design Tokens :root 块的 css）。"
                "请确认项目结构完整，或用文件工具手动创建。"
            )

        audit = audit_theme_tokens(tokens)

        # 整块替换入口 css 顶部的 Design Tokens :root —— 模板三件套
        # （vanilla/vue/react）的 :root 变量名与主题完全同套（--bg/--text-1/
        # --accent/--radius…），替换后页面里所有 var() 引用自动换肤。
        new_root = "\n".join(f"  {k}: {v};" for k, v in tokens.items())
        replacement = (
            "/* === Design Tokens === 平台设计主题（与 PPT 主题库同源）\n"
            f"    主题：{requested} —— 颜色/字体/圆角/阴影全部用 var() 引用，不要写死 hex。\n"
            "    :root {\n" + new_root + "\n}"
        )
        css_text = entry_css.read_text(encoding="utf-8")
        pattern = re.compile(
            r"(/\*\s*=+\s*Design Tokens\s*=+\s*\*/\s*)?:root\s*\{[^}]*\}", re.S
        )
        if pattern.search(css_text):
            updated = pattern.sub(replacement.replace("\\", "\\\\"), css_text, count=1)
        else:
            updated = replacement + "\n\n" + css_text
        entry_css.write_text(updated, encoding="utf-8")

        audit_lines = "\n".join(
            f"  {p['pair']}: {p['ratio']}:1（{p['grade']}）" for p in audit["pairs"]
        )
        rel = str(entry_css.relative_to(project_dir)).replace("\\", "/")
        return (
            f"已应用设计主题「{requested}」到 {rel}（共 {len(tokens)} 个 token）。\n"
            f"\nWCAG 对比度审计：\n{audit_lines}\n"
            f"\n下一步：\n"
            f"1. 页面里所有颜色一律用 var(--bg) / var(--text-1) / var(--accent) 等引用，"
            f"禁止写死 hex（主题整体换色时页面自动跟随）；\n"
            f"2. 需要强调色之外的点缀可用 var(--accent-2) / var(--accent-3)；\n"
            f"3. 调用 build_website('{project_dir.name}') 构建验证。"
        )

    @registry.tool(display_name="列出设计主题")
    async def list_design_themes() -> str:
        """列出全部可用的平台设计主题（与 PPT 主题库同源）。

        返回:
          主题名清单（apply_design_theme 的 theme_name 参数取值）
        """
        from app.services.ppt.theme_token_resolver import list_available_themes

        themes = list_available_themes()
        if not themes:
            return "错误：设计主题目录为空。"
        return f"可用设计主题 {len(themes)} 个（用 apply_design_theme 应用）：\n" + ", ".join(themes)

    @registry.tool(display_name="构建网站")
    async def build_website(project_slug: str) -> str:
        """对指定项目执行 npm install && npm run build（沙箱隔离）。

        参数:
          project_slug: 项目目录名（data/websites/ 下的目录名，如 u1_abc123_v1）

        返回:
          构建结果
        """
        from app.services.sandbox import Sandbox

        # 前置检查：容器/宿主机上没有 npm 时，报错必须是「环境缺 npm」，
        # 而不是让 npm install 以退出码 127 失败、把一行 `sh: npm: not found`
        # 当成「构建失败」甩给用户。部署镜像里没有 npm 曾导致这条链路完全不可用。
        npm_missing = _npm_unavailable_reason()
        if npm_missing:
            return npm_missing

        target_dir = WEBSITES_DIR / project_slug
        if not target_dir.exists():
            return f"项目目录不存在：{target_dir}"

        # vanilla 是纯静态站点：index.html + css/ + js/ 写完就能直接托管，
        # 跑一遍 vite build 只是把同样的文件复制到 dist/。以前不分技术栈一律
        # npm install && npm run build，用户看到「构建中」等几十秒、还要吃
        # 一次 npm 依赖下载失败的风险，收益为零。这里直接就地生成 dist。
        if _is_vanilla_static(target_dir):
            return _emit_static_dist(target_dir)

        pkg_json = target_dir / "package.json"
        if not pkg_json.exists():
            return f"项目缺少 package.json：{pkg_json}"

        # 共享 npm 缓存：沙箱把 HOME 指向工作区，若不显式指定缓存目录，
        # 每个项目都会有一份独立缓存 → 每次构建都重新下载全部依赖。
        npm_cache = NPM_CACHE_DIR
        npm_cache.mkdir(parents=True, exist_ok=True)
        # 内网无外网 DNS 时，npm 默认走公网 registry.npmjs.org 必挂（EAI_AGAIN）。
        # 用环境变量覆盖源与证书校验：内网部署指向 Nexus npm-proxy，
        # 默认仍走公网镜像，同一份代码内外网都能构建。
        import os
        npm_registry = os.getenv("NPM_CONFIG_REGISTRY", "https://registry.npmmirror.com/")
        env = {
            "npm_config_cache": str(npm_cache),
            "npm_config_fund": "false",
            "npm_config_audit": "false",
            "npm_config_registry": npm_registry,
            "npm_config_strict_ssl": os.getenv("NPM_CONFIG_STRICT_SSL", "true"),
        }

        # 超时上限：干净环境下 npm install 实测 53.6s（冷缓存），
        # 120s 在弱网下会踩线 —— 而超时留下的半截 node_modules 会让
        # 后续构建永久失败（见下方 _clean_node_modules）。
        install_timeout = 300
        build_timeout = 180

        sandbox = Sandbox(
            workspace=target_dir,
            timeout=install_timeout,
            max_output=12000,
            extra_env=env,
        )

        # 上一轮如果是被超时杀死的，node_modules 里可能留着半截的原生
        # 二进制（rollup 的 .node 文件实测被截断）。先探测，坏了就清掉重来。
        stale = _detect_broken_node_modules(target_dir)
        if stale:
            _clean_node_modules(target_dir)
            return (
                f"检测到上次构建残留的损坏依赖（{stale}），已清理 node_modules。\n"
                f"请重新调用 build_website('{project_slug}') —— 本次会重新安装依赖，"
                f"首次安装约需 1-5 分钟（取决于网络）。"
            )

        # npm install（使用 --ignore-scripts 防止恶意包脚本）
        install_result = await sandbox.execute(
            "npm install --ignore-scripts", timeout=install_timeout
        )
        if not install_result.success:
            # 失败/超时都清残留：npm 在被打断后可能认为包已装好而跳过重装，
            # 下一次构建就会命中半截文件。
            _clean_node_modules(target_dir)
            hint = (
                "（已清理 node_modules，重试即可重新安装；"
                "首次安装约需 1-5 分钟）"
                if install_result.timed_out
                else "（已清理 node_modules，重试即可重新安装）"
            )
            if install_result.timed_out:
                return (
                    f"npm install 超时（超过 {install_timeout} 秒）{hint}。\n"
                    f"若反复超时，说明网络到 npm 源不通——请改用内网 npm 镜像，"
                    f"或联系管理员配置 registry。"
                )
            return (
                f"npm install 失败（退出码 {install_result.exit_code}）{hint}：\n"
                f"{install_result.stderr[-3000:]}"
            )

        # npm run build 之前先修 HTML 里两个必踩的坑（见 _normalize_index_html）。
        _normalize_index_html(target_dir)

        # npm run build
        build_result = await sandbox.execute("npm run build", timeout=build_timeout)

        if not build_result.success:
            # 构建失败也清一次：构建期报错常见于原生模块损坏，留着会一直复现。
            if _detect_broken_node_modules(target_dir):
                _clean_node_modules(target_dir)
                return (
                    f"构建失败：依赖中的原生模块损坏，已清理 node_modules。\n"
                    f"请重新调用 build_website('{project_slug}')。\n"
                    f"原始错误：\n{build_result.stderr[-2000:]}"
                )
            return (
                f"npm run build 失败（退出码 {build_result.exit_code}）：\n"
                f"{build_result.stderr[-3000:]}"
            )

        dist_dir = target_dir / "dist"
        dist_files = []
        if dist_dir.exists():
            dist_files = sorted(
                str(p.relative_to(dist_dir)).replace("\\", "/")
                for p in dist_dir.rglob("*") if p.is_file()
            )

        return (
            f"构建成功！\n"
            f"项目目录：{target_dir}\n"
            f"产物目录：{dist_dir}\n"
            f"产物文件（{len(dist_files)} 个）：\n" +
            "\n".join(f"  {f}" for f in dist_files[:30]) +
            ("\n  ..." if len(dist_files) > 30 else "")
        )

    @registry.tool(display_name="部署网站（需管理员审批）")
    async def deploy_website(project_slug: str) -> str:
        """请求部署网站到 nginx 服务器。需要管理员审批后才能上线。

        部署流程：
        1. 检查项目是否已构建（dist/ 目录存在）
        2. 创建部署请求（状态：pending）
        3. 管理员在后台审批
        4. 审批通过后自动复制 dist/ 到 nginx 服务目录
        5. 网站可通过 /sites/{slug}/ 访问

        参数:
          project_slug: 项目目录名（如 u1_abc123_v1）

        返回:
          部署请求状态
        """
        from app.services.website_deploy_service import WebsiteDeployService

        target_dir = WEBSITES_DIR / project_slug
        if not target_dir.exists():
            return f"项目目录不存在：{target_dir}"

        dist_dir = target_dir / "dist"
        if not dist_dir.exists():
            return (
                f"项目尚未构建（dist/ 目录不存在）。\n"
                f"请先调用 build_website('{project_slug}') 构建项目，"
                f"构建成功后再请求部署。"
            )

        # 检查 dist 内容
        dist_files = [f for f in dist_dir.rglob("*") if f.is_file()]
        if not dist_files:
            return "dist/ 目录为空，没有可部署的文件"

        # 获取用户信息
        user_id = get_current_user_id()
        session_id = get_current_session_id()

        # 技术栈：从项目自身的 package.json / 源码后缀判定。
        # 早前这里硬编码 "vanilla"（上面那行 _parse_dir_name 的解析结果被丢弃），
        # 导致后台部署管理里 react / vue 站点全显示成 Vanilla。
        from app.services.website_stack import detect_stack

        stack = detect_stack(target_dir)

        # 创建部署请求
        deploy_service = WebsiteDeployService()
        try:
            deploy = deploy_service.request_deploy(
                session_id=session_id or "",
                project_slug=project_slug,
                stack=stack,
                requested_by=user_id or 0,
            )
        except FileNotFoundError as e:
            return str(e)

        deploy_id = deploy.get("id", "?")

        return (
            f"部署请求已提交（ID: {deploy_id}）\n"
            f"\n📋 部署信息：\n"
            f"  项目：{project_slug}\n"
            f"  文件数：{len(dist_files)}\n"
            f"  状态：等待管理员审批\n"
            f"\n⏳ 管理员审批通过后，网站将自动部署到 /sites/{project_slug}/\n"
            f"你可以在后台「网站部署管理」中查看审批状态。"
        )
