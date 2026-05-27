"""Website-scoped file tools — wraps wuwei built-in file tools.

When a website project directory is set (via copy_template), all file
operations automatically resolve relative paths against that directory
instead of the project root.  This prevents the AI from accidentally
writing files into the AgenticOS source tree.
"""

from __future__ import annotations

from pathlib import Path

from wuwei.tools.builtin.file_tools import (
    _collect_files,
    _resolve_workspace_path,
    _truncate_text,
    DEFAULT_READ_LIMIT,
)
from wuwei.tools.registry import ToolRegistry

from app.core.data_path import get_current_website_dir


def _effective_workspace() -> str:
    """Return the current website dir if set, else ``'.'``."""
    wd = get_current_website_dir()
    return wd if wd else "."


def register_website_file_tools(registry: ToolRegistry) -> None:
    """Register file tools that scope to the current website project dir.

    Call **after** the built-in ``file`` tools have been unregistered.
    """

    @registry.tool(
        name="read_text_file",
        description="读取当前网站项目内的文本文件内容。路径为相对路径（如 css/style.css）。",
        display_name="读取文本文件",
    )
    def read_text_file(
        path: str, max_chars: int = DEFAULT_READ_LIMIT, workspace: str | None = None,
    ) -> dict:
        ws = workspace or _effective_workspace()
        target = _resolve_workspace_path(path, workspace=ws)
        if not target.is_file():
            raise FileNotFoundError(f"文件不存在: {path}")
        text = target.read_text(encoding="utf-8")
        content, truncated = _truncate_text(text, max_chars=max_chars)
        return {
            "ok": True,
            "path": str(target),
            "content": content,
            "truncated": truncated,
            "size_chars": len(text),
        }

    @registry.tool(
        name="write_text_file",
        description="写入当前网站项目内的文本文件。路径为相对路径（如 src/main.js）。默认不覆盖已有文件，overwrite=true 时才覆盖。",
        side_effect=True,
        requires_approval=True,
        display_name="写入文本文件",
    )
    def write_text_file(
        path: str,
        content: str,
        overwrite: bool = False,
        workspace: str | None = None,
    ) -> dict:
        ws = workspace or _effective_workspace()
        target = _resolve_workspace_path(path, workspace=ws)
        if target.exists() and target.is_dir():
            raise IsADirectoryError(f"目标是目录，不能写入文件: {path}")
        if target.exists() and not overwrite:
            raise FileExistsError(
                f"文件已存在: {path}。设置 overwrite=true 可覆盖。"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(target), "bytes": len(content.encode("utf-8"))}

    @registry.tool(
        name="append_text_file",
        description="追加内容到当前网站项目内的文本文件。路径为相对路径。",
        side_effect=True,
        requires_approval=True,
        display_name="追加文本文件",
    )
    def append_text_file(
        path: str, content: str, workspace: str | None = None,
    ) -> dict:
        ws = workspace or _effective_workspace()
        target = _resolve_workspace_path(path, workspace=ws)
        if target.exists() and target.is_dir():
            raise IsADirectoryError(f"目标是目录，不能追加文件: {path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as f:
            f.write(content)
        return {"ok": True, "path": str(target), "bytes": len(content.encode("utf-8"))}

    @registry.tool(
        name="replace_text_in_file",
        description="修改当前网站项目内文本文件：把 old_text 替换为 new_text。路径为相对路径。",
        side_effect=True,
        requires_approval=True,
        display_name="替换文件内容",
    )
    def replace_text_in_file(
        path: str,
        old_text: str,
        new_text: str,
        count: int = -1,
        workspace: str | None = None,
    ) -> dict:
        if not old_text:
            raise ValueError("old_text 不能为空")
        ws = workspace or _effective_workspace()
        target = _resolve_workspace_path(path, workspace=ws)
        if not target.is_file():
            raise FileNotFoundError(f"文件不存在: {path}")
        text = target.read_text(encoding="utf-8")
        occurrences = text.count(old_text)
        if occurrences == 0:
            raise ValueError("未找到 old_text，文件未修改")
        max_replace = count if count is not None and count >= 0 else occurrences
        updated = text.replace(old_text, new_text, max_replace)
        target.write_text(updated, encoding="utf-8")
        return {
            "ok": True,
            "path": str(target),
            "replacements": min(occurrences, max_replace),
        }

    @registry.tool(
        name="delete_file",
        description="删除当前网站项目内的单个文件。只删除文件，不删除目录。路径为相对路径。",
        side_effect=True,
        requires_approval=True,
        display_name="删除文件",
    )
    def delete_file(path: str, workspace: str | None = None) -> dict:
        ws = workspace or _effective_workspace()
        target = _resolve_workspace_path(path, workspace=ws)
        if not target.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        if not target.is_file():
            raise IsADirectoryError(f"只允许删除文件，不允许删除目录: {path}")
        target.unlink()
        return {"ok": True, "path": str(target), "deleted": True}

    @registry.tool(
        name="list_files",
        description="列出当前网站项目内指定目录下的文件和子目录（默认递归 3 层，最多返回 200 项）。路径为相对路径。",
        display_name="列出文件",
    )
    def list_files(
        path: str = ".",
        max_depth: int = 3,
        max_files: int = 200,
        workspace: str | None = None,
    ) -> dict:
        ws = workspace or _effective_workspace()
        target = _resolve_workspace_path(path, workspace=ws)
        if not target.exists():
            raise FileNotFoundError(f"路径不存在: {path}")
        if not target.is_dir():
            raise NotADirectoryError(f"路径不是目录: {path}")
        workspace_root = Path(ws).resolve()
        entries, truncated = _collect_files(target, max_depth, max_files, workspace_root)
        return {
            "ok": True,
            "path": str(target.relative_to(workspace_root)),
            "files": entries,
            "count": len(entries),
            "truncated": truncated,
        }

    @registry.tool(
        name="file_to_md",
        description="将文件转换为 markdown 供大模型阅读，支持常见文本文件、pptx,docx,xlsx,xls,pdf 等。路径为相对路径。",
        display_name="文件转Markdown",
    )
    def file_to_md(path: str, workspace: str | None = None):
        from markitdown import MarkItDown

        ws = workspace or _effective_workspace()
        target = _resolve_workspace_path(path, workspace=ws)
        try:
            md_converter = MarkItDown()
            result = md_converter.convert(str(target))
        except Exception as e:
            return str(e)
        if result is None or result.text_content.strip() == "":
            return "转换失败，该文件无法转换"
        return result.text_content

