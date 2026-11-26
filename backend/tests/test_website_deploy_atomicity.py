"""网站发布原子性回归。

失败补偿：拷贝中途失败时旧目录必须保留，deploy_url/access_token 不得被提前
提交（原实现先清空目标目录再逐项拷贝，失败 → 线上空白 + DB 记 failed +
deploy_url 已提交）。
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, WebsiteDeployModel
from app.services.website_deploy_service import WebsiteDeployService, _public_url


def _setup(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path/'deploy.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return engine, SessionLocal


def test_failed_copy_keeps_old_directory_and_rolls_back_db_fields(tmp_path, monkeypatch):
    import app.services.website_deploy_service as svc_mod

    engine, SessionLocal = _setup(tmp_path)
    serve = tmp_path / "serve"
    serve.mkdir()
    monkeypatch.setattr(svc_mod, "NGINX_SERVE_ROOT", serve)
    monkeypatch.setattr(svc_mod.WebsiteDeployService, "_issue_access_token", lambda self, d: "old-token")

    service = WebsiteDeployService(session_factory=SessionLocal)

    # 构造源 dist
    dist = tmp_path / "websites" / "demo" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("new", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("new js", encoding="utf-8")

    # 旧目标目录 + 旧 DB 字段
    old_target = serve / "demo"
    old_target.mkdir(parents=True)
    (old_target / "index.html").write_text("OLD", encoding="utf-8")

    with SessionLocal() as db:
        deploy = WebsiteDeployModel(
            session_id="s-deploy-test",
            project_slug="demo",
            stack="vite",
            dist_path=str(dist),
            visibility="private",
            status="approved",
            requested_by=1,
            short_code="abc12345",
            deploy_url="/s/old-code/",
            access_token="old-token",
        )
        db.add(deploy)
        db.commit()
        deploy_id = deploy.id

    # 让拷贝中途抛错（模拟部分文件已落到 staging 后失败）
    def flaky(src, dst, *args, **kwargs):
        raise RuntimeError("simulated copy failure")

    with patch.object(svc_mod.shutil, "copytree", side_effect=flaky), \
         patch.object(svc_mod.shutil, "copy2", side_effect=flaky):
        with pytest.raises(RuntimeError, match="simulated copy failure"):
            service._execute_deploy(
                SessionLocal().get(WebsiteDeployModel, deploy_id)
            )

    # 旧目录仍在，内容未变
    assert (old_target / "index.html").read_text() == "OLD"
    # 没有残留 staging / backup 目录
    assert not any("staging" in p.name or "backup" in p.name for p in serve.iterdir())

    # DB 字段未被提前改（_execute_deploy 抛错前不写 deploy_url/access_token）
    with SessionLocal() as db:
        row = db.get(WebsiteDeployModel, deploy_id)
        assert row.deploy_url == "/s/old-code/"
        assert row.access_token == "old-token"
        assert row.status == "approved"
