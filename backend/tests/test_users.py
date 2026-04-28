from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import UserModel
from app.db.session import create_db_session
from app.main import app

client = TestClient(app)


def cleanup_test_users(*emails: str) -> None:
    with create_db_session() as db:
        db.execute(delete(UserModel).where(UserModel.email.in_(emails)))
        db.commit()


def create_admin_token(email: str) -> str:
    with create_db_session() as db:
        admin = UserModel(
            email=email,
            name="Admin User",
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


def test_admin_user_crud() -> None:
    admin_email = f"admin-{uuid4().hex}@example.com"
    user_email = f"managed-{uuid4().hex}@example.com"
    updated_email = f"managed-updated-{uuid4().hex}@example.com"

    try:
        token = create_admin_token(admin_email)
        headers = {"Authorization": f"Bearer {token}"}

        create_response = client.post(
            "/api/v1/users",
            headers=headers,
            json={
                "email": user_email,
                "name": "Managed User",
                "password": "password-123",
                "role": "user",
                "is_active": True,
            },
        )
        assert create_response.status_code == 201
        user_id = create_response.json()["id"]

        list_response = client.get("/api/v1/users", headers=headers, params={"search": "Managed"})
        assert list_response.status_code == 200
        assert any(item["id"] == user_id for item in list_response.json()["items"])

        update_response = client.patch(
            f"/api/v1/users/{user_id}",
            headers=headers,
            json={"email": updated_email, "name": "Updated User", "role": "admin", "is_active": False},
        )
        assert update_response.status_code == 200
        update_payload = update_response.json()
        assert update_payload["email"] == updated_email
        assert update_payload["role"] == "admin"
        assert update_payload["is_active"] is False

        status_response = client.patch(
            f"/api/v1/users/{user_id}/status",
            headers=headers,
            json={"is_active": True},
        )
        assert status_response.status_code == 200
        assert status_response.json()["is_active"] is True

        delete_response = client.delete(f"/api/v1/users/{user_id}", headers=headers)
        assert delete_response.status_code == 204

        get_response = client.get(f"/api/v1/users/{user_id}", headers=headers)
        assert get_response.status_code == 404
    finally:
        cleanup_test_users(admin_email, user_email, updated_email)
