"""预生成压测账号（一次性）。

压测用户不应该现场注册 —— 注册接口本身会打数据库、写密码哈希、可能触发
邮件/验证码，把瓶颈挪到与被测路径无关的地方。

用法（后端已启动的前提下）：
    uv run python loadtest/seed_loadtest_users.py
    uv run python loadtest/seed_loadtest_users.py --count 500 --password Loadtest123!

说明：
- 账号命名 lt0001@test.local …，与 locustfile 的 USER_POOL 对齐
- 第一个注册用户会自动成为 admin；压测账号统一按 admin 建，
  这样 dashboard/analytics（require_admin）也能被压到
- 幂等：已存在的账号会跳过
"""

from __future__ import annotations

import argparse
import sys

import httpx

DEFAULT_API = "http://127.0.0.1:8001/api/v1"


def _promote_to_admin(
    client: httpx.Client, admin_token: str, emails: list[str], password: str
) -> tuple[int, int]:
    """把压测账号提升为 admin。

    /dashboard/stats 与 /dashboard/analytics 都是 require_admin，普通 user
    会被 403 —— 那样测出来的错误率全是鉴权噪声，压不到真正的查询路径。
    压测账号是脚本生成的专用账号，提权不影响真实用户。
    """
    promoted = 0
    failed = 0
    headers = {"Authorization": f"Bearer {admin_token}"}

    for email in emails:
        # 登录拿到 user_id（列表接口也可以，但登录顺带验证了密码可用）
        login = client.post("/auth/login", json={"email": email, "password": password})
        if login.status_code != 200:
            failed += 1
            continue
        user_id = login.json().get("user", {}).get("id")
        if user_id is None:
            failed += 1
            continue

        resp = client.patch(f"/users/{user_id}", json={"role": "admin"}, headers=headers)
        if resp.status_code == 200:
            promoted += 1
        else:
            failed += 1

    return promoted, failed


def seed(
    api: str,
    count: int,
    password: str,
    promote_admin: bool,
    admin_email: str = "",
    admin_password: str = "",
) -> int:
    created = 0
    skipped = 0
    failed: list[str] = []
    emails: list[str] = []

    with httpx.Client(base_url=api, timeout=30.0) as client:
        for i in range(1, count + 1):
            email = f"lt{i:04d}@test.local"
            emails.append(email)
            resp = client.post(
                "/auth/register",
                json={"email": email, "password": password, "name": f"Loadtest {i}"},
            )
            if resp.status_code in (200, 201):
                created += 1
            elif resp.status_code in (400, 409):
                # 已存在（注册接口对重复邮箱返回 400/409）
                skipped += 1
            else:
                failed.append(f"{email}: {resp.status_code} {resp.text[:120]}")

        print(f"created={created} skipped={skipped} failed={len(failed)}")
        for line in failed[:10]:
            print(f"  ! {line}")

        if promote_admin:
            admin_token = _resolve_admin_token(client, emails, password, admin_email, admin_password)
            if admin_token is None:
                print(
                    "\n未找到可用于提权的 admin 账号。"
                    "库里只有第一个注册用户是 admin，若它不在压测账号池里，"
                    "请显式指定：\n"
                    "  --admin-email <admin账号> --admin-password <密码>"
                )
                return 1
            promoted, promote_failed = _promote_to_admin(client, admin_token, emails, password)
            print(f"promoted_to_admin={promoted} promote_failed={promote_failed}")

    return 0 if not failed else 1


def _resolve_admin_token(
    client: httpx.Client,
    emails: list[str],
    password: str,
    admin_email: str,
    admin_password: str,
) -> str | None:
    """拿一个 admin token：优先用显式指定的，否则在压测账号池里找。"""
    if admin_email:
        resp = client.post(
            "/auth/login", json={"email": admin_email, "password": admin_password}
        )
        if resp.status_code != 200:
            print(f"  ! 指定 admin 登录失败: {resp.status_code} {resp.text[:120]}")
            return None
        if resp.json().get("user", {}).get("role") != "admin":
            print(f"  ! {admin_email} 不是 admin，无法用于提权")
            return None
        return resp.json()["access_token"]

    # 第一个注册用户才是 admin；已存在的老库里它可能不在压测池中
    for email in emails:
        resp = client.post("/auth/login", json={"email": email, "password": password})
        if resp.status_code == 200 and resp.json().get("user", {}).get("role") == "admin":
            return resp.json()["access_token"]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="预生成 AgenticOS 压测账号")
    parser.add_argument("--api", default=DEFAULT_API, help="后端 API 前缀")
    parser.add_argument("--count", type=int, default=50, help="账号数量")
    parser.add_argument("--password", default="Loadtest123!", help="统一密码")
    parser.add_argument(
        "--promote-admin",
        action="store_true",
        help="把压测账号提升为 admin（dashboard 端点是 require_admin，不提权会 403）",
    )
    parser.add_argument("--admin-email", default="", help="提权用的 admin 账号")
    parser.add_argument("--admin-password", default="", help="提权用的 admin 密码")
    args = parser.parse_args()

    if args.count < 1:
        print("--count 必须 >= 1", file=sys.stderr)
        return 2
    return seed(
        args.api.rstrip("/"),
        args.count,
        args.password,
        args.promote_admin,
        args.admin_email,
        args.admin_password,
    )


if __name__ == "__main__":
    raise SystemExit(main())