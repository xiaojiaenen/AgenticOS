"""
会话数据迁移脚本 — 在一台机器上导出指定会话，在另一台机器上导入。

用法:
  # 导出会话到 JSON 文件
  uv run python scripts/migrate_session.py export <session_id> [输出文件路径]

  # 从 JSON 文件导入会话
  uv run python scripts/migrate_session.py import <json文件路径> --target-user-id <用户ID>

  # 列出所有可用的会话（查看 session_id）
  uv run python scripts/migrate_session.py list

示例:
  uv run python scripts/migrate_session.py list
  uv run python scripts/migrate_session.py export abc-123 ./my_session.json
  uv run python scripts/migrate_session.py import ./my_session.json --target-user-id 1
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.models import (
    AgentMessageModel,
    AgentSessionModel,
    AgentUsageEventModel,
    PptArtifactModel,
)
from app.db.session import SessionLocal, init_db


# ─────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────


def export_session(session_id: str, output_path: Path | None = None) -> dict[str, Any]:
    """Export a single session + all related data to a portable dict, and optionally write to file."""
    db = SessionLocal()
    try:
        session = db.query(AgentSessionModel).filter(AgentSessionModel.session_id == session_id).first()
        if not session:
            print(f"❌ 未找到会话: {session_id}")
            sys.exit(1)

        messages = db.query(AgentMessageModel).filter(AgentMessageModel.session_id == session_id).order_by(AgentMessageModel.created_at).all()
        usage_events = db.query(AgentUsageEventModel).filter(AgentUsageEventModel.session_id == session_id).all()
        ppt_artifacts = db.query(PptArtifactModel).filter(PptArtifactModel.session_id == session_id).all()

        export: dict[str, Any] = {
            "version": 1,
            "exported_at": datetime.now().isoformat(),
            "session": {
                "session_id": session.session_id,
                "user_id": session.user_id,
                "agent_profile_id": session.agent_profile_id,
                "system_prompt": session.system_prompt,
                "max_steps": session.max_steps,
                "parallel_tool_calls": session.parallel_tool_calls,
                "summary": session.summary,
                "metadata_json": session.metadata_json,
                "last_usage_json": session.last_usage_json,
                "last_latency_ms": session.last_latency_ms,
                "last_llm_calls": session.last_llm_calls,
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "updated_at": session.updated_at.isoformat() if session.updated_at else None,
            },
            "messages": [
                {
                    "id": msg.id,
                    "message_json": msg.message_json,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                }
                for msg in messages
            ],
            "usage_events": [
                {
                    "user_id": ev.user_id,
                    "agent_profile_id": ev.agent_profile_id,
                    "model_name": ev.model_name,
                    "response_mode": ev.response_mode,
                    "input_tokens": ev.input_tokens,
                    "output_tokens": ev.output_tokens,
                    "total_tokens": ev.total_tokens,
                    "llm_calls": ev.llm_calls,
                    "tool_calls": ev.tool_calls,
                    "tool_names_json": ev.tool_names_json,
                    "latency_ms": ev.latency_ms,
                    "created_at": ev.created_at.isoformat() if ev.created_at else None,
                }
                for ev in usage_events
            ],
            "ppt_artifacts": [
                {
                    "artifact_id": art.artifact_id,
                    "title": art.title,
                    "slide_count": art.slide_count,
                    "deck_json": art.deck_json,
                    "preview_html": art.preview_html,
                    "metadata_json": art.metadata_json,
                    "created_at": art.created_at.isoformat() if art.created_at else None,
                }
                for art in ppt_artifacts
            ],
        }

        # Counts
        export["_meta"] = {
            "message_count": len(export["messages"]),
            "usage_event_count": len(export["usage_events"]),
            "ppt_artifact_count": len(export["ppt_artifacts"]),
        }

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"✅ 已导出会话 {session_id} → {output_path}")
            print(f"   消息: {len(export['messages'])} 条, "
                  f"用量记录: {len(export['usage_events'])} 条, "
                  f"PPT 制品: {len(export['ppt_artifacts'])} 个")
        else:
            print(json.dumps(export, ensure_ascii=False, indent=2))

        return export

    finally:
        db.close()


# ─────────────────────────────────────────────
# Import
# ─────────────────────────────────────────────


def import_session(json_path: Path, target_user_id: int) -> None:
    """Import a session from a JSON export file into the target database."""
    if not json_path.exists():
        print(f"❌ 文件不存在: {json_path}")
        sys.exit(1)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    session_data = data["session"]

    # Validate version
    version = data.get("version", 0)
    if version < 1:
        print("❌ 不支持的导出格式版本")
        sys.exit(1)

    db = SessionLocal()
    try:
        # 1. Check if session already exists
        existing = db.query(AgentSessionModel).filter(
            AgentSessionModel.session_id == session_data["session_id"]
        ).first()
        if existing:
            print(f"⚠️  会话 {session_data['session_id']} 已存在于目标数据库，跳过导入")
            return

        # 2. Check if target user exists
        from app.db.models import UserModel
        user = db.query(UserModel).filter(UserModel.id == target_user_id).first()
        if not user:
            print(f"❌ 目标用户 ID {target_user_id} 不存在")
            print("   先用 'uv run python scripts/migrate_session.py list-users' 查看可用的用户")
            sys.exit(1)

        # 3. Check agent_profile_id mapping (optional — nullable)
        new_agent_profile_id: int | None = session_data.get("agent_profile_id")
        if new_agent_profile_id is not None:
            from app.db.models import AgentProfileModel
            profile = db.query(AgentProfileModel).filter(AgentProfileModel.id == new_agent_profile_id).first()
            if not profile:
                print(f"⚠️  源机器的 agent_profile_id={new_agent_profile_id} 在目标机器上不存在，将设为 null")
                new_agent_profile_id = None

        # 4. Insert agent_session
        # Use session_data but override user_id and possibly agent_profile_id
        new_session = AgentSessionModel(
            session_id=session_data["session_id"],
            user_id=target_user_id,
            agent_profile_id=new_agent_profile_id,
            system_prompt=session_data["system_prompt"],
            max_steps=session_data["max_steps"],
            parallel_tool_calls=session_data["parallel_tool_calls"],
            summary=session_data.get("summary"),
            metadata_json=session_data.get("metadata_json", "{}"),
            last_usage_json=session_data.get("last_usage_json", "{}"),
            last_latency_ms=session_data.get("last_latency_ms", 0),
            last_llm_calls=session_data.get("last_llm_calls", 0),
        )
        db.add(new_session)
        db.flush()  # Get any generated defaults if needed

        # 5. Insert messages
        for msg_data in data["messages"]:
            new_msg = AgentMessageModel(
                session_id=session_data["session_id"],
                message_json=msg_data["message_json"],
                # created_at is auto-set by default
            )
            db.add(new_msg)

        # 6. Insert usage events (skip the auto-increment id, let DB assign)
        for ev_data in data["usage_events"]:
            new_ev = AgentUsageEventModel(
                user_id=target_user_id,
                agent_profile_id=ev_data.get("agent_profile_id"),
                session_id=session_data["session_id"],
                model_name=ev_data["model_name"],
                response_mode=ev_data.get("response_mode", "general"),
                input_tokens=ev_data["input_tokens"],
                output_tokens=ev_data["output_tokens"],
                total_tokens=ev_data["total_tokens"],
                llm_calls=ev_data["llm_calls"],
                tool_calls=ev_data.get("tool_calls", 0),
                tool_names_json=ev_data.get("tool_names_json", "[]"),
                latency_ms=ev_data["latency_ms"],
            )
            db.add(new_ev)

        # 7. Insert ppt artifacts (skip the auto-increment id, use the original artifact_id)
        for art_data in data["ppt_artifacts"]:
            new_art = PptArtifactModel(
                artifact_id=art_data["artifact_id"],
                session_id=session_data["session_id"],
                title=art_data["title"],
                slide_count=art_data.get("slide_count", 0),
                deck_json=art_data["deck_json"],
                preview_html=art_data["preview_html"],
                metadata_json=art_data.get("metadata_json", "{}"),
            )
            db.add(new_art)

        db.commit()
        meta = data.get("_meta", {})
        print(f"✅ 已导入会话 {session_data['session_id']} (用户 ID: {target_user_id})")
        print(f"   消息: {meta.get('message_count', len(data['messages']))} 条, "
              f"用量记录: {meta.get('usage_event_count', len(data['usage_events']))} 条, "
              f"PPT 制品: {meta.get('ppt_artifact_count', len(data['ppt_artifacts']))} 个")
        print(f"   目标用户: {user.name} ({user.email})")

    except Exception as e:
        db.rollback()
        print(f"❌ 导入失败: {e}")
        raise
    finally:
        db.close()


# ─────────────────────────────────────────────
# List
# ─────────────────────────────────────────────


def list_sessions() -> None:
    """List all sessions in the database."""
    db = SessionLocal()
    try:
        sessions = db.query(AgentSessionModel).order_by(AgentSessionModel.created_at.desc()).all()
        if not sessions:
            print("📭 数据库中没有会话记录")
            return

        print(f"📋 共 {len(sessions)} 个会话:")
        print(f"   {'会话 ID':<40} {'用户 ID':<8} {'摘要':<40} {'创建时间'}")
        print(f"   {'─'*40} {'─'*8} {'─'*40} {'─'*24}")
        for s in sessions:
            summary = (s.summary or "")[:38]
            created = s.created_at.isoformat() if s.created_at else "N/A"
            print(f"   {s.session_id:<40} {str(s.user_id or 'N/A'):<8} {summary:<40} {created}")
    finally:
        db.close()


def list_users() -> None:
    """List all users in the database (for import target selection)."""
    db = SessionLocal()
    try:
        from app.db.models import UserModel
        users = db.query(UserModel).order_by(UserModel.id).all()
        if not users:
            print("📭 数据库中没有用户")
            return

        print(f"👥 共 {len(users)} 个用户:")
        print(f"   {'ID':<6} {'邮箱':<40} {'名称':<20} {'角色':<10}")
        print(f"   {'─'*6} {'─'*40} {'─'*20} {'─'*10}")
        for u in users:
            print(f"   {u.id:<6} {u.email:<40} {u.name:<20} {u.role:<10}")
    finally:
        db.close()


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────


def main() -> None:
    init_db()

    parser = argparse.ArgumentParser(
        description="会话数据迁移工具 — 导出/导入单个会话到另一台机器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    list_parser = subparsers.add_parser("list", help="列出所有可导出的会话")
    list_parser.add_argument("--users", action="store_true", help="列出所有用户（查看导入目标 ID）")

    # export
    export_parser = subparsers.add_parser("export", help="导出会话到 JSON 文件")
    export_parser.add_argument("session_id", help="要导出的会话 ID")
    export_parser.add_argument("output", nargs="?", default=None, help="输出文件路径（默认输出到终端）")

    # import
    import_parser = subparsers.add_parser("import", help="从 JSON 文件导入会话")
    import_parser.add_argument("input", help="JSON 文件路径")
    import_parser.add_argument("--target-user-id", type=int, required=True, help="目标机器上的用户 ID")

    args = parser.parse_args()

    if args.command == "list":
        if args.users:
            list_users()
        else:
            list_sessions()

    elif args.command == "export":
        export_session(args.session_id, Path(args.output) if args.output else None)

    elif args.command == "import":
        import_session(Path(args.input), args.target_user_id)


if __name__ == "__main__":
    main()
