from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root() -> None:
    response = client.get("/")

    assert response.status_code == 200
    # conftest 将 ENVIRONMENT 注入为 test；与 settings 保持一致而不是硬编码
    from app.core.config import get_settings

    assert response.json()["environment"] == get_settings().environment


def test_health_check() -> None:
    response = client.get("/api/v1/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
