"""LLMOps 端点：运行追踪 / 消息反馈 / Prompt 版本 / 发布为应用 / 评测。

路由规划：
- /agent/traces*            运行追踪（登录；admin 全量，普通用户仅本人）
- /agent/feedback           消息标注（👍/👎 + 备注）
- /agent/profiles/*/versions*  Prompt 版本历史与回滚
- /agent/profiles/*/publish    一键发布为独立应用
- /agent/evals/*            评测数据集与运行
- /public/agents/{slug}*    公开聊天页 / 嵌入 widget（无需登录）
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy import delete, select

from app.api.deps import get_current_user
from app.api.v1.endpoints.agent import _format_sse
from app.core.config import get_settings
from app.db.models import (
    AgentProfileModel,
    AgentProfileVersionModel,
    AgentRunTraceModel,
    EvalCaseModel,
    EvalDatasetModel,
    EvalRunModel,
    UserModel,
)
from app.db.session import create_db_session
from app.schemas.agent import AgentStreamRequest
from app.services.agent import AgentService, get_agent_service
from app.services.agent_profile_service import AgentProfileService
from app.services.trace_recorder import message_fingerprint

_logger = logging.getLogger("llmops.api")

router = APIRouter()


# ────────────────────────── 运行追踪 ──────────────────────────


def _trace_summary(row: AgentRunTraceModel) -> dict[str, Any]:
    return {
        "id": row.id,
        "session_id": row.session_id,
        "user_id": row.user_id,
        "agent_profile_id": row.agent_profile_id,
        "mode": row.mode,
        "status": row.status,
        "text_chars": row.text_chars,
        "reasoning_chars": row.reasoning_chars,
        "tool_calls": row.tool_calls,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "latency_ms": row.latency_ms,
        "error": row.error,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


@router.get("/agent/traces", summary="运行追踪列表")
async def list_traces(
    session_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    from sqlalchemy import func

    with create_db_session() as db:
        stmt = select(AgentRunTraceModel).order_by(AgentRunTraceModel.started_at.desc())
        count_stmt = select(func.count(AgentRunTraceModel.id))
        if current_user.role != "admin":
            stmt = stmt.where(AgentRunTraceModel.user_id == current_user.id)
            count_stmt = count_stmt.where(AgentRunTraceModel.user_id == current_user.id)
        if session_id:
            stmt = stmt.where(AgentRunTraceModel.session_id == session_id)
            count_stmt = count_stmt.where(AgentRunTraceModel.session_id == session_id)
        total = db.scalar(count_stmt) or 0
        rows = db.scalars(stmt.offset(offset).limit(limit)).all()
    return {"items": [_trace_summary(r) for r in rows], "total": total}


@router.get("/agent/traces/{trace_id}", summary="运行追踪详情（步骤瀑布）")
async def get_trace(trace_id: int, current_user: UserModel = Depends(get_current_user)) -> dict:
    with create_db_session() as db:
        row = db.get(AgentRunTraceModel, trace_id)
    if row is None:
        raise HTTPException(status_code=404, detail="trace not found")
    if current_user.role != "admin" and row.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权查看该追踪")
    data = _trace_summary(row)
    data["steps"] = json.loads(row.steps_json or "[]")
    return data


# ────────────────────────── 消息标注 ──────────────────────────


class FeedbackRequest(dict):
    pass


@router.post("/agent/feedback", summary="对一条 AI 回复点赞/点踩")
async def submit_feedback(
    payload: dict[str, Any],
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    from app.core.timezone import app_now
    from app.db.models import AgentMessageFeedbackModel
    from app.db.session import create_db_session

    session_id = str(payload.get("session_id") or "").strip()
    rating = str(payload.get("rating") or "").strip()
    if not session_id or rating not in ("up", "down"):
        raise HTTPException(status_code=422, detail="session_id 与 rating(up|down) 必填")
    with create_db_session() as db:
        row = AgentMessageFeedbackModel(
            session_id=session_id,
            user_id=current_user.id,
            message_index=int(payload.get("message_index") or 0),
            message_fingerprint=str(payload.get("fingerprint") or "")[:64] or None,
            rating=rating,
            comment=str(payload.get("comment") or "")[:2000] or None,
            created_at=app_now(),
        )
        db.add(row)
        db.commit()
        return {"success": True, "id": row.id}


@router.get("/agent/feedback", summary="消息标注列表（admin 全量）")
async def list_feedback(
    session_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    from sqlalchemy import func

    from app.db.models import AgentMessageFeedbackModel
    from app.db.session import create_db_session

    with create_db_session() as db:
        stmt = select(AgentMessageFeedbackModel).order_by(
            AgentMessageFeedbackModel.created_at.desc()
        )
        count_stmt = select(func.count(AgentMessageFeedbackModel.id))
        if current_user.role != "admin":
            stmt = stmt.where(AgentMessageFeedbackModel.user_id == current_user.id)
            count_stmt = count_stmt.where(AgentMessageFeedbackModel.user_id == current_user.id)
        if session_id:
            stmt = stmt.where(AgentMessageFeedbackModel.session_id == session_id)
            count_stmt = count_stmt.where(AgentMessageFeedbackModel.session_id == session_id)
        total = db.scalar(count_stmt) or 0
        rows = db.scalars(stmt.limit(limit)).all()
    return {
        "items": [
            {
                "id": r.id,
                "session_id": r.session_id,
                "user_id": r.user_id,
                "message_index": r.message_index,
                "fingerprint": r.message_fingerprint,
                "rating": r.rating,
                "comment": r.comment,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": total,
    }


# ────────────────────────── Prompt 版本 ──────────────────────────


def _load_profile_owned(profile_id: int, current_user: UserModel) -> AgentProfileModel:
    with create_db_session() as db:
        profile = db.get(AgentProfileModel, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="agent profile not found")
    if current_user.role != "admin" and profile.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权管理该智能体")
    return profile


@router.post("/agent/profiles/{profile_id}/versions/save", summary="保存当前配置为版本")
async def save_version(
    profile_id: int,
    payload: dict[str, Any] | None = None,
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    _load_profile_owned(profile_id, current_user)
    version = AgentProfileService().save_profile_version(
        profile_id,
        created_by=current_user.id,
        note=(payload or {}).get("note"),
    )
    if version is None:
        raise HTTPException(status_code=404, detail="agent profile not found")
    return {"success": True, "version": version}


@router.get("/agent/profiles/{profile_id}/versions", summary="版本列表")
async def list_versions(profile_id: int, current_user: UserModel = Depends(get_current_user)) -> dict:
    _load_profile_owned(profile_id, current_user)
    return {"items": AgentProfileService().list_profile_versions(profile_id)}


@router.get("/agent/profiles/{profile_id}/versions/{version}", summary="版本详情")
async def get_version(profile_id: int, version: int, current_user: UserModel = Depends(get_current_user)) -> dict:
    _load_profile_owned(profile_id, current_user)
    data = AgentProfileService().get_profile_version(profile_id, version)
    if data is None:
        raise HTTPException(status_code=404, detail="version not found")
    return data


@router.post("/agent/profiles/{profile_id}/versions/{version}/restore", summary="回滚到指定版本")
async def restore_version(
    profile_id: int, version: int, current_user: UserModel = Depends(get_current_user)
) -> dict:
    _load_profile_owned(profile_id, current_user)
    ok = AgentProfileService().restore_profile_version(profile_id, version)
    if not ok:
        raise HTTPException(status_code=404, detail="version not found")
    return {"success": True}


# ────────────────────────── 发布为应用 ──────────────────────────


def _publish_config_of(profile: AgentProfileModel) -> dict[str, Any]:
    try:
        data = json.loads(profile.publish_config_json or "{}")
    except json.JSONDecodeError:
        data = {}
    return data if isinstance(data, dict) else {}


@router.post("/agent/profiles/{profile_id}/publish", summary="一键发布为独立应用")
async def publish_profile(
    profile_id: int,
    payload: dict[str, Any] | None = None,
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    profile = _load_profile_owned(profile_id, current_user)
    config = _publish_config_of(profile)
    body = payload or {}
    config["title"] = str(body.get("title") or profile.name)[:60]
    config["welcome"] = str(body.get("welcome") or "")[:500]
    access_code = str(body.get("access_code") or "").strip()
    if access_code:
        config["access_code"] = access_code
    elif "access_code" in body:  # 显式传空 = 清除访问码
        config.pop("access_code", None)

    with create_db_session() as db:
        row = db.get(AgentProfileModel, profile_id)
        row.published = True
        if not row.publish_slug:
            row.publish_slug = secrets.token_urlsafe(9)
        row.publish_config_json = json.dumps(config, ensure_ascii=False)
        db.commit()
        slug = row.publish_slug
    return {
        "success": True,
        "slug": slug,
        "chat_url": f"/app/{slug}",
        "widget_url": f"/api/v1/public/agents/{slug}/widget.js",
    }


@router.delete("/agent/profiles/{profile_id}/publish", summary="下线已发布的应用")
async def unpublish_profile(profile_id: int, current_user: UserModel = Depends(get_current_user)) -> dict:
    profile = _load_profile_owned(profile_id, current_user)
    with create_db_session() as db:
        row = db.get(AgentProfileModel, profile_id)
        row.published = False
        db.commit()
    return {"success": True}


@router.get("/agent/profiles/{profile_id}/publish", summary="查看发布状态")
async def publish_status(profile_id: int, current_user: UserModel = Depends(get_current_user)) -> dict:
    profile = _load_profile_owned(profile_id, current_user)
    config = _publish_config_of(profile)
    return {
        "published": profile.published,
        "slug": profile.publish_slug,
        "chat_url": f"/app/{profile.publish_slug}" if profile.publish_slug else None,
        "config": {
            "title": config.get("title", profile.name),
            "welcome": config.get("welcome", ""),
            "has_access_code": bool(config.get("access_code")),
        },
    }


# ────────────────────────── 公开访问（无需登录）──────────────────────────


def _published_agent_by_slug(slug: str) -> tuple[AgentProfileModel, dict[str, Any]]:
    with create_db_session() as db:
        profile = db.scalar(
            select(AgentProfileModel).where(
                AgentProfileModel.publish_slug == slug,
                AgentProfileModel.published.is_(True),
                AgentProfileModel.enabled.is_(True),
            )
        )
    if profile is None:
        raise HTTPException(status_code=404, detail="应用不存在或已下线")
    return profile, _publish_config_of(profile)


@router.get("/public/agents/{slug}", summary="已发布应用信息（公开）")
async def public_agent_info(slug: str) -> dict:
    profile, config = _published_agent_by_slug(slug)
    return {
        "name": config.get("title") or profile.name,
        "avatar": profile.avatar,
        "welcome": config.get("welcome", ""),
        "require_code": bool(config.get("access_code")),
    }


@router.post(
    "/public/agents/{slug}/chat",
    summary="已发布应用对话（SSE，公开）",
    response_class=StreamingResponse,
)
async def public_agent_chat(
    slug: str,
    payload: dict[str, Any],
    agent_service: AgentService = Depends(get_agent_service),
) -> StreamingResponse:
    profile, config = _published_agent_by_slug(slug)
    access_code = config.get("access_code")
    if access_code and str(payload.get("access_code") or "") != access_code:
        raise HTTPException(status_code=403, detail="访问码错误")

    request = AgentStreamRequest(
        message=str(payload.get("message") or "").strip(),
        session_id=payload.get("session_id") or None,
        published_slug=slug,
        max_steps=payload.get("max_steps"),
    )
    if not request.message:
        raise HTTPException(status_code=422, detail="message 必填")

    try:
        agent_service.ensure_ready()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    async def event_stream():
        try:
            async for event in agent_service.stream_chat(request, None):
                yield _format_sse(event["event"], event["data"])
        except Exception as exc:
            _logger.exception("public chat fatal error: slug=%s", slug)
            yield _format_sse("error", {"message": str(exc), "session_id": request.session_id or "(new)"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_WIDGET_TEMPLATE = """(function () {
  if (window.__agenticosAgentLoaded) return;
  window.__agenticosAgentLoaded = true;
  var API = __API_BASE__;
  var SLUG = __SLUG__;
  var style = document.createElement('style');
  style.textContent = [
    '.agos-launcher{position:fixed;right:24px;bottom:24px;z-index:2147483000;width:56px;height:56px;',
    'border-radius:50%;border:none;cursor:pointer;box-shadow:0 8px 24px rgba(0,0,0,.2);',
    'background:#0f172a;color:#fff;font-size:24px;line-height:56px;text-align:center;}',
    '.agos-frame{position:fixed;right:24px;bottom:92px;z-index:2147483000;width:400px;height:600px;',
    'max-height:80vh;max-width:calc(100vw - 32px);border:none;border-radius:16px;',
    'box-shadow:0 12px 40px rgba(0,0,0,.25);display:none;background:#fff;}',
    '.agos-frame.agos-open{display:block;}'
  ].join('');
  document.head.appendChild(style);
  var btn = document.createElement('button');
  btn.className = 'agos-launcher';
  btn.textContent = '💬';
  btn.setAttribute('aria-label', '打开智能助手');
  var frame = document.createElement('iframe');
  frame.className = 'agos-frame';
  frame.src = API + '/app/' + SLUG + '?embed=1';
  frame.allow = 'clipboard-write';
  btn.addEventListener('click', function () {
    frame.classList.toggle('agos-open');
  });
  document.body.appendChild(btn);
  document.body.appendChild(frame);
})();
"""


@router.get("/public/agents/{slug}/widget.js", summary="嵌入脚本（一行引入）")
async def public_agent_widget(slug: str) -> PlainTextResponse:
    _published_agent_by_slug(slug)
    settings = get_settings()
    # widget 以同源相对路径拼 API —— 部署在反代同域时天然同源；
    # 跨域嵌入时由部署方设置 FRONTEND_BASE_URL 生成绝对地址。
    api_base = (settings.frontend_base_url or "").rstrip("/") if hasattr(settings, "frontend_base_url") else ""
    js = (
        _WIDGET_TEMPLATE
        .replace("__API_BASE__", json.dumps(api_base or ""))
        .replace("__SLUG__", json.dumps(slug))
    )
    return PlainTextResponse(
        js,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


# ────────────────────────── 评测 ──────────────────────────


def _load_dataset(dataset_id: int) -> EvalDatasetModel:
    with create_db_session() as db:
        row = db.get(EvalDatasetModel, dataset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return row


@router.get("/agent/evals/datasets", summary="评测数据集列表")
async def list_eval_datasets(current_user: UserModel = Depends(get_current_user)) -> dict:
    with create_db_session() as db:
        rows = db.scalars(
            select(EvalDatasetModel).order_by(EvalDatasetModel.created_at.desc())
        ).all()
        datasets = []
        for row in rows:
            cases = db.scalars(
                select(EvalCaseModel).where(EvalCaseModel.dataset_id == row.id)
            ).all()
            datasets.append({
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "case_count": len(cases),
                "created_at": row.created_at.isoformat() if row.created_at else None,
            })
    return {"items": datasets}


@router.post("/agent/evals/datasets", summary="创建评测数据集")
async def create_eval_dataset(
    payload: dict[str, Any],
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name 必填")
    with create_db_session() as db:
        row = EvalDatasetModel(
            name=name,
            description=str(payload.get("description") or "")[:1000],
            created_by=current_user.id,
        )
        db.add(row)
        db.commit()
        return {"id": row.id, "name": row.name}


@router.delete("/agent/evals/datasets/{dataset_id}", summary="删除评测数据集（级联删除用例）")
async def delete_eval_dataset(dataset_id: int, current_user: UserModel = Depends(get_current_user)) -> dict:
    _load_dataset(dataset_id)
    with create_db_session() as db:
        db.execute(delete(EvalCaseModel).where(EvalCaseModel.dataset_id == dataset_id))
        db.execute(delete(EvalRunModel).where(EvalRunModel.dataset_id == dataset_id))
        db.execute(delete(EvalDatasetModel).where(EvalDatasetModel.id == dataset_id))
        db.commit()
    return {"success": True}


@router.get("/agent/evals/datasets/{dataset_id}", summary="数据集详情（含用例）")
async def get_eval_dataset(dataset_id: int, current_user: UserModel = Depends(get_current_user)) -> dict:
    row = _load_dataset(dataset_id)
    with create_db_session() as db:
        cases = db.scalars(
            select(EvalCaseModel).where(EvalCaseModel.dataset_id == dataset_id)
        ).all()
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "cases": [
            {
                "id": c.id,
                "input": c.input,
                "expected": json.loads(c.expected_json or "{}"),
                "note": c.note,
            }
            for c in cases
        ],
    }


@router.post("/agent/evals/datasets/{dataset_id}/cases", summary="添加评测用例")
async def add_eval_case(dataset_id: int, payload: dict[str, Any], current_user: UserModel = Depends(get_current_user)) -> dict:
    _load_dataset(dataset_id)
    text = str(payload.get("input") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="input 必填")
    expected = payload.get("expected") or {}
    if not isinstance(expected, dict):
        raise HTTPException(status_code=422, detail="expected 必须是对象")
    with create_db_session() as db:
        row = EvalCaseModel(
            dataset_id=dataset_id,
            input=text,
            expected_json=json.dumps(expected, ensure_ascii=False),
            note=str(payload.get("note") or "")[:200] or None,
        )
        db.add(row)
        db.commit()
        return {"id": row.id}


@router.delete("/agent/evals/cases/{case_id}", summary="删除评测用例")
async def delete_eval_case(case_id: int, current_user: UserModel = Depends(get_current_user)) -> dict:
    with create_db_session() as db:
        db.execute(delete(EvalCaseModel).where(EvalCaseModel.id == case_id))
        db.commit()
    return {"success": True}


def _score_case(output: str, expected: dict[str, Any]) -> tuple[bool, str | None]:
    """MVP 评分规则：contains / not_contains。"""
    if not expected:
        return bool(output.strip()), None
    lower = output.lower()
    for keyword in expected.get("contains") or []:
        if str(keyword).lower() not in lower:
            return False, f"输出缺少关键词: {keyword}"
    for keyword in expected.get("not_contains") or []:
        if str(keyword).lower() in lower:
            return False, f"输出包含禁止关键词: {keyword}"
    return True, None


async def _execute_eval(run_id: int, dataset_id: int, profile_id: int, admin: UserModel) -> None:
    """后台执行评测：逐用例跑一轮完整 agent（工具可用），聚合结果与评分。"""
    from app.core.timezone import app_now
    from app.db.session import create_db_session
    from app.services.agent import get_agent_service

    agent_service = get_agent_service()
    results: list[dict[str, Any]] = []

    def _load():
        with create_db_session() as db:
            dataset = db.get(EvalDatasetModel, dataset_id)
            cases = db.scalars(
                select(EvalCaseModel).where(EvalCaseModel.dataset_id == dataset_id)
            ).all()
            return dataset, list(cases)

    try:
        dataset, cases = await asyncio.to_thread(_load)
        total = len(cases)
        for index, case in enumerate(cases):
            expected = json.loads(case.expected_json or "{}")
            session_id = f"eval-{run_id}-{case.id}"
            request = AgentStreamRequest(
                message=case.input,
                session_id=session_id,
                agent_profile_id=profile_id,
                max_steps=10,
            )
            output_parts: list[str] = []
            tool_calls = 0
            error: str | None = None
            started = asyncio.get_event_loop().time()
            try:
                async for event in agent_service.stream_chat(request, admin):
                    et = event.get("event")
                    if et == "delta":
                        output_parts.append(str(event.get("data", {}).get("content") or ""))
                    elif et == "tool_calls":
                        tool_calls += len(event.get("data", {}).get("tool_calls") or [])
                    elif et == "error":
                        error = str(event.get("data", {}).get("message") or "error")
                        break
                    elif et == "done":
                        break
            except Exception as exc:  # noqa: BLE001
                error = repr(exc)[:300]
            output = "".join(output_parts)
            duration_ms = int((asyncio.get_event_loop().time() - started) * 1000)
            passed, reason = _score_case(output, expected)
            if error:
                passed = False
                reason = f"运行出错: {error}"
            results.append({
                "case_id": case.id,
                "input": case.input[:400],
                "output": output[:2000],
                "passed": passed,
                "reason": reason,
                "error": error,
                "duration_ms": duration_ms,
                "tool_calls": tool_calls,
            })
            passed_count = sum(1 for r in results if r["passed"])
            with create_db_session() as db:
                run = db.get(EvalRunModel, run_id)
                run.total = total
                run.passed = passed_count
                run.results_json = json.dumps(results, ensure_ascii=False)
                db.commit()

        with create_db_session() as db:
            run = db.get(EvalRunModel, run_id)
            run.status = "done"
            run.total = len(cases)
            run.passed = sum(1 for r in results if r["passed"])
            run.results_json = json.dumps(results, ensure_ascii=False)
            run.finished_at = app_now()
            db.commit()
    except Exception as exc:  # noqa: BLE001
        _logger.exception("eval run failed")
        with create_db_session() as db:
            run = db.get(EvalRunModel, run_id)
            if run is not None:
                run.status = "error"
                run.error = repr(exc)[:500]
                run.finished_at = app_now()
                db.commit()


@router.post("/agent/evals/datasets/{dataset_id}/run", summary="对指定智能体执行评测")
async def start_eval_run(
    dataset_id: int,
    payload: dict[str, Any],
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可执行评测")
    _load_dataset(dataset_id)
    profile_id = int(payload.get("profile_id") or 0)
    with create_db_session() as db:
        if db.get(AgentProfileModel, profile_id) is None:
            raise HTTPException(status_code=404, detail="agent profile not found")
        run = EvalRunModel(
            dataset_id=dataset_id,
            profile_id=profile_id,
            status="running",
            created_by=current_user.id,
        )
        db.add(run)
        db.commit()
        run_id = run.id

    asyncio.create_task(
        _execute_eval(run_id, dataset_id, profile_id, current_user)
    )
    return {"run_id": run_id, "status": "running"}


@router.get("/agent/evals/runs", summary="评测运行列表")
async def list_eval_runs(
    dataset_id: int | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员")
    with create_db_session() as db:
        stmt = select(EvalRunModel).order_by(EvalRunModel.created_at.desc()).limit(limit)
        if dataset_id:
            stmt = stmt.where(EvalRunModel.dataset_id == dataset_id)
        rows = db.scalars(stmt).all()
    return {
        "items": [
            {
                "id": r.id,
                "dataset_id": r.dataset_id,
                "profile_id": r.profile_id,
                "status": r.status,
                "total": r.total,
                "passed": r.passed,
                "error": r.error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            }
            for r in rows
        ]
    }


@router.get("/agent/evals/runs/{run_id}", summary="评测运行详情（含每用例结果）")
async def get_eval_run(run_id: int, current_user: UserModel = Depends(get_current_user)) -> dict:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员")
    with create_db_session() as db:
        run = db.get(EvalRunModel, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {
        "id": run.id,
        "dataset_id": run.dataset_id,
        "profile_id": run.profile_id,
        "status": run.status,
        "total": run.total,
        "passed": run.passed,
        "results": json.loads(run.results_json or "[]"),
        "error": run.error,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }
