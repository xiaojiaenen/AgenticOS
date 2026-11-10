"""个人年度报告（Wrapped）端点。

- ``GET /wrapped/years``：当前用户有用量数据的年份。
- ``GET /wrapped/{year}``：当前用户某年的年度回顾。
- ``POST /admin/wrapped/send``：管理员手动触发邮件群发（可指定年份/单个用户，
  便于部署后验证；正式群发由 1 月 1 日 cron 自动完成）。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.core.timezone import app_now
from app.db.models import UserModel
from app.services.wrapped_service import compute_wrapped, years_with_data

router = APIRouter(prefix="/wrapped", tags=["Wrapped"])
admin_router = APIRouter(prefix="/admin/wrapped", tags=["admin-wrapped"])


@router.get("/years")
def wrapped_years(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    years = years_with_data(db, current_user.id)
    return {"years": years, "current_year": app_now().year}


@router.get("/{year}")
def get_wrapped(
    year: int,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if year < 2000 or year > app_now().year + 1:
        raise HTTPException(status_code=422, detail="年份无效")
    return compute_wrapped(db, current_user.id, year)


@admin_router.post("/send")
async def admin_send_wrapped(
    year: int | None = Query(default=None, description="留空=上一年"),
    user_id: int | None = Query(default=None, description="留空=全体活跃用户；指定=仅该用户"),
    admin: UserModel = Depends(require_admin),
) -> dict:
    from app.services.notification_service import dispatch_annual_wrapped

    target_year = year if year is not None else app_now().year - 1
    result = await dispatch_annual_wrapped(target_year, user_id=user_id)
    return {"year": target_year, **result}
