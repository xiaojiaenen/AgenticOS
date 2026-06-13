"""
Video 智能体错误系统
完整对标 html-video 原版错误码
"""

from enum import Enum
from typing import Optional, Any


class ErrorCode(str, Enum):
    """错误码枚举"""
    ENGINE_NOT_INSTALLED = "engine-not-installed"
    ENGINE_NOT_REGISTERED = "engine-not-registered"
    TEMPLATE_INVALID = "template-invalid"
    TEMPLATE_NOT_FOUND = "template-not-found"
    RENDER_FAILED = "render-failed"
    RENDER_TIMEOUT = "render-timeout"
    OUTPUT_CORRUPT = "output-corrupt"
    DISK_FULL = "disk-full"
    CANCELLED = "cancelled"
    ASSET_NOT_FOUND = "asset-not-found"
    PROJECT_NOT_FOUND = "project-not-found"
    INVALID_INPUT = "invalid-input"


class HtmlVideoError(Exception):
    """HTML Video 错误基类"""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        retryable: bool = False,
        context: Optional[dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.retryable = retryable
        self.context = context or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
            "context": self.context,
        }

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"
