"""网站项目技术栈探测。

同一个技术栈判定被两处消费，历史上两处各写一套且都不准：

- ``agent/artifacts.py``：按「有没有 ``.vue`` / ``.jsx`` 文件」猜 → 用户把
  Vue 组件改名成 ``.js``、或用 ``.tsx`` 写 React，就判错；
- ``tools/website_tools.py``：压根不判，硬编码 ``"vanilla"`` → 后台部署管理
  里 react / vue 站点全显示成 Vanilla。

统一到一处，判定顺序按**可信度**从高到低：

1. ``package.json`` 的 ``dependencies`` —— 模板自带、技术栈一定在这里声明，
   是唯一的事实来源；
2. 源码文件后缀 —— 只在 ``package.json`` 缺失或被改坏时兜底。

``dependencies`` 里同时有 vue 和 react 时（少见，例如混用），
按后缀命中数多的那个决定；仍然平手则按 vue → react → vanilla 的顺序取先者。
"""

from __future__ import annotations

import json
from pathlib import Path

VANILLA = "vanilla"
VUE = "vue"
REACT = "react"

# 后缀 → 技术栈。仅用于 package.json 不可用时兜底。
_SUFFIX_HINTS: dict[str, str] = {
    ".vue": VUE,
    ".jsx": REACT,
    ".tsx": REACT,
}

# 依赖名 → 技术栈。键是 package.json 里的包名。
_DEP_HINTS: dict[str, str] = {
    "vue": VUE,
    "vue-router": VUE,
    "pinia": VUE,
    "@vitejs/plugin-vue": VUE,
    "react": REACT,
    "react-dom": REACT,
    "react-router-dom": REACT,
    "@vitejs/plugin-react": REACT,
}

# 判定平手时的优先级。
_PRIORITY = {VUE: 3, REACT: 2, VANILLA: 1}


def _stack_from_package_json(project_dir: Path) -> str | None:
    """从 package.json 的 dependencies 判定技术栈；判不出返回 None。"""
    pkg = project_dir / "package.json"
    if not pkg.is_file():
        return None
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    deps: dict[str, str] = {}
    for field in ("dependencies", "devDependencies"):
        section = data.get(field)
        if isinstance(section, dict):
            deps.update({k: v for k, v in section.items() if isinstance(k, str)})

    hits = {
        _DEP_HINTS[name]
        for name in deps
        if name in _DEP_HINTS
    }
    if not hits:
        return None
    if len(hits) == 1:
        return hits.pop()
    # 混用：按优先级取更具体的一个（vue > react > vanilla）。
    return max(hits, key=lambda s: _PRIORITY.get(s, 0))


def _stack_from_suffixes(project_dir: Path) -> str | None:
    """按源码后缀兜底判定。"""
    counts: dict[str, int] = {}
    for suffix, stack in _SUFFIX_HINTS.items():
        try:
            n = sum(1 for p in project_dir.rglob(f"*{suffix}") if p.is_file())
        except OSError:
            continue
        if n:
            counts[stack] = counts.get(stack, 0) + n
    if not counts:
        return None
    return max(counts, key=lambda s: (counts[s], _PRIORITY.get(s, 0)))


def detect_stack(project_dir: Path | str) -> str:
    """判定项目技术栈，返回 ``vanilla`` / ``vue`` / ``react``。

    判不出时返回 ``vanilla``（模板默认值），不会抛异常 —— 部署记录里的
    stack 只是展示字段，不该因为它把整个部署流程搞失败。
    """
    path = Path(project_dir)
    if not path.is_dir():
        return VANILLA

    return (
        _stack_from_package_json(path)
        or _stack_from_suffixes(path)
        or VANILLA
    )
