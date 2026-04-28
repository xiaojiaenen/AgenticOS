from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import UserModel
from app.db.session import create_db_session
from app.main import app
from app.services.tool_config_service import DEFAULT_MODE_TOOLS, ToolConfigService

client = TestClient(app)


def cleanup_test_users(*emails: str) -> None:
    with create_db_session() as db:
        db.execute(delete(UserModel).where(UserModel.email.in_(emails)))
        db.commit()


def create_admin_token(email: str) -> str:
    with create_db_session() as db:
        admin = UserModel(
            email=email,
            name="Tool Admin",
            password_hash=hash_password("password-123"),
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

    settings = get_settings()
    return create_access_token(
        {"sub": str(admin.id), "email": admin.email, "role": admin.role},
        secret=settings.auth_secret_key,
        expires_in_seconds=settings.auth_token_expire_minutes * 60,
    )


def test_admin_can_read_and_update_mode_tool_config() -> None:
    email = f"tool-admin-{uuid4().hex}@example.com"
    try:
        token = create_admin_token(email)
        headers = {"Authorization": f"Bearer {token}"}

        get_response = client.get("/api/v1/tool-config", headers=headers)
        assert get_response.status_code == 200
        payload = get_response.json()
        assert {mode["mode"] for mode in payload["modes"]} == {"general", "ppt", "website"}
        assert {item["name"] for item in payload["catalog"]} >= {"time", "file"}

        update_response = client.put(
            "/api/v1/tool-config/modes/ppt",
            headers=headers,
            json={
                "tools": [
                    {"tool_name": "time", "enabled": True, "requires_approval": False},
                    {"tool_name": "file", "enabled": True, "requires_approval": True},
                ],
            },
        )
        assert update_response.status_code == 200
        ppt_mode = next(mode for mode in update_response.json()["modes"] if mode["mode"] == "ppt")
        by_tool = {tool["tool_name"]: tool for tool in ppt_mode["tools"]}
        assert by_tool["time"]["enabled"] is True
        assert by_tool["file"]["enabled"] is True
        assert by_tool["file"]["requires_approval"] is True
    finally:
        ToolConfigService().update_mode(
            "ppt",
            [
                {"tool_name": tool_name, **settings}
                for tool_name, settings in DEFAULT_MODE_TOOLS["ppt"].items()
            ],
        )
        cleanup_test_users(email)
