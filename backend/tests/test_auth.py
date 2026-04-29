from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.models import AuthRateLimitModel, AuthSessionModel, UserModel
from app.db.session import create_db_session
from app.main import app

client = TestClient(app)


def cleanup_test_users(*emails: str) -> None:
    with create_db_session() as db:
        user_ids = db.scalars(select(UserModel.id).where(UserModel.email.in_(emails))).all()
        if user_ids:
            db.execute(delete(AuthSessionModel).where(AuthSessionModel.user_id.in_(user_ids)))
        db.execute(delete(UserModel).where(UserModel.email.in_(emails)))
        db.execute(delete(AuthRateLimitModel))
        db.commit()


def test_register_login_and_me() -> None:
    email = f"user-{uuid4().hex}@example.com"
    password = "password-123"

    try:
        register_response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "name": "Test User", "password": password},
        )
        assert register_response.status_code == 201
        register_payload = register_response.json()
        assert register_payload["user"]["email"] == email
        assert register_payload["access_token"]

        duplicate_response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "name": "Test User", "password": password},
        )
        assert duplicate_response.status_code == 400

        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        me_response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_response.status_code == 200
        assert me_response.json()["email"] == email
    finally:
        cleanup_test_users(email)


def test_login_rejects_bad_password() -> None:
    email = f"user-{uuid4().hex}@example.com"
    try:
        client.post(
            "/api/v1/auth/register",
            json={"email": email, "name": "Test User", "password": "password-123"},
        )

        response = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "wrong-password"},
        )
        assert response.status_code == 401
    finally:
        cleanup_test_users(email)


def test_logout_revokes_token() -> None:
    email = f"user-{uuid4().hex}@example.com"
    password = "password-123"

    try:
        register_response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "name": "Test User", "password": password},
        )
        token = register_response.json()["access_token"]

        logout_response = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert logout_response.status_code == 200

        me_response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_response.status_code == 401
    finally:
        cleanup_test_users(email)


def test_login_rate_limit_blocks_after_repeated_failures() -> None:
    email = f"user-{uuid4().hex}@example.com"
    password = "password-123"

    try:
        client.post(
            "/api/v1/auth/register",
            json={"email": email, "name": "Test User", "password": password},
        )

        attempts = get_settings().auth_rate_limit_max_attempts
        for _ in range(attempts):
            response = client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "wrong-password"},
            )
            assert response.status_code == 401

        blocked_response = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert blocked_response.status_code == 429
    finally:
        cleanup_test_users(email)
