"""透明加密上传链路的诊断端点测试。

验证 /files/probe 能正确区分明文与密文，且不落盘。
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _register_and_token() -> tuple[str, str]:
    email = f"probe-{uuid.uuid4().hex}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "name": "Probe Tester", "password": "ProbeTest#2024"},
    )
    assert resp.status_code == 201, resp.text
    return email, resp.json()["access_token"]


def test_probe_detects_plain_ooxml() -> None:
    email, token = _register_and_token()
    try:
        r = client.post(
            "/api/v1/files/probe",
            files={"file": ("排班表.xlsx", b"PK\x03\x04" + b"\x00" * 12, "application/octet-stream")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["kind"] == "plain"
        assert body["head"].startswith("50 4B 03 04")
        assert body["size"] == 16
    finally:
        _cleanup(email)


def test_probe_detects_plain_pdf() -> None:
    email, token = _register_and_token()
    try:
        r = client.post(
            "/api/v1/files/probe",
            files={"file": ("合同.pdf", b"%PDF-1.7\n%\xe2\xe3", "application/pdf")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["kind"] == "plain"
    finally:
        _cleanup(email)


def test_probe_detects_plain_ole2() -> None:
    email, token = _register_and_token()
    try:
        r = client.post(
            "/api/v1/files/probe",
            files={"file": ("旧报表.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "application/vnd.ms-excel")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["kind"] == "plain"
    finally:
        _cleanup(email)


def test_probe_detects_cipher() -> None:
    """模拟 DLP 密文：未知魔数，应判定为 cipher 并给出换宿主/白名单建议。"""
    email, token = _register_and_token()
    try:
        r = client.post(
            "/api/v1/files/probe",
            files={"file": ("加密.xlsx", bytes(range(16)), "application/octet-stream")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "cipher"
        assert "密文" in body["advice"]
        assert body["head"] == "00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F"
    finally:
        _cleanup(email)


def test_probe_empty_file() -> None:
    email, token = _register_and_token()
    try:
        r = client.post(
            "/api/v1/files/probe",
            files={"file": ("空.bin", b"", "application/octet-stream")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["kind"] == "empty"
    finally:
        _cleanup(email)


def test_probe_requires_auth() -> None:
    r = client.post(
        "/api/v1/files/probe",
        files={"file": ("a.xlsx", b"PK\x03\x04", "application/octet-stream")},
    )
    assert r.status_code == 401


def _cleanup(email: str) -> None:
    from sqlalchemy import delete

    from app.db.models import UserModel
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        db.execute(delete(UserModel).where(UserModel.email == email))
        db.commit()
