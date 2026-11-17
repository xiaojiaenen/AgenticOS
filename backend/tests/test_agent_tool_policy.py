"""管理员对用户自建智能体的工具/Skill 限制。

这是平台层的安全收口：用户可以自建智能体，但**不该能给自己开危险工具**。
测试锁住的语义：

1. 默认只限制危险写操作（不是全限，否则新工具上线就"坏了"）
2. 特权所有者（管理员自建 / 平台内置）不受限
3. 普通用户自建会被裁掉受管工具
4. 策略可改、可存、读回一致
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models import SystemSettingModel, UserModel
from app.db.session import create_db_session
from app.services import agent_tool_policy as policy_mod
from app.services.agent_tool_policy import (
    DEFAULT_RESTRICTED_TOOLS,
    ToolPolicy,
    apply_policy_to_tools,
    load_policy,
    save_policy,
)


@pytest.fixture()
def clean_policy():
    """每个用例前清空策略行，保证读回的是默认值。"""
    def _clear():
        with create_db_session() as db:
            db.execute(
                delete(SystemSettingModel).where(
                    SystemSettingModel.key.in_(
                        [
                            policy_mod.KEY_RESTRICTED_TOOLS,
                            policy_mod.KEY_RESTRICTED_SKILLS,
                        ]
                    )
                )
            )
            db.commit()

    _clear()
    yield
    _clear()


class TestDefaults:
    def test_defaults_restrict_dangerous_writes(self, clean_policy):
        """默认限制写文件与代码执行 —— 这些等价于在服务器上跑代码。"""
        policy = load_policy_with_session()
        for tool in ("write_text_file", "delete_file", "python", "npm", "git"):
            assert tool in policy.restricted_tools, f"{tool} 应该默认受限"

    def test_defaults_do_not_restrict_safe_tools(self, clean_policy):
        """只读/计算类工具不该默认受限，否则新智能体上线即残缺。"""
        policy = load_policy_with_session()
        for tool in ("calc", "time", "read_emails", "search_emails"):
            assert tool not in policy.restricted_tools, f"{tool} 不该默认受限"

    def test_every_default_restricted_name_actually_exists(self):
        """默认名单里的名字必须是真的工具 —— 否则限制是空转的。

        真实事故：早先写了 write_file / run_shell / npm_install 三个不存在的
        名字，管理员以为限制了 shell 执行，实际一个都没限制住。
        """
        from app.services.tool_config_service import DEFAULT_MODE_TOOLS, TOOL_CATALOG

        known = set(TOOL_CATALOG)
        for mapping in DEFAULT_MODE_TOOLS.values():
            known.update(mapping)

        ghosts = sorted(t for t in DEFAULT_RESTRICTED_TOOLS if t not in known)
        assert not ghosts, (
            "默认限制名单里有不存在的工具名："
            + ", ".join(ghosts)
            + "。限制一个不存在的工具等于没限制，请改成真实工具名。"
        )

    def test_default_restricted_tuple_matches_policy(self, clean_policy):
        policy = load_policy_with_session()
        assert policy.restricted_tools == frozenset(DEFAULT_RESTRICTED_TOOLS)


class TestApplyToTools:
    def test_privileged_owner_keeps_everything(self):
        allowed = frozenset({"calc", "write_text_file", "run_shell"})
        policy = ToolPolicy(restricted_tools=frozenset({"write_text_file", "run_shell"}))
        # 管理员自建 / 平台内置 → 原样返回
        assert apply_policy_to_tools(allowed, policy=policy, is_privileged_owner=True) == allowed

    def test_normal_user_loses_restricted_tools(self):
        allowed = frozenset({"calc", "write_text_file", "run_shell"})
        policy = ToolPolicy(restricted_tools=frozenset({"write_text_file", "run_shell"}))
        filtered = apply_policy_to_tools(allowed, policy=policy, is_privileged_owner=False)
        assert filtered == frozenset({"calc"})

    def test_empty_policy_is_noop(self):
        allowed = frozenset({"calc", "write_text_file"})
        out = apply_policy_to_tools(
            allowed, policy=ToolPolicy(), is_privileged_owner=False
        )
        assert out == allowed

    def test_filtering_preserves_unknown_tools(self):
        """策略里写了一个不存在的工具名，不该影响实际工具。"""
        allowed = frozenset({"calc"})
        policy = ToolPolicy(restricted_tools=frozenset({"nonexistent_tool"}))
        assert apply_policy_to_tools(
            allowed, policy=policy, is_privileged_owner=False
        ) == allowed


class TestSaveAndLoad:
    def test_save_roundtrip(self, clean_policy):
        with create_db_session() as db:
            saved = save_policy(
                db,
                restricted_tools=["calc", "time"],
                restricted_skills=["danger-skill"],
            )
        assert saved.restricted_tools == frozenset({"calc", "time"})
        assert saved.restricted_skills == frozenset({"danger-skill"})

        # 读回一致
        again = load_policy_with_session()
        assert again.restricted_tools == frozenset({"calc", "time"})
        assert again.restricted_skills == frozenset({"danger-skill"})

    def test_partial_update_keeps_other_field(self, clean_policy):
        with create_db_session() as db:
            save_policy(db, restricted_tools=["calc"])
        with create_db_session() as db:
            # 只改 skill，tools 应保持
            save_policy(db, restricted_skills=["s1"])
        policy = load_policy_with_session()
        assert policy.restricted_tools == frozenset({"calc"})
        assert policy.restricted_skills == frozenset({"s1"})

    def test_overlong_list_rejected(self, clean_policy):
        """system_settings.value 只有 1024 字符：超长要报错而不是写坏 JSON。"""
        long_names = [f"tool_with_a_very_long_name_{i:03d}" for i in range(60)]
        with create_db_session() as db:
            with pytest.raises(ValueError, match="限制名单过长"):
                save_policy(db, restricted_tools=long_names)

    def test_malformed_db_value_falls_back_to_default(self, clean_policy):
        with create_db_session() as db:
            db.add(
                SystemSettingModel(
                    key=policy_mod.KEY_RESTRICTED_TOOLS, value="{ not json"
                )
            )
            db.commit()
        policy = load_policy_with_session()
        assert policy.restricted_tools == frozenset(DEFAULT_RESTRICTED_TOOLS)


class TestSkillFiltering:
    class _Skill:
        def __init__(self, slug: str):
            self.slug = slug

    def test_restricted_skill_removed_for_user(self):
        skills = (self._Skill("ok-skill"), self._Skill("bad-skill"))
        out = policy_mod.filter_skills(
            skills,
            policy=ToolPolicy(restricted_skills=frozenset({"bad-skill"})),
            is_privileged_owner=False,
        )
        assert [s.slug for s in out] == ["ok-skill"]

    def test_privileged_keeps_restricted_skill(self):
        skills = (self._Skill("bad-skill"),)
        out = policy_mod.filter_skills(
            skills,
            policy=ToolPolicy(restricted_skills=frozenset({"bad-skill"})),
            is_privileged_owner=True,
        )
        assert len(out) == 1


class TestPrivilegedDetection:
    def test_admin_owned_profile_is_privileged(self):
        from app.services.agent_profile_service import AgentProfileService

        email = f"pol-admin-{uuid4().hex}@example.com"
        try:
            with create_db_session() as db:
                admin = UserModel(
                    email=email, name="A", password_hash="x", role="admin", is_active=True
                )
                db.add(admin)
                db.commit()
                db.refresh(admin)

                class _Profile:
                    owner_id = admin.id
                    id = 999

                assert AgentProfileService._is_privileged_profile(db, _Profile()) is True
        finally:
            with create_db_session() as db:
                db.execute(delete(UserModel).where(UserModel.email == email))
                db.commit()

    def test_user_owned_profile_is_not_privileged(self):
        from app.services.agent_profile_service import AgentProfileService

        email = f"pol-user-{uuid4().hex}@example.com"
        try:
            with create_db_session() as db:
                user = UserModel(
                    email=email, name="U", password_hash="x", role="user", is_active=True
                )
                db.add(user)
                db.commit()
                db.refresh(user)

                class _Profile:
                    owner_id = user.id
                    id = 998

                assert AgentProfileService._is_privileged_profile(db, _Profile()) is False
        finally:
            with create_db_session() as db:
                db.execute(delete(UserModel).where(UserModel.email == email))
                db.commit()

    def test_builtin_profile_is_privileged(self):
        from app.services.agent_profile_service import AgentProfileService

        with create_db_session() as db:
            class _Profile:
                owner_id = None
                id = 997

            assert AgentProfileService._is_privileged_profile(db, _Profile()) is True


def load_policy_with_session():
    from app.db.session import create_db_session as _mk

    with _mk() as db:
        return load_policy(db)
