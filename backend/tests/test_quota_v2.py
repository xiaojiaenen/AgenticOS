"""额度系统 v2：全局/个人额度、生图额度、发布奖励、用户侧总览。"""

from __future__ import annotations

from app.services.quota_service import (
    PUBLISH_REWARD_TOKENS,
    check_image_quota,
    get_eff_quota,
    get_user_quota_status,
    grant_publish_reward,
)

UID = 999999
UID2 = 999998


def _restore(db, key, old):
    from app.db.models import SystemSettingModel

    row = db.get(SystemSettingModel, key)
    if old is None:
        if row is not None:
            db.delete(row)
    elif row is not None:
        row.value = old
    db.commit()


def test_publish_reward_tokens_defined():
    assert PUBLISH_REWARD_TOKENS["ppt"] > 0
    assert PUBLISH_REWARD_TOKENS["document"] > 0
    assert PUBLISH_REWARD_TOKENS["image"] > 0


def test_get_eff_quota_global_and_user_override():
    from app.db.models import SystemSettingModel
    from app.db.session import create_db_session
    from app.services.quota_service import QUOTA_KEY, _user_quota_key

    gkey = QUOTA_KEY
    ukey = _user_quota_key(UID, "token")
    with create_db_session() as db:
        g = db.get(SystemSettingModel, gkey)
        old_g = g.value if g else None
        u = db.get(SystemSettingModel, ukey)
        old_u = u.value if u else None
        if g is None:
            db.add(SystemSettingModel(key=gkey, value="12345"))
        else:
            g.value = "12345"
        if u is None:
            db.add(SystemSettingModel(key=ukey, value="777"))
        else:
            u.value = "777"
        db.commit()
        try:
            assert get_eff_quota(db, UID, "token") == 777
            assert get_eff_quota(db, UID2, "token") == 12345
        finally:
            _restore(db, gkey, old_g)
            _restore(db, ukey, old_u)


def test_grant_publish_reward_accumulates():
    reward = grant_publish_reward(UID, "ppt")
    assert reward == PUBLISH_REWARD_TOKENS["ppt"]
    assert grant_publish_reward(UID, "ppt") == PUBLISH_REWARD_TOKENS["ppt"]


def test_quota_status_shape():
    status = get_user_quota_status(UID, role="user")
    assert "token" in status and "image" in status
    assert "quota" in status["token"] and "remaining" in status["token"]
    assert "rewards" in status


def test_admin_quota_status_unlimited():
    status = get_user_quota_status(UID, role="admin")
    assert status["token"]["quota"] == -1
    assert status["image"]["quota"] == -1


def test_image_quota_admin_exempt():
    """管理员始终豁免生图额度检查。"""
    from app.db.models import SystemSettingModel
    from app.db.session import create_db_session
    from app.services.quota_service import IMAGE_QUOTA_KEY

    with create_db_session() as db:
        row = db.get(SystemSettingModel, IMAGE_QUOTA_KEY)
        old = row.value if row else None
        if row is None:
            db.add(SystemSettingModel(key=IMAGE_QUOTA_KEY, value="1"))
        else:
            row.value = "1"
        db.commit()
    try:
        # 管理员豁免：返回 used=None 表示不检查用量
        assert check_image_quota(UID2, role="admin")["used"] is None
    finally:
        with create_db_session() as db:
            _restore(db, IMAGE_QUOTA_KEY, old)
