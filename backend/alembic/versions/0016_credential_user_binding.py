"""凭据表增加 user_id 绑定（LDAP 账号 == 企业网关账号的部署形态）。

背景：部署环境里平台的 LDAP 账号与百通 SSO 是**同一套企业账号密码**。
原设计「账号池是系统级资源，与终端用户无关」在这种形态下有两个问题：

1. **审计**：用同事的企业账号替用户调上游，上游日志里的身份是错的；
2. **密码轮换**：用户改了域密码后，池里那条账号的自动登录会持续失败，
   没有任何机制把「重新登录平台」和「更新网关凭据」串起来。

加 ``user_id`` 后：LDAP 登录时把（用户名+密码）写进本人绑定的凭据行并
自动登录拿 Cookie；取号优先用本人凭据；重登失败（密码已改）→ 吊销其
平台会话强制重新登录 → 新密码被捕获 → 自动恢复。

兼容：user_id 为空 = 传统共享池账号，行为完全不变。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_credential_user_binding"
down_revision = "0015_mcp_intranet_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("llm_provider_credentials")}
    if "user_id" not in cols:
        op.add_column(
            "llm_provider_credentials",
            sa.Column("user_id", sa.Integer(), nullable=True),
        )
    indexes = {i["name"] for i in inspector.get_indexes("llm_provider_credentials")}
    if "ix_llm_provider_cred_user" not in indexes:
        op.create_index(
            "ix_llm_provider_cred_user", "llm_provider_credentials", ["user_id"]
        )


def downgrade() -> None:
    op.drop_index("ix_llm_provider_cred_user", table_name="llm_provider_credentials")
    op.drop_column("llm_provider_credentials", "user_id")
