"""文生图工具：走 provider 的 image 角色。

为什么做成工具而不是固定流程：生图是「按需」能力 —— PPT 配图、网站
hero 图、海报都可能用，但绝大多数对话用不到。做成工具让智能体自己判断，
而不是每次对话都预先生成。

关键取舍：

- **端点从 provider 解析**（resolve_image_endpoint），不在工具里写死
  OpenAI 的 URL。这样管理员在「AI 提供商」页面绑了 image 角色就能用，
  换厂商不用改代码。
- **未配置时给可执行提示**，不是报错。用户看到「请先去 AI 提供商页面
  绑定生图模型」比看到 500 有用得多。
- **产物落到会话工作区**（outputs/），与其它产物一致，不污染进程内存。
"""

from __future__ import annotations

import base64
import logging
import uuid

import httpx
from wuwei.tools import ToolRegistry

from app.core.data_path import current_workspace_dir

logger = logging.getLogger("tools.image_gen")

# 常见尺寸（OpenAI 兼容端点普遍支持）
_SIZE_PRESETS = {
    "square": "1024x1024",
    "landscape": "1792x1024",
    "portrait": "1024x1792",
}


def register_image_gen_tools(registry: ToolRegistry) -> None:
    """注册文生图工具。"""

    @registry.tool(display_name="生成图片")
    async def generate_image(
        prompt: str,
        size: str = "landscape",
        filename: str = "",
    ) -> str:
        """用 AI 生成一张图片，保存到工作区并返回路径。

        什么时候用：需要原创配图（PPT 封面、网站 hero、示意图），而图库
        搜索找不到合适的图。单纯找现成图片请用 search_images。

        参数:
          prompt: 图片描述。英文效果通常更好，写清主体、风格、构图、色调。
                  例: "minimal flat illustration of a data pipeline, blue palette"
          size: 尺寸档位
                - landscape: 1792x1024（16:9，PPT 封面首选）
                - square: 1024x1024（图标、头像）
                - portrait: 1024x1792（手机端、海报）
          filename: 输出文件名（不含扩展名）。留空则自动生成

        返回:
          生成结果，含文件相对路径；失败时给出可执行的修正建议
        """
        from app.db.session import create_db_session
        from app.services.llm_providers.resolve_models import resolve_image_endpoint

        if not (prompt or "").strip():
            return "prompt 不能为空。请描述要生成的图片内容。"

        try:
            with create_db_session() as db:
                endpoint = resolve_image_endpoint(db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("解析生图端点失败", exc_info=True)
            return f"读取生图配置失败：{exc}"

        if endpoint is None:
            return (
                "还没有配置生图模型。请让管理员到「管理后台 → AI 提供商」：\n"
                "1. 选一个支持 /images/generations 的提供商（OpenAI、通义、SiliconFlow 等）\n"
                "2. 在「模型用途」里把「文生图」绑定到一个生图模型\n"
                "3. 保存后即可使用\n\n"
                "在此之前可以先用 search_images 找现成图库图片。"
            )

        if not endpoint.api_key:
            return (
                f"提供商「{endpoint.source}」绑定了生图模型「{endpoint.model}」，"
                "但缺少 API Key。请到 AI 提供商页面补上密钥。"
            )

        size_value = _SIZE_PRESETS.get(size, _SIZE_PRESETS["landscape"])

        # 产物落到会话工作区 outputs/，与其它产物一致。
        # current_workspace_dir 在没有会话上下文时返回 None —— 生图是重操作，
        # 拿不到工作区就不该继续（否则图片会落到不可预期的地方）。
        try:
            ws = current_workspace_dir(create=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("定位工作区失败", exc_info=True)
            return f"无法定位工作区：{exc}"
        if ws is None:
            return (
                "当前没有会话工作区，无法保存生成的图片。"
                "请在一个对话里使用这个工具（生图产物会存到该会话的 outputs/）。"
            )
        out_dir = ws / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)

        stem = (filename or f"img-{uuid.uuid4().hex[:10]}").strip()
        # 防路径穿越：只保留文件名部分
        stem = stem.replace("\\", "/").rsplit("/", 1)[-1]
        if stem.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            stem = stem.rsplit(".", 1)[0]

        payload = {
            "model": endpoint.model,
            "prompt": prompt,
            "n": 1,
            "size": size_value,
            "response_format": "b64_json",
        }

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(
                    f"{endpoint.base_url}/images/generations",
                    headers={
                        "Authorization": f"Bearer {endpoint.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if resp.status_code == 404:
                    return (
                        f"提供商端点不支持 /images/generations（HTTP 404）。\n"
                        f"当前端点：{endpoint.base_url}\n"
                        "请确认这家提供商的生图接口路径，或换一家支持 OpenAI 生图协议的。"
                    )
                if resp.status_code in (401, 403):
                    return (
                        f"生图鉴权失败（HTTP {resp.status_code}）。\n"
                        f"提供商：{endpoint.source}\n"
                        "请在 AI 提供商页面检查密钥是否正确、是否有生图权限。"
                    )
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            return "生图请求超时（180s）。生图通常比对话慢，可稍后重试或换更小的尺寸。"
        except Exception as exc:  # noqa: BLE001
            logger.warning("生图调用失败", exc_info=True)
            return f"生图失败：{type(exc).__name__}: {exc}"

        items = data.get("data") or []
        if not items:
            return f"上游没有返回图片。原始响应片段：{str(data)[:200]}"

        first = items[0] if isinstance(items[0], dict) else {}
        b64 = first.get("b64_json")
        url = first.get("url")

        if b64:
            try:
                raw = base64.b64decode(b64)
            except Exception as exc:  # noqa: BLE001
                return f"图片解码失败：{exc}"
            target = out_dir / f"{stem}.png"
            try:
                target.write_bytes(raw)
            except OSError as exc:
                return f"写入图片失败：{exc}"
            rel = f"outputs/{target.name}"
            return (
                f"图片已生成并保存到工作区：{rel}\n"
                f"尺寸 {size_value}，模型 {endpoint.model}，{len(raw) // 1024} KB。\n"
                "可以直接在 PPT / SVG 里引用这个相对路径。"
            )

        if url:
            return (
                f"图片已生成，上游返回的是临时 URL：{url}\n"
                "注意：这类 URL 通常几小时后失效。如需长期使用，请让上游改用 "
                "response_format=b64_json，或先下载到工作区。"
            )

        return f"上游返回了图片项但没有 b64_json 也没有 url：{str(first)[:200]}"
