"""Check baitong auto-login readiness + embedding model + chrome (ASCII only)."""
import os
import sys

sys.path.insert(0, "/app/backend")

# 1. playwright browsers
for base in ("/root/.cache/ms-playwright", "/ms-playwright", os.path.expanduser("~/.cache/ms-playwright")):
    if os.path.isdir(base):
        print("pw dir:", base, "->", os.listdir(base))
    else:
        print("pw dir missing:", base)
try:
    from playwright.async_api import async_playwright  # noqa: F401

    print("playwright package: installed")
except Exception as exc:  # noqa: BLE001
    print("playwright package MISSING:", exc)

# 2. hf cache (embedding model)
for base in ("/app/data/hf-cache/hub", "/opt/agenticos/data/hf-cache/hub"):
    if os.path.isdir(base):
        print("hf hub:", base, "->", sorted(os.listdir(base))[:5])

# 3. baitong provider + credential/cookie state (ASCII output only)
from app.db.session import create_db_session  # noqa: E402
from sqlalchemy import select  # noqa: E402
from app.db.models import LlmProviderModel, LlmProviderCredentialModel  # noqa: E402

with create_db_session() as db:
    rows = db.scalars(select(LlmProviderModel)).all()
    for r in rows:
        print(
            f"provider #{r.id} {r.slug} type={r.provider_type} enabled={r.enabled} "
            f"base={r.base_url}"
        )
        creds = db.scalars(
            select(LlmProviderCredentialModel).where(LlmProviderCredentialModel.provider_id == r.id)
        ).all()
        for c in creds:
            cookie_len = len(c.cookie_encrypted or "") if getattr(c, "cookie_encrypted", None) else 0
            has_pw = bool(getattr(c, "password_encrypted", None) or getattr(c, "password_encrypted", None))
            print(
                f"  cred #{c.id} user={c.username} active={getattr(c, 'is_active', None)} "
                f"cookie_len={cookie_len} has_pw={has_pw} "
                f"expire={getattr(c, 'cookie_expire_at', None)} updated={getattr(c, 'updated_at', None)}"
            )
