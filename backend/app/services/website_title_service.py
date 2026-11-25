"""用模型给发布的作品起名字。

## 为什么需要它

发布对话框的输入框写着「留空则由 AI 根据对话自动生成」—— 但那句话一直
是空头支票：后端 `request_deploy` 里只有 `title=(title or "").strip() or None`，
留空就是 None，最终落到 `project_slug`（形如 `u3_s1794556944894-y3dle1_v2`）
当展示名。用户看到的是一串机器 ID。

这里补上真正的生成：读对话最后若干条 + 文件清单，让模型起一个**短、具体、
不带营销腔**的名字。失败时返回 None，由调用方退回现有兜底（不阻断发布）。
"""

from __future__ import annotations

import json
import logging

from app.services.llm_factory import build_llm_optional

logger = logging.getLogger("agenticos.website_title")


_TITLE_PROMPT = """你在给一个刚做好的网站起名字，它会作为作品标题展示给用户和管理员。

要求：
- **8-18 个汉字**（或等长的英文），能一眼看出这是做什么的
- 直接描述功能或主题，例如「季度销售数据看板」「团队协作流程说明」
- 不要营销腔（不要"全新""赋能""一站式"这类词）
- 不要书名号、引号、感叹号
- 只输出名字本身，不要解释、不要 markdown、不要句末标点

用户对话（最后几条，用于理解他要什么）：
{conversation}

文件清单（部分）：
{files}

网站技术栈：{stack}
用户填写的说明：{description}
"""


async def generate_site_title(
    *,
    conversation: list[dict[str, object]] | None = None,
    files: list[dict[str, object]] | None = None,
    stack: str | None = None,
    description: str | None = None,
) -> str | None:
    """返回生成的名字，失败返回 None（调用方应退回项目标识兜底）。"""
    convo = conversation or []
    file_list = files or []

    convo_text = "\n".join(
        f"{m.get('role')}: {str(m.get('text') or '')[:300]}" for m in convo[-8:]
    ) or "（无对话记录）"
    files_text = "\n".join(
        f"- {f.get('path')}" for f in file_list[:20]
    ) or "（未提供文件清单）"

    prompt = _TITLE_PROMPT.format(
        conversation=convo_text,
        files=files_text,
        stack=stack or "（未知）",
        description=(description or "").strip() or "（未填写）",
    )

    llm = build_llm_optional(role="fast", max_tokens=64, timeout=20, purpose="作品标题生成")
    if llm is None:
        return None

    try:
        from app.services.agent.native.types import HumanMessage

        resp = await llm.generate([HumanMessage(content=prompt)])
        text = (getattr(getattr(resp, "message", None), "content", "") or "").strip()

        # 模型偶尔会带引号/书名号/句号，去掉
        cleaned = _clean_title(text)
        if not cleaned:
            return None
        # 长度兜底：超过 40 字说明模型没照做，宁可用 slug 兜底也不要一长串
        if len(cleaned) > 40:
            logger.info("生成标题过长，丢弃：%r", cleaned[:60])
            return None
        return cleaned
    except json.JSONDecodeError:  # 理论上不该走到，防御性保留
        return None
    except Exception:  # noqa: BLE001 —— 命名失败不能阻断发布
        logger.warning("作品标题生成失败", exc_info=True)
        return None


def _clean_title(raw: str) -> str:
    """去掉引号、书名号、markdown 包装与句末标点。

    顺序很重要：**先去句末标点，再去包裹引号**。反过来会漏 ——
    `"「季度看板」。"` 结尾是 `」。`，先按引号匹配就对不上，剥完标点
    又留下半个书名号。
    """
    text = raw.strip()

    # 1) 去掉 ``` 代码围栏（模型偶尔把名字包在围栏里）
    if "```" in text:
        parts = text.split("```")
        # 取第一个非空段（围栏可能是 ```text 开头）
        for part in parts:
            candidate = part.strip()
            if candidate:
                # 语言标记行（如 "json"）跳过
                first_line = candidate.splitlines()[0].strip().lower()
                if first_line in {"json", "text", "plaintext", "md", "markdown"}:
                    candidate = "\n".join(candidate.splitlines()[1:]).strip()
                text = candidate
                break

    # 2) 去掉 markdown 标题前缀
    text = text.lstrip("#").strip()

    # 3) 只取第一行（模型常补充说明）
    text = text.splitlines()[0].strip() if text else ""

    # 4) **先去句末标点**
    text = text.rstrip("。.！!？?;；,，、 ").strip()

    # 5) 再剥包裹引号/书名号（此时结尾不再有句号，能正确配对）
    pairs = (('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"),
             ("「", "」"), ("『", "』"), ("《", "》"), ("<", ">"))
    changed = True
    while changed and len(text) > 2:
        changed = False
        for left, right in pairs:
            if text.startswith(left) and text.endswith(right):
                text = text[1:-1].strip()
                changed = True

    # 6) 剥完引号可能又露出句末标点（如 「标题」→ 标题。）—— 再清一次
    return text.rstrip("。.！!？?;；,，、 ").strip()
