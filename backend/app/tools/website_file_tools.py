"""Website-scoped file tools — wraps wuwei built-in file tools.

When a website project directory is set (via copy_template), all file
operations automatically resolve relative paths against that directory
instead of the project root.  This prevents the AI from accidentally
writing files into the AgenticOS source tree.
"""

from __future__ import annotations

import pathlib
from pathlib import Path

from wuwei.plugin.builtin.file import (
    _collect_files,
    _resolve_workspace_path,
    _truncate_text,
    DEFAULT_READ_LIMIT,
)
from wuwei.tools.registry import ToolRegistry

from app.core.data_path import current_workspace_dir, get_current_website_dir


# 本模块注册的全部工具名。注册前按此清单清场，避免与内置插件/独立注册冲突。
_SCOPED_FILE_TOOL_NAMES = (
    "read_text_file",
    "write_text_file",
    "append_text_file",
    "replace_in_file",
    "delete_file",
    "list_files",
    "file_to_md",
)


def _unregister_if_exists(registry: ToolRegistry, name: str) -> None:
    """移除已注册的同名工具（wuwei 的 register() 拒绝重名）。"""
    existing = registry.get(name)
    if existing is not None:
        registry.unregister(existing)


def _effective_workspace() -> str:
    """解析本次工具调用应该以哪个目录为根。

    优先级：
      1. website 模式已绑定项目目录 → 用它（建站工具链依赖这个语义）
      2. 否则 → 当前会话工作区 ``data/workspaces/u<uid>/s<sid>/``

    **绝不回退到 ``"."``**：那等于把进程 cwd（容器里是 ``/app``，含后端源码与
    全部用户数据）当成用户的 workspace。会话上下文缺失时抛错，让上层看到
    真实原因，而不是悄悄把 AI 放进 /app。
    """
    wd = get_current_website_dir()
    if wd:
        return wd
    workspace = current_workspace_dir(create=True)
    if workspace is None:
        raise RuntimeError(
            "文件工具缺少会话上下文（user_id / session_id 未设置），"
            "无法确定工作区。这是服务端调用顺序问题，不是用户操作问题。"
        )
    _ensure_workspace_layout(str(workspace))
    return str(workspace)


# 已确认布局就绪的工作区路径。工具调用是热路径（一轮对话可能几十次），
# 每次都两次 mkdir 实测约 0.2ms/次，且随调用次数线性累积；缓存后只在
# 首次进入该工作区时落盘一次。
#
# 用 set 而非单个标记：同一进程会服务多个会话。集合本身无上限风险 ——
# 每个元素只是一个路径字符串，且工作区数量远小于会话数量级。
_layout_ready: set[str] = set()


def _ensure_workspace_layout(workspace: str) -> None:
    """首次进入时补齐 uploads/ outputs/ 两个子目录（幂等，带进程内缓存）。

    不补的话 AI 第一次 ``list_files(".")`` 会看到一个空目录，无法知道该把
    产出放哪；``uploads/`` 不存在时上传工具也无处落地。
    """
    from app.core.data_path import WORKSPACE_OUTPUTS, WORKSPACE_UPLOADS

    if workspace in _layout_ready:
        return
    root = pathlib.Path(workspace)
    for name in (WORKSPACE_UPLOADS, WORKSPACE_OUTPUTS):
        (root / name).mkdir(parents=True, exist_ok=True)
    _layout_ready.add(workspace)


def register_website_file_tools(registry: ToolRegistry) -> None:
    """注册「作用域文件工具」。

    调用时机：必须**在卸载 wuwei 内置 file 插件之后**，否则同名工具会冲突。

    作用域规则见 :func:`_effective_workspace`：website 模式用项目目录，
    其它模式用会话工作区。所有模式共用这一套工具，避免出现「general 模式
    用的是内置插件（workspace='.'）→ 看到 /app」这种不一致。
    """
    try:
        _ensure_workspace_layout(_effective_workspace())
    except RuntimeError:
        # 注册阶段可能还没有会话上下文（例如应用启动时枚举工具），
        # 这时不阻断注册；真正调用工具时会再次解析并给出明确错误。
        pass

    # 先清掉同名旧工具。wuwei 的 ToolRegistry.register() 拒绝重名，
    # 而 `file_to_md` 在本模块之外还有一处独立注册（factory 的
    # `if "file" not in builtin_tools` 分支），内置 file 插件也会注册它。
    for tool_name in _SCOPED_FILE_TOOL_NAMES:
        _unregister_if_exists(registry, tool_name)

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

