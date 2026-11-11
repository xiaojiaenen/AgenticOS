"""模型能力探测（当前仅视觉）。

为什么用名称启发式而不是探测请求：视觉能力没有便宜可靠的运行时探测
（真发一张图要花一次 LLM 调用，且不支持时各网关报错格式不一）。名称
启发式覆盖主流视觉模型族，误判的代价可控 —— 支持视觉但名字不匹配的
模型，图片仍可上传（后端不拦截，只是前端提示弱一些）；反之不支持却
误放行，上游会报错且现有错误展示能兜住。

新模型族出现时在这里加一行模式即可。
"""

from __future__ import annotations

import re

# 常见视觉/多模态模型族的名称模式（不区分大小写）。
_VISION_PATTERNS = (
    r"gpt-4o",              # OpenAI GPT-4o / 4o-mini 全系
    r"gpt-4\.1",            # GPT-4.1 全系
    r"gpt-5",               # GPT-5 全系
    r"o3", r"o4",           # o 系推理模型（多模态输入）
    r"claude-[3-9]",        # Claude 3+ 全系支持视觉
    r"gemini",              # Gemini 全系
    r"glm-4v",              # 智谱视觉系
    r"glm-4\.[56]",         # GLM-4.5/4.6 旗舰多模态
    r"glm-5",               # GLM-5 系
    r"qwen.*vl",            # Qwen-VL 系
    r"qwen2?\.5?-?(max|plus|turbo)",  # Qwen 商业版（多模态）
    r"doubao.*vision",      # 豆包视觉系
    r"pixtral",             # Mistral 视觉系
    r"llama.*vision",       # Llama Vision
    r"vl-",                 # 通用 -vl 后缀（如 deepseek-vl）
    r"-vision",             # 通用 -vision 后缀
)

_COMPILED = tuple(re.compile(p, re.IGNORECASE) for p in _VISION_PATTERNS)


def supports_vision(model_name: str | None) -> bool:
    """判断模型名是否匹配已知视觉模型族。未知名称保守返回 False。"""
    if not model_name:
        return False
    return any(p.search(model_name) for p in _COMPILED)
