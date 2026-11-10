"""网站产物链路的三个回归。

## 1. metadata_json 撞 TEXT 上限导致整轮不落库

MySQL 上 `agent_sessions.metadata_json` 原本是 TEXT（64KB），而它存的是
session.metadata 完整 JSON —— 其中 action_log 随会话长度线性增长。
实测某会话已达 59KB，再聊几轮就撞顶：

    pymysql.err.DataError: (1406, "Data too long for column 'metadata_json'")

后果不是「元数据没存上」这么轻：save_meta 与 _persist_session_messages
在同一段 try 里顺序执行，前者抛错让后者整轮不执行 —— 用户看到「模型说了话
但界面没内容」，刷新后只剩思考，工具链也断在中间。

## 2. 部署一次出现两个待审批

deploy_website 既是 HITL 审批工具，执行时又会自己创建部署审批单
（website_deploys.status=pending）。同一个动作被批两次。

## 3. 历史消息时间戳丢失

后端只返回 role/content 等，没有 created_at；前端靠
parseInt(message.id) 从流式 id 抠时间，历史消息 id 是 "backend-0"，
parseInt 得到 NaN → 时间整块消失。
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ── 1. 长文本列 ──────────────────────────────────────────────

def test_longtext_migration_covers_metadata_json():
    """0023 迁移必须覆盖 agent_sessions.metadata_json。"""
    src = Path("alembic/versions/0023_longtext_metadata.py").read_text(encoding="utf-8")
    assert '("agent_sessions", "metadata_json")' in src
    # 只在 MySQL 执行（SQLite 的 TEXT 无长度上限）
    assert 'dialect.name != "mysql"' in src
    # 幂等：已是 LONGTEXT 就跳过
    assert "LONG" in src and "MEDIUM" in src


def test_save_meta_failure_does_not_block_message_persist():
    """save_meta 抛错时，消息落库仍要执行。

    这是本次「没有输出内容」的直接原因：两步共用一个 try，前者失败后者
    整轮跳过。消息是用户可见产出，元数据只是内部状态，不该被后者拖垮。
    """
    from app.services.agent import orchestrator

    src = Path(orchestrator.__file__).read_text(encoding="utf-8")
    # 定位 produce_events 的 finally 段
    idx = src.find("saving meta for session")
    assert idx > 0
    segment = src[idx : idx + 2000]
    # save_meta 必须被单独的 try 包住，且 catch 之后继续往下走
    assert "save_meta failed" in segment, "save_meta 没有独立异常处理"
    assert "_persist_session_messages" in segment
    # 关键顺序：消息落库在 save_meta 的 except 之后
    assert segment.index("save_meta failed") < segment.index("_persist_session_messages")


# ── 2. 部署重复审批 ──────────────────────────────────────────

def test_deploy_website_does_not_require_hitl():
    """deploy_website 不该走 HITL —— 它自己会创建部署审批单。

    否则用户点一次「部署」，后台出现两个待审批：一个「允许调用工具」，
    一个「批准上线」，管理员点完一个又来一个。
    """
    from app.services.tool_config_service import DEFAULT_MODE_TOOLS

    for mode, tools in DEFAULT_MODE_TOOLS.items():
        entry = tools.get("deploy_website")
        if entry is not None:
            assert entry["requires_approval"] is False, (
                f"mode={mode} 的 deploy_website 仍在走 HITL 审批"
            )


def test_deploy_website_approval_upgrade_clears_legacy_rows():
    """已存库的 requires_approval=True 要被一次性清掉。

    只改默认值不够：存量行不会自动跟随，用户会继续看到两个待审批。
    """
    from app.services.agent_profile_service import AgentProfileService

    src = Path(AgentProfileService.__module__.replace(".", "/") + ".py")
    # 模块文件路径解析（__module__ 是 app.services.agent_profile_service）
    actual = Path(__file__).resolve().parents[1] / "app" / "services" / "agent_profile_service.py"
    text = actual.read_text(encoding="utf-8")
    assert "_upgrade_deploy_website_approval" in text
    assert "deploy_website" in text
    # 必须真的调用，否则只是死代码
    assert text.count("_upgrade_deploy_website_approval") >= 2


# ── 3. 时间戳 ────────────────────────────────────────────────

def test_storage_exposes_message_timestamps():
    """要有按顺序返回落库时间的方法（wuwei 的 Message 对象没有 created_at）。"""
    from app.services.session_storage import DatabaseAgentStorage

    assert hasattr(DatabaseAgentStorage, "load_message_timestamps")


def test_messages_endpoint_returns_created_at():
    """序列化必须带 created_at，否则前端只能靠 parseInt(id) 猜。"""
    from app.api.v1.endpoints.agent import get_session_messages

    import inspect

    src = inspect.getsource(get_session_messages)
    assert "created_at" in src
    assert "load_message_timestamps" in src


# ── 4. action_log 瘦身 ──────────────────────────────────────

def test_slim_action_log_drops_tool_call_arguments():
    """action_log 必须去掉完整 tool_calls 参数。

    上游 `agent_runner.py:607` 每步都存
    `data={"tool_calls": [tc.model_dump(mode="json") ...]}` ——
    模型写一个文件，整份 CSS/JS/HTML 都进去了。实测一个 31 条的会话占
    54KB（metadata 其余字段加起来才 2.4KB），最终把 MySQL TEXT 撑爆。

    这份数据**没有任何读取方**（上游只写不读，本项目也不读 entries），
    是纯负担。
    """
    from wuwei.runtime.action_log import ActionLog

    from app.services.session_storage import _slim_action_log

    big_css = "a{color:red}" * 5000
    log = ActionLog()
    log.append(
        run_id="r1", agent="s1", step=0, kind="llm", summary="写样式表",
        data={"tool_calls": [{
            "id": "c1", "type": "function",
            "function": {"name": "write_text_file", "arguments": {"content": big_css}},
        }]},
    )
    import json

    slim = _slim_action_log(log.to_dict())
    entry = slim["entries"][0]

    # 完整参数必须消失
    assert "tool_calls" not in entry["data"]
    assert big_css not in json.dumps(slim, ensure_ascii=False)
    # 但审计信息要留住
    assert entry["data"]["tool_names"] == ["write_text_file"]
    for field in ("run_id", "agent", "step", "kind", "digest", "timestamp"):
        assert field in entry
    # 压缩比：60KB 量级降到百字节级
    assert len(json.dumps(slim, ensure_ascii=False)) < 1000


def test_slim_action_log_caps_entries_and_summary():
    """条目数与单条 summary 都要有上限，否则仍会随会话无限增长。"""
    from wuwei.runtime.action_log import ActionLog

    from app.services.session_storage import _slim_action_log

    log = ActionLog()
    for i in range(120):
        log.append(run_id="r", agent="s", step=i, kind="tool", summary="x" * 5000)

    slim = _slim_action_log(log.to_dict())
    entries = slim["entries"]
    assert len(entries) == 60, "条目数未截断"
    assert all(len(e["summary"]) <= 601 for e in entries), "summary 未截断"
    # 保留的是**最近**的，不是最早的
    assert entries[-1]["step"] == 119


def test_slim_action_log_preserves_non_dict_shapes():
    """异常输入不能崩（历史 checkpoint 可能是裸 dict / 空结构）。"""
    from app.services.session_storage import _slim_action_log

    assert _slim_action_log({}) == {}
    assert _slim_action_log({"entries": None}) == {"entries": None}
    assert _slim_action_log({"entries": []}) == {"entries": []}
    # 非 dict 条目被跳过而不是抛异常
    assert _slim_action_log({"entries": ["garbage", None]})["entries"] == []
