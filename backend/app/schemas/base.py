from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_serializer

from app.core.timezone import isoformat_app_timezone


class AppBaseModel(BaseModel):
    @field_serializer("*", when_used="json")
    def serialize_app_timezone(self, value):
        if isinstance(value, datetime):
            return isoformat_app_timezone(value)
        return value
