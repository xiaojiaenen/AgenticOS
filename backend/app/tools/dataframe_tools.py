"""代码式数据分析工具 — 在受限命名空间里跑 pandas/numpy/scipy 代码。

设计目标（用户要求）：
- 自带 pandas / numpy / scipy（项目已声明为依赖），**不允许安装其他库**；
- 代码在受限命名空间执行：import 白名单 + 危险 AST 节点拒绝 + 无文件/网络/系统调用；
- 支持把 DataFrame 导出成 CSV / Excel 到会话 workspace 的 outputs/（配合制品面板下载）。

安全边界（纵深防御，三层）：
1. AST 静态校验：只允许白名单节点；import 只能导入白名单模块；拒绝 attribute
   访问以下划线开头的名字（防 __class__/__globals__ 逃逸）、拒绝 exec/eval/open/
   compile/__import__/input 等危险内置名。
2. 受限 globals：__builtins__ 只给安全子集；不注入 __file__/__loader__ 等。
3. 资源限制：执行超时由 ToolExecutionPolicy 控制（子进程隔离由调用方 factory 的
   工具包装层统一处理），输出截断，导出路径强制在 workspace outputs/ 内。

注意：这里用的是 exec（非子进程），依赖 AST 白名单做隔离。pandas/numpy/scipy
本身是可信库；风险来自模型写的代码，因此 AST 层必须严格。任何拿不准的节点
一律拒绝（fail-closed）。
"""

from __future__ import annotations

import ast
import io
import json
import logging
import re
from typing import Any

from app.services.agent.native.tool_registry import ToolRegistry

logger = logging.getLogger("agenticos.dataframe_tools")

# 允许的 import（用户明确：自带 pandas/numpy，不装其他）。scipy 已在依赖里，
# 一并放行以便做统计/插值；statistics/math 等标准库按需放行。
_ALLOWED_IMPORTS = frozenset({
    "pandas", "numpy", "scipy",
    "math", "statistics", "json", "re", "datetime", "decimal", "fractions",
})
# import x as y / from x import y 时，只放行白名单根模块
_ALLOWED_IMPORT_ROOTS = frozenset(m.split(".")[0] for m in _ALLOWED_IMPORTS)

# 危险内置名：一律拒绝出现在代码里（作为 Name/attribute）
_FORBIDDEN_NAMES = frozenset({
    "open", "exec", "eval", "compile", "__import__", "__builtins__",
    "input", "breakpoint",
    "exit", "quit", "help", "globals", "locals", "vars", "dir", "getattr",
    "setattr", "delattr", "memoryview", "super", "property", "classmethod",
    "staticmethod", "type", "object", "classmethod",
})

# pandas/numpy 的文件/网络/进程 IO 入口一律禁止：本工具的数据只来自入参 data，
# 导出只走受控 export 参数。列出的是常用入口，未来新增按同样模式补充。
_FORBIDDEN_LIB_ATTRS = frozenset({
    "read_csv", "read_table", "read_excel", "read_json", "read_html",
    "read_parquet", "read_feather", "read_pickle", "read_sql",
    "read_sql_query", "read_sql_table", "read_xml", "read_clipboard",
    "read_fwf", "read_sas", "read_stata", "read_gbq", "read_hdf",
    "read_orc", "read_spss", "load", "loads", "loadtxt", "genfromtxt",
    "fromfile", "to_pickle", "to_csv", "to_excel", "to_json", "to_parquet",
    "to_sql", "to_hdf", "to_feather", "to_clipboard", "save", "savetxt",
})

# 安全的 builtins 子集（给 exec 的 globals 用）
def _guarded_import(name: str, globals=None, locals=None, fromlist=(), level=0):
    """受控 __import__：运行时再校验一次模块名（纵深防御，防 AST 绕过）。

    import 语句在 exec 时会调用 builtins.__import__，必须提供它才能让
    `import pandas` 这类白名单导入工作。这里在运行时再次检查根模块，
    即使将来 AST 校验有遗漏，非白名单模块也会被这一层挡住。
    """
    root = (name or "").split(".")[0]
    if level or root not in _ALLOWED_IMPORT_ROOTS:
        raise ImportError(f"不允许导入模块：{name}")
    return __import__(name, globals, locals, fromlist, level)


