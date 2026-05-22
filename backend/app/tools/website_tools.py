"""Website 生成工具 — copy_template 复制基础模板到工作目录"""

import shutil
from pathlib import Path

from wuwei.tools import ToolRegistry

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_TEMPLATES_DIR = _PROJECT_ROOT / "data" / "website-templates"
_WEBSITES_DIR = _PROJECT_ROOT / "data" / "websites"

ALLOWED_STACKS = {"vanilla", "vue", "react"}


def register_website_tools(registry: ToolRegistry) -> None:

    @registry.tool(display_name="复制网站模板")
    async def copy_template(stack: str, target_slug: str) -> str:
        """复制基础模板到目标目录，作为新项目的起点。

        参数:
          stack: 技术栈，可选 "vanilla"、"vue"、"react"
          target_slug: 项目标识，kebab-case，如 "my-homepage"

        返回:
          操作结果描述
        """
        if stack not in ALLOWED_STACKS:
            return f"不支持的技术栈：{stack}。可选：{', '.join(sorted(ALLOWED_STACKS))}"

        source_dir = _TEMPLATES_DIR / stack
        if not source_dir.exists():
            return f"模板目录不存在：{source_dir}"

        target_dir = _WEBSITES_DIR / target_slug
        if target_dir.exists():
            return (
                f"目标目录已存在：{target_dir}\n"
                f"如果要修改已有项目，请直接使用文件工具编辑 {target_dir} 下的文件，"
                f"或调用 list_website_projects 查看所有项目。"
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

        return (
            f"已复制 {stack} 模板到 {target_dir}\n"
            f"\n项目文件：\n{file_list}\n"
            f"\n下一步：使用文件工具编辑项目文件，然后调用 build_website('{target_slug}') 构建。"
        )

    @registry.tool(display_name="列出网站项目")
    async def list_website_projects() -> str:
        """列出 data/websites/ 下所有已创建的网站项目。

        返回:
          项目列表，包含名称、技术栈推测、文件数
        """
        if not _WEBSITES_DIR.exists():
            return "暂无项目（data/websites/ 目录不存在）"

        projects = sorted(
            d for d in _WEBSITES_DIR.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

        if not projects:
            return "暂无项目"

        lines = []
        for proj in projects:
            files = list(proj.rglob("*"))
            file_count = len([f for f in files if f.is_file()])
            # 推测技术栈
            has_vue = any(f.suffix == ".vue" for f in files)
            has_jsx = any(f.suffix == ".jsx" for f in files)
            has_tsx = any(f.suffix == ".tsx" for f in files)
            if has_vue:
                stack_guess = "vue"
            elif has_jsx or has_tsx:
                stack_guess = "react"
            else:
                stack_guess = "vanilla"

            has_pkg = (proj / "package.json").exists()
            has_dist = (proj / "dist").exists()
            extra = []
            if not has_pkg:
                extra.append("无 package.json")
            if has_dist:
                extra.append("已构建")

            note = f" ({', '.join(extra)})" if extra else ""
            lines.append(
                f"  {proj.name} — {stack_guess}，{file_count} 个文件{note}"
            )

        return "已创建的项目：\n" + "\n".join(lines)

    @registry.tool(display_name="构建网站")
    async def build_website(project_slug: str) -> str:
        """对指定项目执行 npm install && npm run build。

        参数:
          project_slug: 项目标识（data/websites/ 下的目录名）

        返回:
          构建结果
        """
        import subprocess
        import sys

        target_dir = _WEBSITES_DIR / project_slug
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
            f"产物目录：{dist_dir}\n"
            f"产物文件（{len(dist_files)} 个）：\n" +
            "\n".join(f"  {f}" for f in dist_files[:30]) +
            ("\n  ..." if len(dist_files) > 30 else "")
        )
