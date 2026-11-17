"""产物事件通道：把本轮产出的 artifact 描述累积起来，供落库挂 metadata。

**为什么需要这个模块**（用户报的三个症状的同一个根因）：

``artifact_ready`` 一直只作为 SSE 事件下发，**从未落库**。于是刷新会话
（或从作品库重进）后，前端只能从历史消息里读回文字、思考、工具链、A2UI、
图表 —— 唯独读不到产物标识。缺少 artifactId 的连锁后果：

* **导出 PPTX 静默失败** —— ``handleExport`` 在 ``artifact.artifactId``
  为空时直接 return，用户点了没反应也没有报错；
* **主题切换无效** —— ``handleThemeChange`` 同理 early-return；
* **侧边栏是裸 iframe** —— ``IdeSidebar`` 的 PPT 标签只渲染预览 HTML，
  主题/导出/编辑按钮长在 ``PptArtifactPanel`` 上，而侧栏没复用它。

A2UI 与图表早就走「工具产出 → session_artifacts 累积 → 挂 metadata →
前端重载时恢复」这条路（见 ``chart_events.py`` 的踩坑记录），产物缺了
同一套。本模块补上，并复用 ``session_artifacts``（Redis 持久化，
进程重启不丢；Redis 不可用时退进程内 dict）。

与 chart 的差别：图表是**一轮多张**（列表），产物是**一类一个**（dict）。
同一轮里 ppt 与 document 不会同时出现（模式互斥），但为了以后扩展
（比如一轮里既出网站又出封面图），仍按 kind 合并且保留最新一条。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("agenticos.artifact")

#: 产物类别 → 落库时用的键名（与前端 Message 上的 xxxArtifact 字段对应）
_KIND_TO_KEY = {
    "ppt": "ppt",
    "website": "website",
    "document": "document",
    "sheet": "sheet",
}


def record(kind: str, payload: dict[str, Any], session_id: str) -> None:
    """记录一条产物描述。同一 kind 只保留最新（后写覆盖先写）。

    在 ``_finalize_artifact`` / ``_create_ppt_artifact`` 之后调用 ——
    也就是确定产物真的建成了（有 artifact_id）再记，避免把质量门
    拒掉的半成品写进 metadata。
    """
    key = _KIND_TO_KEY.get(kind)
    if not key or not session_id or not payload:
        return
    artifact_id = payload.get("artifact_id") or payload.get("project_slug")
    if not artifact_id:
        # 没有标识的产物无法在刷新后回源，记了也没用
        logger.debug("skip recording artifact without id: kind=%s", kind)
        return
    try:
        from app.services import session_artifacts

        # 用单元素列表承载「最新一条」，读取时取最后一个 —— 复用 LIST
        # 的原子追加语义，不必新造一套 KV 读写。
        session_artifacts.append("artifact", session_id, [{"kind": kind, "payload": payload}])
    except Exception:  # noqa: BLE001 -- 采集失败不该影响产物返回
        logger.warning("record artifact failed (kind=%s)", kind, exc_info=True)


def accumulated(session_id: str) -> dict[str, dict[str, Any]]:
    """读取该会话累积的产物，按 kind 折叠成 ``{kind: payload}``（后者胜）。

    返回空 dict 表示本轮没有产物 —— 调用方据此跳过挂 metadata。
    """
    if not session_id:
        return {}
    try:
        from app.services import session_artifacts

        items = session_artifacts.read_all("artifact", session_id)
    except Exception:  # noqa: BLE001
        logger.warning("read accumulated artifacts failed", exc_info=True)
        return {}

    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        payload = item.get("payload")
        if isinstance(kind, str) and isinstance(payload, dict):
            merged[kind] = payload
    return merged


def clear_accumulated(session_id: str) -> None:
    """落库后清空，避免同一产物重复写入后续消息。"""
    if not session_id:
        return
    try:
        from app.services import session_artifacts

        session_artifacts.clear("artifact", session_id)
    except Exception:  # noqa: BLE001
        logger.warning("clear accumulated artifacts failed", exc_info=True)


def reset_session(session_id: str) -> None:
    """新一轮 run 开始时清空，避免上一轮的产物串到这一轮。

    必须在 run 入口调用（与 chart_events.reset_session 并列）：
    Redis 在线时累积跨请求存活，不清就会把上一轮的 artifactId 挂到
    本轮的新消息上，用户点开看到的是旧产物。
    """
    clear_accumulated(session_id)
