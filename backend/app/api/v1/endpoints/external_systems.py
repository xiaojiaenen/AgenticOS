"""Endpoints for managing external systems (admin) and user integrations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.db.models import UserModel
from app.schemas.external_systems import (
    OpenApiImportRequest,
    ExternalApiCreateRequest,
    ExternalApiListResponse,
    ExternalApiTestRequest,
    ExternalApiTestResponse,
    ExternalApiUpdateRequest,
    ExternalSystemCreateRequest,
    ExternalSystemListResponse,
    ExternalSystemUpdateRequest,
    ExternalSystemResponse,
    ExternalApiDetail,
    ProfileExternalSystemRef,
    UserConnectionCreateRequest,
    UserConnectionListResponse,
    UserConnectionResponse,
)
from app.services import audit_service
from app.services.external_system_service import ExternalSystemService, set_ext_user_id

# ── Admin router ────────────────────────────────────────────────────────────

admin_router = APIRouter(prefix="/external-systems", tags=["External Systems"])


@admin_router.get("", response_model=ExternalSystemListResponse)
def list_systems(
    admin: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ExternalSystemListResponse(items=ExternalSystemService(db).list_systems())


@admin_router.post("", response_model=ExternalSystemResponse, status_code=status.HTTP_201_CREATED)
def create_system(
    body: ExternalSystemCreateRequest,
    http_request: Request,
    admin: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
):
    created = ExternalSystemService(db).create_system(body, user_id=admin.id)
    audit_service.record_request(
        db, http_request, action="external_system.create", actor=admin,
        resource_type="external_system", resource_id=created.get("id"),
        detail={"name": body.name, "base_url": body.base_url},
    )
    return created


@admin_router.get("/{system_id}", response_model=ExternalSystemResponse)
def get_system(
    system_id: int,
    admin: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return ExternalSystemService(db).get_system(system_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="外部系统不存在")


@admin_router.patch("/{system_id}", response_model=ExternalSystemResponse)
async def update_system(
    system_id: int,
    body: ExternalSystemUpdateRequest,
    http_request: Request,
    admin: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        updated = await ExternalSystemService(db).update_system(system_id, body)
    except KeyError:
        raise HTTPException(status_code=404, detail="外部系统不存在")
    # 只记改动的字段名，值里可能含凭据
    audit_service.record_request(
        db, http_request, action="external_system.update", actor=admin,
        resource_type="external_system", resource_id=system_id,
        detail={"fields": sorted(body.model_dump(exclude_none=True).keys())},
    )
    return updated


@admin_router.delete("/{system_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_system(
    system_id: int,
    http_request: Request,
    admin: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        ExternalSystemService(db).delete_system(system_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="外部系统不存在")
    audit_service.record_request(
        db, http_request, action="external_system.delete", actor=admin,
        resource_type="external_system", resource_id=system_id,
    )


# ── API CRUD (admin, nested under system) ───────────────────────────────────


@admin_router.get("/{system_id}/apis", response_model=ExternalApiListResponse)
def list_apis(
    system_id: int,
    admin: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ExternalApiListResponse(items=ExternalSystemService(db).list_apis(system_id))


@admin_router.post("/{system_id}/apis", response_model=ExternalApiDetail, status_code=status.HTTP_201_CREATED)
def create_api(
    system_id: int,
    body: ExternalApiCreateRequest,
    http_request: Request,
    admin: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        created = ExternalSystemService(db).create_api(system_id, body)
    except KeyError:
        raise HTTPException(status_code=404, detail="外部系统不存在")
    audit_service.record_request(
        db, http_request, action="external_api.create", actor=admin,
        resource_type="external_api",
        resource_id=created.get("id") if isinstance(created, dict) else None,
        detail={"system_id": system_id, "name": getattr(body, "name", None),
                "method": getattr(body, "method", None), "path": getattr(body, "path", None)},
    )
    return created


@admin_router.get("/{system_id}/apis/{api_id}", response_model=ExternalApiDetail)
def get_api(
    system_id: int,
    api_id: int,
    admin: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return ExternalSystemService(db).get_api(api_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="外部接口不存在")


@admin_router.patch("/{system_id}/apis/{api_id}", response_model=ExternalApiDetail)
def update_api(
    system_id: int,
    api_id: int,
    body: ExternalApiUpdateRequest,
    http_request: Request,
    admin: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        updated = ExternalSystemService(db).update_api(api_id, body)
    except KeyError:
        raise HTTPException(status_code=404, detail="外部接口不存在")
    audit_service.record_request(
        db, http_request, action="external_api.update", actor=admin,
        resource_type="external_api", resource_id=api_id,
        detail={"system_id": system_id, "fields": sorted(body.model_dump(exclude_none=True).keys())},
    )
    return updated


@admin_router.delete("/{system_id}/apis/{api_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_api(
    system_id: int,
    api_id: int,
    http_request: Request,
    admin: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        ExternalSystemService(db).delete_api(api_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="外部接口不存在")
    audit_service.record_request(
        db, http_request, action="external_api.delete", actor=admin,
        resource_type="external_api", resource_id=api_id, detail={"system_id": system_id},
    )


@admin_router.post("/{system_id}/apis/{api_id}/test", response_model=ExternalApiTestResponse)
async def test_api(
    system_id: int,
    api_id: int,
    body: ExternalApiTestRequest,
    admin: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
):
    set_ext_user_id(admin.id)
    try:
        return await ExternalSystemService(db).test_api_call(api_id, body.params, body.credential_data)
    except KeyError:
        raise HTTPException(status_code=404, detail="外部接口不存在")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Profile ↔ system association (admin) ────────────────────────────────────


@admin_router.get("/profiles/{profile_id}/systems")
def list_profile_systems(
    profile_id: int,
    admin: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ExternalSystemService(db).list_profile_systems(profile_id)


@admin_router.put("/profiles/{profile_id}/systems", status_code=status.HTTP_200_OK)
def apply_profile_systems(
    profile_id: int,
    body: list[ProfileExternalSystemRef],
    http_request: Request,
    admin: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
):
    refs = [{"system_id": r.system_id, "enabled": r.enabled} for r in body]
    ExternalSystemService(db).apply_profile_systems(profile_id, refs)
    audit_service.record_request(
        db, http_request, action="agent_profile.bind_systems", actor=admin,
        resource_type="agent_profile", resource_id=profile_id,
        detail={"systems": refs},
    )
    return {"ok": True}


# ── User router (integrations) ──────────────────────────────────────────────

router = APIRouter(prefix="/integrations", tags=["Integrations"])


@router.get("/categories")
def list_categories():
    """返回集成分类列表（预设常量，不提供管理 API）。"""
    from app.services.external_system_service import INTEGRATION_CATEGORIES
    return {"items": INTEGRATION_CATEGORIES}


@router.get("", response_model=ExternalSystemListResponse)
def list_integrations(
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ExternalSystemListResponse(items=ExternalSystemService(db).list_published_systems(user_id=user.id))


@router.get("/{system_id}", response_model=ExternalSystemResponse)
def get_integration(
    system_id: int,
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        svc = ExternalSystemService(db)
        sys = svc.get_system(system_id)
        if not sys.get("published"):
            raise HTTPException(status_code=404, detail="集成不存在")
        return sys
    except KeyError:
        raise HTTPException(status_code=404, detail="集成不存在")


@router.post("/{system_id}/connect", response_model=UserConnectionResponse, status_code=status.HTTP_201_CREATED)
def connect_integration(
    system_id: int,
    body: UserConnectionCreateRequest,
    http_request: Request,
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = ExternalSystemService(db).connect_system(user.id, system_id, body.credential_data)
    except KeyError:
        raise HTTPException(status_code=404, detail="集成不存在")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 个人接入第三方凭据是高敏感动作，记审计但不记凭据内容
    audit_service.record_request(
        db, http_request, action="integration.connect", actor=user,
        resource_type="external_system", resource_id=system_id,
    )
    return result


@router.delete("/{system_id}/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_integration(
    system_id: int,
    http_request: Request,
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ExternalSystemService(db).disconnect_system(user.id, system_id)
    audit_service.record_request(
        db, http_request, action="integration.disconnect", actor=user,
        resource_type="external_system", resource_id=system_id,
    )


@router.get("/{system_id}/status", response_model=UserConnectionResponse)
def get_connection_status(
    system_id: int,
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = ExternalSystemService(db).get_user_connection(user.id, system_id)
    if not result:
        raise HTTPException(status_code=404, detail="尚未连接")
    return result


@router.get("/my/connections", response_model=UserConnectionListResponse)
def list_my_connections(
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return UserConnectionListResponse(items=ExternalSystemService(db).list_user_connections(user.id))


# ── OpenAPI import (admin) ──────────────────────────────────────────────────


@admin_router.post("/import-openapi/preview")
async def preview_openapi_import(
    body: OpenApiImportRequest,
    admin: UserModel = Depends(require_admin),
):
    try:
        from app.services.external_system_service import ExternalSystemService as ESS
        preview = await ESS.parse_openapi(body.openapi_json, body.openapi_url)
        return preview
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@admin_router.post("/import-openapi/confirm", status_code=status.HTTP_201_CREATED)
def confirm_openapi_import(
    body: dict,
    http_request: Request,
    admin: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        svc = ExternalSystemService(db)
        result = svc.import_from_openapi_preview(body, admin.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit_service.record_request(
        db, http_request, action="external_system.import_openapi", actor=admin,
        resource_type="external_system",
        resource_id=result.get("id") if isinstance(result, dict) else None,
        detail={"source": "openapi"},
    )
    return result
