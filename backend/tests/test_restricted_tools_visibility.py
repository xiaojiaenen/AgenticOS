"""受限工具在智能体商店/编辑器里对普通用户不可见、不可启用。

用户要求：「希望我限制的工具在智能体商店创建智能体不可见」。

之前只做了运行期裁剪（`allowed_tools`），结果是用户**能勾选**、保存后却不生效
—— 他只会觉得是 bug，反复勾同一个开关。现在是三层：

1. **看不见**：`catalog`（勾选清单）对普通用户剔除受限项
2. **带不出来**：已存配置里的受限工具在渲染时也被过滤（避免"勾着的工具用不了"）
3. **存不进去**：保存时服务端拒绝（防绕过前端直接调 API）

管理员不受影响：他们本来就该能用全部工具有。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models import SystemSettingModel, UserModel
from app.db.session import create_db_session
from app.services import agent_tool_policy as policy_mod
from app.services.agent_profile_service import AgentProfileService
from app.services.agent_tool_policy import save_policy


@pytest.fixture()
def restricted_policy():
    """把 calc 设为受限（calc 是普通用户也确实能用的工具，便于对照）。"""
    def _set():
        with create_db_session() as db:
            save_policy(db, restricted_tools=["calc", "write_text_file"])

    def _clear():
        with create_db_session() as db:
            db.execute(
                delete(SystemSettingModel).where(
                    SystemSettingModel.key.in_(
                        [policy_mod.KEY_RESTRICTED_TOOLS, policy_mod.KEY_RESTRICTED_SKILLS]
                    )
                )
            )
            db.commit()

    _clear()
    _set()
    yield
    _clear()


class TestCatalogVisibility:
    def test_user_catalog_hides_restricted_tools(self, restricted_policy):
        """普通用户视角的 catalog 不含受限工具。"""
        from app.db.session import create_db_session

        service = AgentProfileService()
        with create_db_session() as db:
            catalog = service._catalog(db=db, for_privileged=False)
        names = {item["name"] for item in catalog}
        assert "calc" not in names, "受限工具不该出现在普通用户的勾选清单里"
        assert "write_text_file" not in names
        # 未受限的仍在
        assert "time" in names

    def test_admin_catalog_has_everything(self, restricted_policy):
        """管理员视角仍然看得到（他要用）。"""
        from app.db.session import create_db_session
        from app.services.tool_config_service import TOOL_CATALOG

        service = AgentProfileService()
        with create_db_session() as db:
            catalog = service._catalog(db=db, for_privileged=True)
        names = {item["name"] for item in catalog}
        assert "calc" in names
        assert "write_text_file" in names
        assert names == set(TOOL_CATALOG), "管理员视角应覆盖全部目录条目"

    def test_no_policy_configured_shows_all(self):
        """没配策略（默认只限危险写操作）时，calc 这类安全工具照常可见。"""
        from app.db.session import create_db_session

        with create_db_session() as db:
            db.execute(
                delete(SystemSettingModel).where(
                    SystemSettingModel.key == policy_mod.KEY_RESTRICTED_TOOLS
                )
            )
            db.commit()

        service = AgentProfileService()
        with create_db_session() as db:
            catalog = service._catalog(db=db, for_privileged=False)
        names = {item["name"] for item in catalog}
        assert "calc" in names
        # 默认受限的写文件工具仍然隐藏
        assert "write_text_file" not in names


class TestHiddenToolsForViewer:
    def test_normal_user_gets_restricted_set(self, restricted_policy):
        from app.db.session import create_db_session

        with create_db_session() as db:
            hidden = AgentProfileService._hidden_tools_for_viewer(db, "user")
        assert hidden == frozenset({"calc", "write_text_file"})

    def test_admin_gets_nothing_hidden(self, restricted_policy):
        """管理员不被隐藏任何工具。"""
        from app.db.session import create_db_session

        for role in ("admin", "superadmin"):
            with create_db_session() as db:
                hidden = AgentProfileService._hidden_tools_for_viewer(db, role)
            assert hidden == frozenset(), f"{role} 不该被隐藏工具"

    def test_operator_is_not_privileged_for_tools(self, restricted_policy):
        """operator 能管内容但不是管理员，受限工具对他同样隐藏。"""
        from app.db.session import create_db_session

        with create_db_session() as db:
            hidden = AgentProfileService._hidden_tools_for_viewer(db, "operator")
        assert "calc" in hidden

    def test_none_role_treated_as_normal_user(self, restricted_policy):
        """viewer_role=None 按普通用户处理（失败即收紧）。"""
        from app.db.session import create_db_session

        with create_db_session() as db:
            hidden = AgentProfileService._hidden_tools_for_viewer(db, None)
        assert "calc" in hidden


class TestMergedToolsFiltering:
    def test_stored_restricted_tool_is_dropped_for_user(self, restricted_policy):
        """历史上已勾选的受限工具：普通用户渲染时看不到。"""
        from app.db.session import create_db_session
        from app.services.tool_config_service import DEFAULT_MODE_TOOLS

        class _Row:
            def __init__(self, name, enabled=True):
                self.tool_name = name
                self.enabled = enabled
                self.requires_approval = False
                self.approval_sub_tools_json = "[]"

        rows = [_Row("calc"), _Row("time"), _Row("write_text_file")]
        with create_db_session() as db:
            hidden = AgentProfileService._hidden_tools_for_viewer(db, "user")
        merged = AgentProfileService._merge_tools_with_catalog(rows, hidden_names=hidden)
        names = {item["tool_name"] for item in merged}
        assert "calc" not in names
        assert "write_text_file" not in names
        assert "time" in names

    def test_admin_merge_keeps_restricted(self, restricted_policy):
        class _Row:
            def __init__(self, name):
                self.tool_name = name
                self.enabled = True
                self.requires_approval = False
                self.approval_sub_tools_json = "[]"

        merged = AgentProfileService._merge_tools_with_catalog(
            [_Row("calc")], hidden_names=frozenset()
        )
        assert "calc" in {item["tool_name"] for item in merged}


class TestSaveGuard:
    """第三层：服务端拒绝。防绕过前端直接调 API。"""

    @staticmethod
    def _make_user(email: str, role: str) -> int:
        from app.core.security import hash_password

        with create_db_session() as db:
            user = UserModel(
                email=email, name="U", password_hash=hash_password("password-123"),
                role=role, is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            return user.id

    @staticmethod
    def _cleanup(*emails: str) -> None:
        with create_db_session() as db:
            db.execute(delete(UserModel).where(UserModel.email.in_(emails)))
            db.commit()

    def test_user_cannot_enable_restricted_tool(self, restricted_policy):
        from app.services.agent_profile_service import AgentProfileCreateRequest, AgentProfileTool

        email = f"guard-{uuid4().hex}@example.com"
        try:
            self._make_user(email, "user")
            with create_db_session() as db:
                user = db.scalar(
                    __import__("sqlalchemy").select(UserModel).where(UserModel.email == email)
                )
                service = AgentProfileService()
                with pytest.raises(PermissionError, match="管理员限制"):
                    service.create(
                        AgentProfileCreateRequest(
                            name="受限测试",
                            slug=f"restricted-{uuid4().hex[:8]}",
                            system_prompt="x",
                            response_mode="general",
                            tools=[AgentProfileTool(tool_name="calc", enabled=True, requires_approval=False)],
                        ),
                        user,
                    )
        finally:
            self._cleanup(email)

    def test_user_can_still_disable_restricted_tool(self, restricted_policy):
        """已勾选的受限工具必须能**取消** —— 否则配置彻底卡死。"""
        from app.services.agent_profile_service import (
            AgentProfileCreateRequest,
            AgentProfileTool,
        )

        email = f"guard2-{uuid4().hex}@example.com"
        slug = f"toggle-{uuid4().hex[:8]}"
        try:
            self._make_user(email, "user")
            with create_db_session() as db:
                user = db.scalar(
                    __import__("sqlalchemy").select(UserModel).where(UserModel.email == email)
                )
                service = AgentProfileService()
                # 创建时不带受限工具
                profile = service.create(
                    AgentProfileCreateRequest(
                        name="切换测试", slug=slug, system_prompt="x",
                        response_mode="general",
                        tools=[AgentProfileTool(tool_name="time", enabled=True, requires_approval=False)],
                    ),
                    user,
                )
                # 显式 enabled=False 应该允许（取消勾选）
                service.update(
                    profile["id"],
                    __import__(
                        "app.services.agent_profile_service", fromlist=["AgentProfileUpdateRequest"]
                    ).AgentProfileUpdateRequest(
                        tools=[AgentProfileTool(tool_name="calc", enabled=False, requires_approval=False)],
                    ),
                    user,
                )
        finally:
            # 清掉 profile
            from app.db.models import AgentProfileModel

            with create_db_session() as db:
                row = db.scalar(
                    __import__("sqlalchemy").select(AgentProfileModel).where(
                        AgentProfileModel.slug == slug
                    )
                )
                if row is not None:
                    db.execute(
                        delete(AgentProfileModel).where(AgentProfileModel.id == row.id)
                    )
                    db.commit()
            self._cleanup(email)

    def test_admin_can_enable_restricted_tool(self, restricted_policy):
        from app.services.agent_profile_service import AgentProfileCreateRequest, AgentProfileTool

        email = f"guard3-{uuid4().hex}@example.com"
        slug = f"admin-ok-{uuid4().hex[:8]}"
        try:
            self._make_user(email, "admin")
            with create_db_session() as db:
                user = db.scalar(
                    __import__("sqlalchemy").select(UserModel).where(UserModel.email == email)
                )
                service = AgentProfileService()
                profile = service.create(
                    AgentProfileCreateRequest(
                        name="管理员测试", slug=slug, system_prompt="x",
                        response_mode="general",
                        tools=[AgentProfileTool(tool_name="calc", enabled=True, requires_approval=False)],
                    ),
                    user,
                )
                assert profile["id"] > 0
        finally:
            from app.db.models import AgentProfileModel

            with create_db_session() as db:
                db.execute(delete(AgentProfileModel).where(AgentProfileModel.slug == slug))
                db.commit()
            self._cleanup(email)
