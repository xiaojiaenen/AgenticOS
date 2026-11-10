"""工作流功能级授权回归（feature: use_workflows / view_workflow_runs）。

背景：工作流是近期新增能力，接入 `require_feature` 时不能「升级即断供」——
存量普通用户在没有被显式授权前应保持可用的升级前行为。

语义（本文件全部钉住）：
1. **默认拒绝**：普通用户未被显式授权 → 403（不依赖策略是否「配置过」）；
2. **显式授权后放行**：管理员在权限页授予 feature:use_workflows 即可用；
3. **管理员**：始终放行（enforce_for_user 的 admin 短路）；
4. **无身份**：工具桥按拒绝处理（不能成为绕过端点的后门）。

工具桥与端点必须**同一口径**（否则会出现「界面能跑、对话里被拒」或反过来）。
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.db.models import CasbinRuleModel, UserModel
from app.db.session import create_db_session
from app.core.security import hash_password


def _make_user(email: str, *, role: str = "user") -> int:
    with create_db_session() as db:
        # SQLite 复用被删用户的 id：清掉该 id 上残留的 g 绑定，
        # 否则新用户会「继承」上一个用户的角色（实测把普通用户变成 admin）
        from app.db.models import CasbinRuleModel

        user = UserModel(
            email=email,
            name="Perm Tester",
            password_hash=hash_password("pw-123456"),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        uid = user.id
        db.query(CasbinRuleModel).filter(
            CasbinRuleModel.ptype == "g", CasbinRuleModel.v0 == f"user:{uid}"
        ).delete()
        db.commit()
    from app.services.permission_service import get_permission_service

    get_permission_service().reload()
    return uid


def _load_user(uid: int) -> UserModel:
    with create_db_session() as db:
        return db.get(UserModel, uid)


def _clear_feature_policies(feature: str) -> None:
    """删掉该 feature 的所有显式策略（恢复「未配置」状态）。

    不加主体过滤：测试用户的 id 会被 SQLite 复用，只针对某个 user:<id>
    删会让上一个用例留下的授权恰好命中下一个用例（实测被污染过）。
    """
    target = f"feature:{feature}"
    with create_db_session() as db:
        # **不能**把 v2 == "*" 一起删：那是 `p, admin, *, *, *` 的通配策略，
        # 删掉会让后续所有用例的管理员判定失效（实测把 workflow_api 的
        # 管理员跑批用例全部打成 403）。只删本文件自己授出去的 feature 规则。
        db.execute(
            delete(CasbinRuleModel).where(
                CasbinRuleModel.ptype == "p",
                CasbinRuleModel.v2.in_([target, "feature:*"]),
            )
        )
        db.commit()


def _grant(feature: str = "use_workflows", subject: str = "perm_test_subject", action: str = "read") -> None:

    from app.services.permission_service import get_permission_service as _get

    svc = _get()
    svc.add_policy(subject, "*", f"feature:{feature}", action)
    svc.reload()  # 立即从库重载，避免读到写库前的内存态


@pytest.fixture()
def clean_policies():
    """前后都清空该 feature 的策略，并让 enforcer 立即重载。

    只调 invalidate() 不够：它标记缓存过期，下一个 enforcer 操作才重载；
    若清理写库失败或顺序颠倒，上一个用例授予的策略会泄漏到下一个用例
    （实测过：端点 403 用例被前面的授权用例污染成 200）。
    """
    features = ("use_workflows", "view_workflow_runs")

    def _reset():
        """把这两个 feature 重置成确定状态：仅 admin 锚点，无任何角色/个人授权。

        直接操作库再 reload，以库为唯一事实源 —— Casbin 的 add_policy 在
        内存判定「已存在」时不落库，reload 后会丢失（踩过）。
        """
        from app.db.models import CasbinRuleModel
        from app.services.permission_service import get_permission_service

        svc = get_permission_service()
        svc.reload()
        targets = [f"feature:{f}" for f in features]
        with create_db_session() as db:
            db.execute(
                delete(CasbinRuleModel).where(
                    CasbinRuleModel.ptype == "p",
                    CasbinRuleModel.v2.in_(targets),
                )
            )
            for target in targets:
                db.add(CasbinRuleModel(ptype="p", v0="admin", v1="*", v2=target, v3="read"))
            db.commit()
        svc.reload()

    _reset()
    yield
    _reset()


class TestFeatureGateStrictByDefault:
    def test_regular_user_denied_by_default(self):
        """默认拒绝：普通用户未被显式授权时不能用工作流。

        用独立 feature 名验证「无授权即拒绝」的判定语义 —— 真实
        feature:use_workflows 的策略会被其他测试文件（它们测业务逻辑，
        需要可用环境）授予，在那里断言「拒绝」必然不稳定。
        真实端点的默认拒绝由 TestEndpointGate 用独立用户验证。
        """
        from app.services.permission_service import get_permission_service

        svc = get_permission_service()
        svc.reload()  # 确保读到的是库里的最新策略（不是其他文件留下的内存态）
        uid = _make_user("wf-perm-default-deny@example.com")
        try:
            user = _load_user(uid)
            assert svc.enforce_for_user(user, "read", "feature", "perm_probe_deny") is False
        finally:
            _cleanup_users("wf-perm-default-deny@example.com")

    def test_restricted_features_are_anchored_at_startup(self):
        """启动时为受限功能写入 admin 锚点：保证「已配置」状态成立。"""
        from app.services.permission_service import (
            DEFAULT_RESTRICTED_FEATURES,
            ensure_default_policies,
            get_permission_service,
        )

        ensure_default_policies()
        svc = get_permission_service()
        svc.reload()
        policies = svc.get_policy()
        for feature in DEFAULT_RESTRICTED_FEATURES:
            assert any(
                rule[:3] == ["admin", "*", f"feature:{feature}"] for rule in policies
            ), f"{feature} 缺少 admin 锚点策略"

    def test_configured_feature_denies_ungranted_user(self, clean_policies):
        """一旦被显式配置，未授权的普通用户被拒。"""
        from app.services.permission_service import get_permission_service

        svc = get_permission_service()
        _grant("use_workflows")  # 授给一个不存在的 user 主体，仅让配置「存在」
        assert svc.feature_unconfigured("use_workflows") is False

        uid = _make_user("wf-perm-denied@example.com")
        try:
            user = _load_user(uid)
            assert svc.enforce_for_user(user, "read", "feature", "use_workflows") is False
        finally:
            _cleanup_users("wf-perm-denied@example.com")

    def test_configured_feature_allows_granted_user(self, clean_policies):
        from app.services.permission_service import get_permission_service

        uid = _make_user("wf-perm-granted@example.com")
        try:
            _grant("use_workflows", subject=f"user:{uid}")
            svc = get_permission_service()
            user = _load_user(uid)
            assert svc.feature_unconfigured("use_workflows") is False
            assert svc.enforce_for_user(user, "read", "feature", "use_workflows") is True
        finally:
            _cleanup_users("wf-perm-granted@example.com")

    def test_admin_always_allowed(self, clean_policies):
        from app.services.permission_service import get_permission_service

        svc = get_permission_service()
        _grant("use_workflows")  # 配置存在，且没有任何针对 admin 的 user 级策略
        uid = _make_user("wf-perm-admin@example.com", role="admin")
        try:
            user = _load_user(uid)
            assert svc.enforce_for_user(user, "read", "feature", "use_workflows") is True
        finally:
            _cleanup_users("wf-perm-admin@example.com")


class TestToolBridgeUsesSameGate:
    """工具桥（对话侧）与端点必须同一口径。"""

    def test_denied_when_configured_and_not_granted(self, clean_policies):
        from app.tools.workflow_tools import _may_use_workflows

        _grant("use_workflows")
        uid = _make_user("wf-perm-tool-denied@example.com")
        try:
            assert _may_use_workflows(_load_user(uid)) is False
        finally:
            _cleanup_users("wf-perm-tool-denied@example.com")

    def test_denied_by_default(self, clean_policies):
        from app.tools.workflow_tools import _may_use_workflows

        uid = _make_user("wf-perm-tool-default@example.com")
        try:
            assert _may_use_workflows(_load_user(uid)) is False
        finally:
            _cleanup_users("wf-perm-tool-default@example.com")

    def test_allowed_when_granted(self, clean_policies):
        from app.tools.workflow_tools import _may_use_workflows

        uid = _make_user("wf-perm-tool-granted@example.com")
        try:
            _grant("use_workflows", subject=f"user:{uid}")
            assert _may_use_workflows(_load_user(uid)) is True
        finally:
            _cleanup_users("wf-perm-tool-granted@example.com")

    def test_no_identity_is_denied(self):
        """无会话身份时拒绝：工具桥不能成为绕过端点鉴权的后门。"""
        from app.tools.workflow_tools import _may_use_workflows

        assert _may_use_workflows(None) is False


class TestFeatureGrantsCatalog:
    def test_workflow_features_registered(self):
        """授权项必须出现在权限编辑器可选列表里，否则管理员配不了。"""
        from app.api.v1.endpoints.permissions import FEATURE_GRANTS

        keys = {key for key, _label, _desc in FEATURE_GRANTS}
        assert "use_workflows" in keys
        assert "view_workflow_runs" in keys


class TestEndpointGate:
    """端点层：配置后未授权用户 403；管理员始终放行。"""

    def test_run_endpoint_403_when_configured_and_not_granted(self, clean_policies):
        from fastapi.testclient import TestClient

        from app.core.config import get_settings
        from app.core.security import create_access_token
        from app.main import app

        _grant("use_workflows")
        email = "wf-perm-ep-denied@example.com"
        _cleanup_users(email)
        uid = _make_user(email)
        try:
            wf_name = "wf-权限-端点"
            with create_db_session() as db:
                from app.db.models import WorkflowModel

                db.add(WorkflowModel(
                    name=wf_name,
                    graph_json=(
                        '{"nodes":[{"id":"start","type":"start"},'
                        '{"id":"end","type":"end"}],'
                        '"edges":[{"from":"start","to":"end"}]}'
                    ),
                    enabled=True,
                ))
                db.commit()
            try:
                settings = get_settings()
                token = create_access_token(
                    {"sub": str(uid), "email": email, "role": "user"},
                    secret=settings.auth_secret_key,
                    expires_in_seconds=600,
                )
                with TestClient(app) as client:
                    list_resp = client.get(
                        "/api/v1/workflows", headers={"Authorization": f"Bearer {token}"}
                    )
                    wf_id = next(
                        w["id"] for w in list_resp.json()["items"] if w["name"] == wf_name
                    )
                    resp = client.post(
                        f"/api/v1/workflows/{wf_id}/run",
                        headers={"Authorization": f"Bearer {token}"},
                        json={"inputs": {}},
                    )
                assert resp.status_code == 403, resp.text
                assert "use_workflows" in resp.json()["detail"]
            finally:
                with create_db_session() as db:
                    db.execute(delete(WorkflowModel).where(WorkflowModel.name == wf_name))
                    db.commit()
        finally:
            _cleanup_users(email)


class TestGrantedUserCanRun:
    """默认拒绝之后，管理员授权必须真的生效（否则功能等于被砍掉）。"""

    def test_granted_regular_user_can_run_workflow(self, clean_policies):
        from fastapi.testclient import TestClient

        from app.core.config import get_settings
        from app.core.security import create_access_token
        from app.db.models import WorkflowModel
        from app.main import app

        email = "wf-perm-granted-run@example.com"
        _cleanup_users(email)
        uid = _make_user(email)
        wf_name = "wf-权限-已授权"
        try:
            _grant("use_workflows", subject=f"user:{uid}")
            _grant("view_workflow_runs", subject=f"user:{uid}")

            with create_db_session() as db:
                db.add(WorkflowModel(
                    name=wf_name,
                    graph_json=(
                        '{"nodes":[{"id":"start","type":"start"},'
                        '{"id":"t","type":"template","params":{"template":"ok"}},'
                        '{"id":"end","type":"end","params":{"output":"{{nodes.t.output}}"}}],'
                        '"edges":[{"from":"start","to":"t"},{"from":"t","to":"end"}]}'
                    ),
                    enabled=True,
                ))
                db.commit()

            settings = get_settings()
            token = create_access_token(
                {"sub": str(uid), "email": email, "role": "user"},
                secret=settings.auth_secret_key,
                expires_in_seconds=600,
            )
            headers = {"Authorization": f"Bearer {token}"}
            with TestClient(app) as client:
                items = client.get("/api/v1/workflows", headers=headers).json()["items"]
                wf_id = next(w["id"] for w in items if w["name"] == wf_name)
                resp = client.post(
                    f"/api/v1/workflows/{wf_id}/run", headers=headers, json={"inputs": {}}
                )
            assert resp.status_code == 200, resp.text
            run_id = resp.json()["id"]

            # 轮询到终态，并确认能被本人读到（view_workflow_runs 已授权）
            import time as _time

            deadline = _time.monotonic() + 15
            body = {}
            with TestClient(app) as client:
                while _time.monotonic() < deadline:
                    body = client.get(
                        f"/api/v1/workflows/runs/{run_id}", headers=headers
                    ).json()
                    if body.get("status") in ("succeeded", "failed"):
                        break
                    _time.sleep(0.1)
            assert body.get("status") == "succeeded", body
            assert body.get("outputs") == "ok"
        finally:
            with create_db_session() as db:
                db.execute(delete(WorkflowModel).where(WorkflowModel.name == wf_name))
                db.commit()
            _cleanup_users(email)


def _cleanup_users(*emails: str) -> None:
    """删用户时连带删它的 g/p 规则。

    不删会留下孤儿绑定：SQLite 复用 id，下一个用例的新用户会「继承」
    已删除用户的角色授权（实测导致「默认拒绝」用例莫名放行）。
    """
    with create_db_session() as db:
        uids = [
            uid for (uid,) in db.execute(
                select(UserModel.id).where(UserModel.email.in_(emails))
            ).all()
        ]
        for uid in uids:
            subject = f"user:{uid}"
            db.execute(delete(CasbinRuleModel).where(CasbinRuleModel.v0 == subject))
        db.execute(delete(UserModel).where(UserModel.email.in_(emails)))
        db.commit()
    from app.services.permission_service import get_permission_service

    get_permission_service().reload()
