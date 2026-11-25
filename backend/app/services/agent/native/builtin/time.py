from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.agent.native.plugins import PluginContext  # wuwei 退役 A5-3 移植


def setup(ctx: PluginContext) -> None:
    @ctx.tool_registry.tool(description="获取当前时间", display_name="获取当前时间")
    def get_now(timezone: str = "Asia/Shanghai") -> dict:
        now = datetime.now(ZoneInfo(timezone))
        return {"timezone": timezone, "iso": now.isoformat()}