_SAFE_BUILTINS: dict[str, Any] = {
    "__import__": _guarded_import,
    "abs": abs, "all": all, "any": any, "bool": bool, "bytes": bytes,
    "dict": dict, "enumerate": enumerate, "filter": filter, "float": float,
    "format": format, "frozenset": frozenset, "int": int, "isinstance": isinstance,
    "issubclass": issubclass, "iter": iter, "len": len, "list": list,
    "map": map, "max": max, "min": min, "next": next, "print": print,
    "range": range, "repr": repr, "reversed": reversed, "round": round,
    "set": set, "slice": slice, "sorted": sorted, "str": str, "sum": sum,
    "tuple": tuple, "zip": zip, "True": True, "False": False, "None": None,
    # 异常类型（捕获用）
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "KeyError": KeyError, "ZeroDivisionError": ZeroDivisionError,
    "IndexError": IndexError, "RuntimeError": RuntimeError,
}

# 允许的 AST 节点（fail-closed：不在列表里的一律拒绝）
_ALLOWED_NODES = (
    ast.Module, ast.Expr, ast.Assign, ast.AugAssign, ast.AnnAssign,
    ast.Name, ast.Load, ast.Store, ast.Del,
    ast.Constant,  # 涵盖数字/字符串/字节/None/Ellipsis（3.8+ 统一为 Constant）
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.MatMult, ast.LShift, ast.RShift, ast.BitOr, ast.BitAnd, ast.BitXor,
    ast.Invert, ast.UAdd, ast.USub, ast.Not,
    ast.And, ast.Or, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Is, ast.IsNot, ast.In, ast.NotIn,
    ast.Call, ast.keyword, ast.Attribute, ast.Subscript, ast.Slice,
    ast.List, ast.Tuple, ast.Set, ast.Dict,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
    ast.comprehension,
    ast.If, ast.IfExp, ast.For, ast.While, ast.Break, ast.Continue,
    ast.Import, ast.ImportFrom, ast.alias,
    ast.FunctionDef, ast.AsyncFunctionDef, ast.Return, ast.Lambda, ast.arguments,
    ast.arg, ast.Try, ast.ExceptHandler, ast.Raise, ast.Assert, ast.With,
    ast.withitem, ast.Pass,
    ast.JoinedStr, ast.FormattedValue,  # f-string
)

class CodeRejected(ValueError):
    """代码未通过安全校验。"""


