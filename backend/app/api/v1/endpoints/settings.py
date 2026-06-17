from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.db.models import SystemSettingModel, UserModel

router = APIRouter(prefix="/settings", tags=["Settings"])


class LdapSettingResponse(BaseModel):
    ldap_enabled: bool


class LdapSettingUpdate(BaseModel):
    ldap_enabled: bool


@router.get("/ldap", response_model=LdapSettingResponse)
def get_ldap_setting(
    _: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LdapSettingResponse:
    row = db.scalar(
        select(SystemSettingModel).where(SystemSettingModel.key == "ldap_enabled")
    )
    return LdapSettingResponse(ldap_enabled=(row is not None and row.value == "true"))


@router.put("/ldap", response_model=LdapSettingResponse)
def update_ldap_setting(
    request: LdapSettingUpdate,
    _: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LdapSettingResponse:
    value = "true" if request.ldap_enabled else "false"
    row = db.scalar(
        select(SystemSettingModel).where(SystemSettingModel.key == "ldap_enabled")
    )
    if row is None:
        row = SystemSettingModel(key="ldap_enabled", value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()
    return LdapSettingResponse(ldap_enabled=request.ldap_enabled)
