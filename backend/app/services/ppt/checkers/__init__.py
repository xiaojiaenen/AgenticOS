"""PPT 质量检查器模块

拆分为三个轻量级检查器：
- technical_checker: 技术检查（必须通过）
- design_checker: 设计检查（警告为主）
- accessibility_checker: 可访问性检查（可选）
"""

from .technical_checker import TechnicalChecker
from .design_checker import DesignChecker
from .unified_checker import PPTChecker, CheckResult, CheckReport, DeckCheckReport

__all__ = [
    "TechnicalChecker",
    "DesignChecker",
    "PPTChecker",
    "CheckResult",
    "CheckReport",
    "DeckCheckReport",
]
