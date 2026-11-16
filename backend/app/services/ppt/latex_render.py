"""LaTeX 公式渲染（本地 KaTeX，离线可用）。

**定位**：给 agent 一个「公式能不能用」的校验器 + 渲染器，避免它写出
KaTeX 解析不了的 LaTeX 却一路生成到幻灯片里（用户最终看到一坨原始
LaTeX 源码）。

**为什么不用上游 ppt-master 的原生公式方案**：上游把 LaTeX 编译成
PowerPoint 原生可编辑公式（``a14:m > m:oMath``），那条路需要约 8000 行
LaTeX→OMML 编译器，且深度耦合它自己的导出管线。内网离线环境也不该依赖
codecogs / quicklatex 这类外网渲染服务。

**本模块的做法**：调本地 Node 的 KaTeX（前端构建已依赖 ``katex``，
runtime 镜像自带 node）把 LaTeX 渲染成 HTML。

- 用在校验：``validate_latex`` 给出可读错误，agent 可据此修公式；
- 用在预览：前端本来就有 KaTeX，公式在浏览器里能正确排版；
- 导出 PPTX 时：公式按普通文本处理（保底可读）。要原生可编辑公式，
  需要另做 LaTeX→OMML 移植，不在本次范围。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("agent.ppt.latex")

#: stdin: [{"latex": str, "display": bool}]
#: stdout: {"results": [{"ok": bool, "latex": str, "html"?: str, "error"?: str}]}
_RENDER_SCRIPT = r"""
const katexPath = process.env.KATEX_PATH;
let katex;
try {
  katex = require(katexPath || 'katex');
} catch (e) {
  process.stdout.write(JSON.stringify({ error: 'katex_not_found: ' + String((e && e.message) || e) }));
  process.exit(0);
}
let raw = '';
process.stdin.on('data', (c) => { raw += c; });
process.stdin.on('end', () => {
  let items = [];
  try { items = JSON.parse(raw || '[]'); } catch (e) { items = []; }
  const results = items.map(({ latex, display }) => {
    try {
      const html = katex.renderToString(latex, {
        displayMode: !!display,
        throwOnError: true,
        output: 'html',
        strict: 'ignore',
      });
      return { ok: true, latex, html };
    } catch (e) {
      return { ok: false, latex, error: String((e && e.message) || e) };
    }
  });
  process.stdout.write(JSON.stringify({ results }));
});
"""


def _katex_module_dir() -> Path | None:
    """定位 katex 模块（开发环境在 frontend/node_modules，容器内看 /app）。"""
    candidates = [
        Path(__file__).resolve().parents[4] / "frontend" / "node_modules" / "katex",
        Path("/app/frontend/node_modules/katex"),
        Path("/app/data/node_modules/katex"),
    ]
    for c in candidates:
        if (c / "package.json").exists():
            return c
    return None


def _fail_all(items: list[dict], error: str) -> list[dict]:
    return [{"ok": False, "latex": it.get("latex", ""), "error": error} for it in items]


def render_latex(items: list[dict]) -> list[dict]:
    """渲染一批 LaTeX。

    ``items``: ``[{"latex": "...", "display": bool}, ...]``
    返回同序结果，每条含 ``ok`` 与 ``html`` 或 ``error``。

    node 缺失 / KaTeX 加载失败时返回全部 ``ok=False``（带原因），
    调用方据此提示模型，而不是让整页生成失败。
    """
    if not items:
        return []

    node = shutil.which("node")
    if node is None:
        return _fail_all(items, "当前环境没有 node，无法渲染公式")

    env = dict(os.environ)
    katex_dir = _katex_module_dir()
    if katex_dir is not None:
        env["KATEX_PATH"] = str(katex_dir)

    try:
        proc = subprocess.run(
            [node, "-e", _RENDER_SCRIPT],
            input=json.dumps(items, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return _fail_all(items, "公式渲染超时")
    except Exception as exc:  # noqa: BLE001 -- 渲染失败不该抛给调用方
        logger.warning("latex render failed: %s", exc, exc_info=True)
        return _fail_all(items, f"公式渲染失败: {exc}")

    if proc.returncode != 0:
        return _fail_all(items, f"node 退出码 {proc.returncode}: {(proc.stderr or '')[:200]}")

    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return _fail_all(items, "渲染器返回非 JSON")

    if payload.get("error"):
        return _fail_all(items, str(payload["error"]))

    return payload.get("results") or _fail_all(items, "渲染器无返回")


def validate_latex(latex: str) -> tuple[bool, str]:
    """校验一条 LaTeX 能否被 KaTeX 解析。返回 ``(ok, 错误信息)``。"""
    text = (latex or "").strip()
    if not text:
        return False, "公式为空"
    results = render_latex([{"latex": text, "display": True}])
    if not results:
        return False, "渲染器无返回"
    r = results[0]
    return (True, "") if r.get("ok") else (False, str(r.get("error") or "未知错误"))
