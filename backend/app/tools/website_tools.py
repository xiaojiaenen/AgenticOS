"""Website 生成工具 — copy_template 复制基础模板到工作目录"""

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
        """对指定项目执行 npm install && npm run build。

        参数:
          project_slug: 项目目录名（data/websites/ 下的目录名，如 u1_abc123_v1）

        返回:
          构建结果
        """
        import subprocess
        import sys

        target_dir = WEBSITES_DIR / project_slug
        if not target_dir.exists():
            return f"项目目录不存在：{target_dir}"

        pkg_json = target_dir / "package.json"
        if not pkg_json.exists():
            return f"项目缺少 package.json：{pkg_json}"

        npm = "npm.cmd" if sys.platform == "win32" else "npm"

        # npm install
        try:
            result = subprocess.run(
                [npm, "install"],
                cwd=str(target_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return "npm install 超时（120 秒）"

        if result.returncode != 0:
            out = (result.stdout or "")[-2000:] + (result.stderr or "")[-2000:]
            return f"npm install 失败（退出码 {result.returncode}）：\n{out}"

        # npm run build
        try:
            result = subprocess.run(
                [npm, "run", "build"],
                cwd=str(target_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return "npm run build 超时（120 秒）"

        if result.returncode != 0:
            out = (result.stdout or "")[-3000:] + (result.stderr or "")[-3000:]
            return f"npm run build 失败（退出码 {result.returncode}）：\n{out}"

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
