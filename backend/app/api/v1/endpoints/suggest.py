"""输入补全 API"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.db.models import UserModel
from app.services.cache_service import get_cache_service

router = APIRouter(prefix="/agent", tags=["Agent"])


class PolishPromptRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000, description="待润色的原始提示词")


class PolishPromptResponse(BaseModel):
    polished: str = Field(..., description="润色后的提示词")
    original: str = Field(..., description="原文（便于前端取消时还原）")
    changed: bool = Field(..., description="是否与原文不同")


@router.get("/suggest", summary="输入补全建议")
async def get_suggestions(
    q: str = Query(..., min_length=2, max_length=200, description="用户输入的前缀"),
    limit: int = Query(default=5, ge=1, le=10, description="返回数量"),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """根据用户输入前缀，返回历史输入建议。

    优先匹配当前用户的输入，不足时补充全局热门输入。
    """
    cache = get_cache_service()

    # 先搜当前用户的
    user_suggestions = await cache.suggest_input(current_user.id, q, limit=limit)

    # 不足时补充全局的
    remaining = limit - len(user_suggestions)
    global_suggestions = []
    if remaining > 0:
        global_suggestions = await cache.suggest_global(q, limit=remaining)

    # 合并去重
    seen = set()
    suggestions = []
    for s in user_suggestions + global_suggestions:
        if s not in seen:
            seen.add(s)
            suggestions.append(s)

    return {"suggestions": suggestions[:limit]}


@router.post("/polish-prompt", response_model=PolishPromptResponse, summary="提示词润色")
async def polish_prompt(
    request: PolishPromptRequest,
    current_user: UserModel = Depends(get_current_user),
) -> PolishPromptResponse:
    """分析用户意图并把原始提示词改写为更可执行的长提示词。

    失败（如上游超时/报错）时返回 502，前端提示"润色失败"并保留原文。
    """
    from app.services.prompt_polish_service import polish_prompt as _polish

    try:
        result = await _polish(request.text, user_id=current_user.id)
    except Exception as exc:  # noqa: BLE001 —— 统一转 502，原始提示词不丢
        import logging

        logging.getLogger("agent.suggest").warning(
            "polish prompt failed: user=%s error=%s", current_user.id, exc
        )
        raise HTTPException(status_code=502, detail="提示词润色失败，请稍后重试") from exc

    return PolishPromptResponse(
        polished=result["polished"],
        original=result["original"],
        changed=result["changed"],
    )