def _validate_code(code: str) -> ast.Module:
    """AST 白名单校验；任何不合规都抛 CodeRejected。"""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise CodeRejected(f"代码语法错误：{exc}") from exc

    for node in ast.walk(tree):
        # 1) 节点类型白名单
        if not isinstance(node, _ALLOWED_NODES):
            raise CodeRejected(f"不允许的语法节点：{type(node).__name__}")

        # 1.5) 防止死循环：while 的条件不能是字面真值（True/非零数字）。
        # exec 在线程池里跑，无法硬超时 kill；拒绝 `while True` 这类无界循环，
        # 有界循环（while i < 10）和 for 遍历 DataFrame 仍可用。
        if isinstance(node, ast.While):
            cond = node.test
            if isinstance(cond, ast.Constant) and bool(cond.value):
                raise CodeRejected("不允许 while True / while 1 这类无界循环（防止超时卡死）")

        # 2) import 白名单
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in _ALLOWED_IMPORT_ROOTS:
                    raise CodeRejected(f"不允许导入模块：{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in _ALLOWED_IMPORT_ROOTS:
                raise CodeRejected(f"不允许从模块导入：{node.module}")
            if node.level:  # 相对导入
                raise CodeRejected("不允许相对导入")

        # 3) 危险名字（直接 Name 或 attribute）
        elif isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise CodeRejected(f"不允许使用：{node.id}")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise CodeRejected(f"不允许访问私有属性：{node.attr}")
            if node.attr in ("__class__", "__globals__", "__builtins__", "__subclasses__"):
                raise CodeRejected(f"不允许访问：{node.attr}")
            # 安全边界：pandas/numpy 的 IO 入口能读宿主机任意文件
            # （pd.read_csv("/etc/hosts") 已实测可越界）。本工具只操作传入的
            # data，禁止代码侧自行读文件/网络；导出走受控的 export 参数。
            if isinstance(node.value, ast.Name) and node.value.id in ("pd", "pandas", "np", "numpy", "pl", "polars"):
                if node.attr in _FORBIDDEN_LIB_ATTRS:
                    raise CodeRejected(f"不允许调用 IO 接口：{node.value.id}.{node.attr}")

        # 4) 格式化字符串 gadget：`'{0.__class__}'.format(...)` 把属性表达式
        # 藏在字符串常量里，ast.walk 只能看到 .format，绕过上面的私有属性检查
        # （已实测可枚举 object 子类）。拒绝带属性/下标参数的 format 调用，
        # f-string 中出现的属性访问同理拒绝。
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
            # 格式字符串是 `.format` 的接收者：'{0.__class__}'.format(1)
            receiver = node.func.value
            if isinstance(receiver, ast.Constant) and isinstance(receiver.value, str):
                if re.search(r"\{[^}]*\.[A-Za-z_]", receiver.value):
                    raise CodeRejected("不允许 format 字符串内含属性表达式（防格式化字符串逃逸）")
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                if any(isinstance(sub, (ast.Attribute, ast.Subscript)) for sub in ast.walk(arg)):
                    raise CodeRejected("不允许 format 带属性/下标参数（防格式化字符串逃逸）")
                # 属性表达式常藏在**格式字符串本身**（'{0.__class__}'.format(1)），
                # ast.walk 只看到 Constant，必须直接扫字符串内容。
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if re.search(r"\{[^}]*\.[A-Za-z_]", arg.value):
                        raise CodeRejected("不允许 format 字符串内含属性表达式（防格式化字符串逃逸）")
        if isinstance(node, ast.JoinedStr):
            for value in node.values:
                if isinstance(value, ast.FormattedValue) and any(
                    isinstance(sub, ast.Attribute) for sub in ast.walk(value.value)
                ):
                    raise CodeRejected("不允许 f-string 中访问属性（防格式化字符串逃逸）")

    return tree


def _safe_globals() -> dict[str, Any]:
    return {
        "__builtins__": dict(_SAFE_BUILTINS),
        "__name__": "__data_analysis__",
    }


def _capture_exports(ns: dict[str, Any]) -> dict[str, Any]:
    """从执行后的命名空间里挑出 DataFrame/Series，供调用方导出。"""
    exports: dict[str, Any] = {}
    try:
        import pandas as pd
    except ImportError:
        return exports
    for key, value in ns.items():
        if key.startswith("_"):
            continue
        if isinstance(value, (pd.DataFrame, pd.Series)):
            exports[key] = value
    return exports


def _data_to_dataframe(data: str | list | dict) -> Any:
    """把模型传进来的 data 解析成 DataFrame。"""
    import pandas as pd

    if isinstance(data, pd.DataFrame):
        return data
    if isinstance(data, (list, dict)):
        return pd.DataFrame(data)
    if isinstance(data, str):
        text = data.strip()
        if not text:
            raise ValueError("data 不能为空")
        # JSON 优先：以 [ 或 { 开头就按 JSON 解析（JSON 文本里也可能带换行，
        # 不能靠换行误判成 CSV）。解析失败再退回 CSV。
        if text[0] in "[{":
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"data 看起来是 JSON 但解析失败：{exc}") from exc
            if isinstance(parsed, list):
                return pd.DataFrame(parsed)
            if isinstance(parsed, dict):
                # 支持 {列名: [值...]} 与单个对象两种形式
                try:
                    return pd.DataFrame(parsed)
                except Exception:
                    return pd.DataFrame([parsed])
            raise ValueError("data 必须是 JSON 数组/对象或 CSV 文本")
        # CSV（表头 + 逗号/制表符分隔）
        if "\n" in text or "," in text or "\t" in text:
            sep = "\t" if "\t" in text.splitlines()[0] else ","
            return pd.read_csv(io.StringIO(text), sep=sep)
        raise ValueError("无法识别的 data 格式（需要 JSON 数组或 CSV）")
    raise ValueError("无法识别的 data 格式")


