from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

APP_TIMEZONE_NAME = "Asia/Shanghai"
APP_TIMEZONE = ZoneInfo(APP_TIMEZONE_NAME)


def app_now() -> datetime:
    return datetime.now(APP_TIMEZONE)


def to_app_timezone(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=APP_TIMEZONE)
    return value.astimezone(APP_TIMEZONE)


def isoformat_app_timezone(value: datetime | None) -> str | None:
    converted = to_app_timezone(value)
    return converted.isoformat() if converted else None


def app_today() -> date:
    return app_now().date()
