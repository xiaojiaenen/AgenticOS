"""Website 生成工具 — copy_template / build / deploy"""

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

    @registry.tool(display_name="构建网站")
    async def build_website(project_slug: str) -> str:
        """对指定项目执行 npm install && npm run build（沙箱隔离）。

        参数:
          project_slug: 项目目录名（data/websites/ 下的目录名，如 u1_abc123_v1）

        返回:
          构建结果
        """
        from app.services.sandbox import Sandbox

        target_dir = WEBSITES_DIR / project_slug
        if not target_dir.exists():
            return f"项目目录不存在：{target_dir}"

        pkg_json = target_dir / "package.json"
        if not pkg_json.exists():
            return f"项目缺少 package.json：{pkg_json}"

        # 共享 npm 缓存：沙箱把 HOME 指向工作区，若不显式指定缓存目录，
        # 每个项目都会有一份独立缓存 → 每次构建都重新下载全部依赖。
        npm_cache = NPM_CACHE_DIR
        npm_cache.mkdir(parents=True, exist_ok=True)
        env = {
            "npm_config_cache": str(npm_cache),
            "npm_config_fund": "false",
            "npm_config_audit": "false",
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