def register_dataframe_tools(registry: ToolRegistry) -> None:
    @registry.tool(
        display_name="代码数据分析",
        timeout_seconds=60,
        side_effect=False,
    )
    def analyze_with_pandas(
        code: str,
        data: str = "",
        export: str = "",
        filename: str = "analysis",
    ) -> dict[str, Any]:
        """用 Python 代码对数据做灵活的统计分析（内置 pandas / numpy / scipy）。

        与预设分析工具 analyze_data 的区别：这里由你**写代码**实现任意分析逻辑，
        适合分组聚合、透视、清洗、时间序列、统计检验等复杂场景。

        可用库：pandas（pd）、numpy（np）、scipy、math、statistics、json、re、datetime。
        **不可 import 其他库，不可读写文件/网络/系统命令**（安全沙箱限制）。

        用法约定：
        - data：要分析的数据，JSON 数组字符串（如 '[{"部门":"销售","金额":100}]'）
          或 CSV 文本；会在执行前解析为 DataFrame 并注入为变量 `df`。
        - code：Python 代码，可直接用 df / pd / np / math 等；用 print() 输出结果。
        - export（可选）：要把结果导出成文件时，设为 'csv' / 'excel' / 'json'。
          导出对象取代码中名为 `result` 的 DataFrame/Series（没有则用 df）。
        - filename（可选）：导出文件名（不含扩展名）。

        示例：
          code = "out = df.groupby('部门')['金额'].agg(['sum','mean']).round(2)\\nprint(out)"
          data = '[{"部门":"销售","金额":100},{"部门":"技术","金额":200}]'

        :param code: 要执行的分析代码
        :param data: 输入数据（JSON/CSV 字符串）
        :param export: 导出格式：csv / excel / json，留空不导出
        :param filename: 导出文件名（不含扩展名）
        """
        result: dict[str, Any] = {
            "ok": False,
            "stdout": "",
            "error": None,
            "exports": [],
            "export_dir": None,
            "truncated": False,
        }

        # 1) 安全校验（fail-closed）
        try:
            tree = _validate_code(code)
        except CodeRejected as exc:
            result["error"] = {
                "type": "CodeRejected",
                "message": str(exc),
                "hint": "只允许数据处理相关的 import（pandas/numpy/scipy/math/statistics/...）；"
                        "禁止文件/网络/系统操作与私有属性访问。",
            }
            return result

        # 2) 准备数据并注入命名空间
        ns = _safe_globals()
        try:
            df = _data_to_dataframe(data) if data else None
        except Exception as exc:  # noqa: BLE001
            result["error"] = {"type": "DataError", "message": f"解析 data 失败：{exc}"}
            return result
        if df is not None:
            ns["df"] = df

        # 3) 捕获 stdout
        buf = io.StringIO()
        import contextlib

        exec_error: str | None = None
        try:
            with contextlib.redirect_stdout(buf):
                exec(compile(tree, "<data_analysis>", "exec"), ns)  # noqa: S102 - AST 白名单已校验
        except Exception as exc:  # noqa: BLE001
            exec_error = f"{type(exc).__name__}: {exc}"
            logger.info("数据分析代码执行失败：%s", exec_error)

        stdout = buf.getvalue()
        # 输出截断（防止超大表格打爆 SSE）
        max_chars = 8000
        if len(stdout) > max_chars:
            stdout = stdout[:max_chars]
            result["truncated"] = True
        result["stdout"] = stdout

        if exec_error:
            result["error"] = {"type": "ExecutionError", "message": exec_error}
            return result

        # 4) 导出（用户选择支持）
        export = (export or "").strip().lower().lstrip(".")
        if export:
            if export not in ("csv", "excel", "json"):
                result["error"] = {
                    "type": "ExportError",
                    "message": "export 只支持 csv / excel / json",
                }
                return result
            try:
                from app.core.data_path import current_workspace_dir

                ws = current_workspace_dir(create=True)
                if ws is None:
                    result["error"] = {
                        "type": "ExportError",
                        "message": "当前没有会话工作区，无法导出文件。请在对话中使用本工具。",
                    }
                    return result
                out_dir = ws / "outputs"
                out_dir.mkdir(parents=True, exist_ok=True)

                # 文件名净化：只保留文件名本身，防路径穿越
                stem = re.sub(r"[^A-Za-z0-9._-]", "_", (filename or "analysis").strip())
                stem = stem.replace("\\", "/").rsplit("/", 1)[-1].lstrip(".") or "analysis"
                if stem.lower().endswith((".csv", ".xlsx", ".json")):
                    stem = stem.rsplit(".", 1)[0]

                obj = ns.get("result")
                if obj is None or not hasattr(obj, "to_" + ("excel" if export == "excel" else export)):
                    obj = ns.get("df")
                if obj is None:
                    result["error"] = {
                        "type": "ExportError",
                        "message": "没有可导出的 DataFrame。请先定义 df 或 result 变量。",
                    }
                    return result

                suffix = ".xlsx" if export == "excel" else f".{export}"
                out_path = out_dir / f"{stem}{suffix}"
                if export == "csv":
                    obj.to_csv(out_path, index=False)
                elif export == "excel":
                    obj.to_excel(out_path, index=False)
                else:
                    obj.to_json(out_path, orient="records", force_ascii=False, indent=2)

                result["exports"] = [{
                    "filename": out_path.name,
                    "path": str(out_path),
                    "format": export,
                    "size_bytes": out_path.stat().st_size,
                }]
                result["export_dir"] = str(out_dir)
            except Exception as exc:  # noqa: BLE001
                result["error"] = {
                    "type": "ExportError",
                    "message": f"导出失败：{exc}",
                }
                return result

        result["ok"] = True
        return result
