"""邮件模板 — 深底印刷（Dark Print）视觉的 HTML 构建器。

为什么单独抽一个模块：
原来通知邮件、欢迎邮件、验证码邮件的 HTML 分别写在各 service 里，三份
互不相同的模板 —— 配色漂移、结构重复、改一次要改三处。这里收成一套
设计令牌 + 三个内容布局，service 只负责传数据。

## 视觉方向：深底印刷（Dark Print）

不是「深色 SaaS 卡片」。取的是**印刷品**的气质：深墨绿纸面、一条贯穿的
琥珀色立边、超大无衬线标题压住版面、等宽数字像铅字。三个场景共用同一套
骨架（页眉记号 / 标题区 / 立边内容块 / 细线页脚），换的是中间的内容结构。

配色刻意避开两个常见 AI 默认：
- 不是「近黑底 + 单一亮色点缀」的通用模板 —— 底色是有色相的墨绿 #0a1512，
  不是 #0b0b0b 那类纯黑；亮色只有一枚琥珀 #cf9a34，且只用在记号与按钮。
- 不是「暖奶油 + 衬线 + 陶土」的编辑部套路。

## 邮件客户端的能力边界（决定了下面的写法）

这不是网页。下面这些在主流客户端里**不可靠或直接不生效**，所以刻意避开：

- `<style>` 里的类选择器 —— Gmail 会剥掉大部分，必须写内联 `style`。
  本文件只在 `<style>` 里留 `@media` 与少量窄屏微调，绝不让主体依赖它。
- `flex` / `grid` / `position` —— Outlook（Word 渲染引擎）不支持，布局必须
  用 `<table>` 嵌套。
- 外链图片 —— 默认屏蔽，内网邮件网关也常拦。品牌记号用一个**纯 CSS 色块**
  （琥珀 9×9 小方），不依赖任何图片资源。
- `border-radius` —— Outlook 会渲染成直角，所以圆角都是「锦上添花」；
  关键视觉（立边、分割线、版面层级）都不依赖它。
- `box-shadow` / `backdrop-filter` / `transform` —— 一律不用。
- `@keyframes` —— Gmail / Outlook 全都不支持，不用。

## 可交互的诚实边界

普通 HTML 邮件能做的「交互」只有三种，且都是渐进增强：

1. **可点链接**（`<a href>`）—— 100% 支持，这是唯一的真交互；
2. **悬停反馈**（`:hover` + `transition`）—— Apple Mail / iOS / Outlook.com
   支持；Gmail 不播，但按钮仍是完整实心块，不丢信息；
3. **SMIL 微动效**（内联 SVG `<animate>`）—— 同上。

真正的交互组件（表单 / 折叠 / 轮播）只有 AMP for Email 能做，需要 Google
白名单且仅 Gmail/Yahoo 生效，内部部署不现实 —— 所以不假装有交互。

## 可读性（任何客户端都不豁免）

正文 ≥14px、标签 ≥12px、对比度 ≥4.5:1。琥珀按钮上是深墨字（反差足够），
深底上的次要文字用 #8aa398 一级（在 #0a1512 上约 5.4:1）。
"""

from __future__ import annotations

import html
from dataclasses import dataclass

# ── 设计令牌 ──────────────────────────────────────────────────────────

# 墨绿色相：不是纯黑，保留一点绿，深底才有「纸」的温度而非屏幕的黑
INK_BG = "#0a1512"        # 页面底
CARD_BG = "#0e1c18"       # 卡片（比页面底略亮一层）
INSET_BG = "#0a1512"      # 内容牌（回到页面底色，靠立边与底区分）
HAIRLINE = "#1c302a"      # 分割线 / 卡片描边

# 文字三级
TEXT_HI = "#f2f7f4"       # 主文字（标题、数值）
TEXT_MID = "#a9bfb4"      # 正文
TEXT_LOW = "#7f9c90"      # 次要（页脚、说明）—— 在 INK_BG 上 6.2:1
TEXT_FAINT = "#6f8a7f"    # 极次要

# 唯一的强调色：琥珀（一枚记号 + 按钮，仅此两处）
AMBER = "#cf9a34"
AMBER_INK = "#1a1206"     # 琥珀按钮上的文字（深墨，非纯黑）

FONT_SANS = (
    "'Helvetica Neue',Helvetica,Arial,'PingFang SC','Hiragino Sans GB',"
    "'Microsoft YaHei','Noto Sans SC',sans-serif"
)
FONT_MONO = "'SFMono-Regular',Menlo,Consolas,'Courier New',monospace"

#: 邮件主体宽度。540px 在桌面客户端阅读舒适，也留够移动端边距。
CARD_WIDTH = 540

#: 反馈联系人。mailto: 点击会唤起本机默认邮件客户端（Outlook / Foxmail / 系统邮件），
#: 并自动填好收件人。必须是**完整邮箱地址**，只写工号会让客户端当成无效收件人。
#: 显示文案仍用短号（更低调、不显眼），放在页脚最末、字号与颜色压到最低一档。
CONTACT_ADDRESS = "731302@gree.com.cn"
CONTACT_LABEL = "731302"
CONTACT_MAILTO = f"mailto:{CONTACT_ADDRESS}?subject=AgenticOS%20%E5%8F%8D%E9%A6%88"


# ── 基础片段 ──────────────────────────────────────────────────────────

def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _marker(size: int = 9, color: str = AMBER) -> str:
    """品牌记号：一枚实心色块。代替 logo 图 —— 图会被拦，色块不会。"""
    return (
        f'<div style="width:{size}px;height:{size}px;background:{color};'
        f'font-size:0;line-height:0;">&nbsp;</div>'
    )


def _header(left: str, right: str) -> str:
    """页眉：左品牌（琥珀记号 + 字标），右一句状态/分类。"""
    return f"""<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
  <td valign="middle">
    <table cellpadding="0" cellspacing="0" border="0"><tr>
      <td style="width:9px;">{_marker(9)}</td>
      <td style="padding-left:10px;font-family:{FONT_SANS};font-size:14px;font-weight:700;letter-spacing:0.01em;color:{TEXT_HI};">{_esc(left)}</td>
    </tr></table>
  </td>
  <td align="right" valign="middle" style="font-family:{FONT_SANS};font-size:12px;color:{TEXT_LOW};">{right}</td>
</tr></table>"""


def _eyebrow(text: str) -> str:
    """标题上方的一句小字分类（不是全大写标签，是正常中文短语）。"""
    return (
        f'<div style="font-family:{FONT_SANS};font-size:13px;letter-spacing:0.1em;'
        f'color:{TEXT_FAINT};">{_esc(text)}</div>'
    )


def _h1(text: str) -> str:
    """页面主标题：超大无衬线、紧字距、压住版面。"""
    return (
        f'<div style="margin-top:14px;font-family:{FONT_SANS};font-size:34px;'
        f'font-weight:800;line-height:1.2;color:{TEXT_HI};letter-spacing:-0.02em;">'
        f"{text}</div>"
    )


def _rule(pad_top: int = 0) -> str:
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0">'
        f'<tr><td style="height:{pad_top}px;font-size:0;line-height:0;">&nbsp;</td></tr>'
        f'<tr><td style="height:1px;background:{HAIRLINE};font-size:0;line-height:0;">&nbsp;</td></tr>'
        f"</table>"
    )


def _button(label: str, href: str) -> str:
    """主按钮：琥珀实心 + 深墨字。悬停变深一档（支持 transition 的客户端）。

    Gmail 不播 transition，但按钮本身的实心块完整可读 —— 悬停只是加分项。
    """
    return f"""<table cellpadding="0" cellspacing="0" border="0"><tr>
  <td style="background:{AMBER};border-radius:6px;">
    <a href="{_esc(href)}"
       style="display:inline-block;padding:12px 30px;font-family:{FONT_SANS};
              font-size:14px;font-weight:700;color:{AMBER_INK};text-decoration:none;
              letter-spacing:0.01em;transition:opacity .16s ease;"
       onmouseover="this.style.opacity='0.86';"
       onmouseout="this.style.opacity='1';">{_esc(label)}</a>
  </td>
</tr></table>"""


def _kv_table(rows: list[tuple[str, str, bool]]) -> str:
    """键值表：像单据字段。rows = [(label, value, is_mono), ...]。

    最后一行不带底边，避免与页面分割线叠成双线。
    """
    body = ""
    for i, (label, value, mono) in enumerate(rows):
        border = "" if i == len(rows) - 1 else f"border-bottom:1px solid {HAIRLINE};"
        value_font = f"font-family:{FONT_MONO};" if mono else f"font-family:{FONT_SANS};font-weight:600;"
        body += (
            f'<tr><td style="padding:12px 0;{border}font-family:{FONT_SANS};'
            f'font-size:13px;color:{TEXT_LOW};">{_esc(label)}</td>'
            f'<td align="right" style="padding:12px 0;{border}{value_font}'
            f'font-size:13px;color:{TEXT_HI};">{_esc(value)}</td></tr>'
        )
    return f'<table width="100%" cellpadding="0" cellspacing="0" border="0">{body}</table>'


def _inset_block(inner: str) -> str:
    """内容牌：回到底色 + 左侧 3px 琥珀立边。这是整套视觉的骨干元素。"""
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{INSET_BG};border-left:3px solid {AMBER};">'
        f'<tr><td style="padding:24px 26px;">{inner}</td></tr></table>'
    )


@dataclass
class EmailShell:
    """一封邮件的整体框架。三个场景共用，只换 body。"""

    preheader: str
    header_left: str
    header_right: str
    body: str
    #: 是否在页脚带「联系 731302」反馈入口。
    #: 系统通知邮件（验证码/欢迎/任务）带 —— 收信人是平台用户，反馈走平台；
    #: 用户自己发的邮件**不带** —— 那是私人通信，塞平台反馈页脚会很怪。
    show_feedback: bool = True
    #: 页脚最底那行小字。系统邮件是「AGENTICOS · 系统自动发出」；
    #: 用户自己发的邮件换中性文案，不宣称「系统自动发出」。
    footer_note: str = "AGENTICOS · 系统自动发出"


def render(shell: EmailShell) -> str:
    preheader = (
        f'<div style="display:none;font-size:1px;color:{INK_BG};line-height:1px;'
        f'max-height:0;max-width:0;opacity:0;overflow:hidden;">'
        f"{_esc(shell.preheader)}</div>"
    )
    feedback_html = ""
    if shell.show_feedback:
        feedback_html = (
            f'<div style="padding:8px 0 0;font-family:{FONT_SANS};font-size:12px;'
            f'color:{TEXT_LOW};text-align:center;">'
            f'有问题或想法，<a href="{CONTACT_MAILTO}" style="color:{TEXT_LOW};'
            f'text-decoration:underline;">联系 {CONTACT_LABEL}</a></div>'
        )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="x-apple-disable-message-reformatting">
<meta name="color-scheme" content="dark only">
<title>AgenticOS</title>
<style>
  @media (max-width:480px){{
    .card{{width:100%!important}}
    .px{{padding-left:26px!important;padding-right:26px!important}}
    .h1{{font-size:28px!important}}
    .hero{{font-size:44px!important;letter-spacing:0.1em!important}}
    .btn{{display:block!important;text-align:center!important}}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:{INK_BG};-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">
{preheader}
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{INK_BG};">
<tr><td align="center" style="padding:56px 16px;">

  <table class="card" width="{CARD_WIDTH}" cellpadding="0" cellspacing="0" border="0"
         style="width:{CARD_WIDTH}px;max-width:{CARD_WIDTH}px;background:{CARD_BG};border:1px solid {HAIRLINE};">

    <!-- 顶部琥珀信号线：整套视觉的签名，与内容牌的立边、按钮同源 -->
    <tr><td style="height:3px;background:{AMBER};font-size:0;line-height:0;">&nbsp;</td></tr>

    <!-- 页眉 -->
    <tr><td class="px" style="padding:30px 40px 0;">
      {_header(shell.header_left, shell.header_right)}
    </td></tr>

    <!-- 内容 -->
    <tr><td class="px" style="padding:46px 40px 0;">
      {shell.body}
    </td></tr>

    <!-- 页脚分割 -->
    <tr><td class="px" style="padding:38px 40px 0;">
      <div style="height:1px;background:{HAIRLINE};font-size:0;line-height:0;">&nbsp;</div>
    </td></tr>
    <tr><td class="px" style="padding:15px 40px 28px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
        <td style="font-family:{FONT_SANS};font-size:12px;color:{TEXT_FAINT};">AgenticOS</td>
        <td align="right" style="font-family:{FONT_SANS};font-size:12px;color:{TEXT_FAINT};">系统通知</td>
      </tr></table>
    </td></tr>

  </table>

  <div style="padding:20px 0 0;font-family:{FONT_SANS};font-size:12px;color:{TEXT_LOW};text-align:center;letter-spacing:0.04em;">
    {shell.footer_note}
  </div>

  {feedback_html}

</td></tr>
</table>
</body>
</html>"""


# ── 三个内容布局 ──────────────────────────────────────────────────────

def build_verification_code(code: str, purpose: str, *, ttl_minutes: int = 5) -> str:
    """验证码邮件。验证码是唯一行动目标，给它最大的视觉重量。"""
    action = "登录" if purpose == "login" else "注册"

    body = (
        _eyebrow("一次性验证码")
        + _h1("请在登录页输入")
        + f'<div style="margin-top:28px;">'
        + _inset_block(
            f'<div style="text-align:center;">'
            f'<span class="hero" style="font-family:{FONT_MONO};font-size:54px;'
            f'font-weight:700;letter-spacing:0.16em;color:{TEXT_HI};line-height:1;">'
            f"{_esc(code)}</span></div>"
        )
        + '</div>'
        + f'<div style="margin-top:22px;font-family:{FONT_SANS};font-size:14px;'
        f'line-height:1.8;color:{TEXT_MID};">'
        f"验证码 {ttl_minutes} 分钟内有效，仅可使用一次。若非你本人操作，忽略本邮件即可"
        f" —— 没有验证码，无法完成{action}。</div>"
    )

    return render(
        EmailShell(
            preheader=f"你的 AgenticOS {action}验证码是 {code}，{ttl_minutes} 分钟内有效。",
            header_left="AgenticOS",
            header_right=f"{action}验证",
            body=body,
        )
    )


def build_task_notification(
    task_summary: str,
    duration_str: str,
    session_id: str,
    frontend_base: str = "",
    *,
    is_error: bool = False,
    title_hint: str = "",
) -> str:
    """任务完成 / 失败通知。状态用页眉右上的小圆点 + 文字双重编码。"""
    chat_url = f"{frontend_base}/chat?session={session_id}" if frontend_base else ""

    summary = task_summary.strip()
    if len(summary) > 300:
        summary = summary[:297] + "…"
    summary_html = _esc(summary).replace("\n", "<br>")

    if is_error:
        status_dot = "#c15a54"
        status_text = "未完成"
        status_color = "#d99086"
        title = title_hint or "任务执行失败"
        eyebrow = "后台任务通知"
    else:
        status_dot = "#4f9d72"
        status_text = "已完成"
        status_color = "#7fb397"
        title = title_hint or "任务已完成"
        eyebrow = "后台任务通知"

    # 页眉右侧：小圆点 + 状态文字
    right = (
        f'<table cellpadding="0" cellspacing="0" border="0" align="right"><tr>'
        f'<td style="width:7px;"><div style="width:7px;height:7px;background:{status_dot};'
        f'border-radius:7px;font-size:0;line-height:0;">&nbsp;</div></td>'
        f'<td style="padding-left:7px;">{_esc(status_text)}</td></tr></table>'
    )

    parts = [_eyebrow(eyebrow), _h1(_esc(title))]

    if summary_html:
        parts.append(
            f'<div style="margin-top:26px;">'
            + _inset_block(
                f'<div style="font-family:{FONT_SANS};font-size:14px;line-height:1.8;'
                f'color:#c2d3ca;">{summary_html}</div>'
            )
            + '</div>'
        )

    parts.append(
        f'<div style="margin-top:22px;">'
        + _kv_table(
            [
                ("耗时", duration_str, False),
                ("会话编号", session_id, True),
            ]
        )
        + '</div>'
    )

    if chat_url:
        parts.append(f'<div style="margin-top:28px;">{_button("回到对话查看", chat_url)}</div>')

    return render(
        EmailShell(
            preheader=f"{title}，耗时 {duration_str}。",
            header_left="AgenticOS",
            header_right=right,
            body="".join(parts),
        )
    )


def build_welcome(user_name: str, frontend_base: str = "") -> str:
    """欢迎邮件。一句话定位 + 三条能力 + 一个入口，不堆功能清单。"""
    login_url = f"{frontend_base}/login" if frontend_base else ""

    features: tuple[tuple[str, str], ...] = (
        ("对话", "把需求说清楚，它能查资料、做分析、写代码。"),
        ("文档", "Word / Excel / PPT，直接产出可编辑的文件。"),
        ("建站", "描述想要的页面，构建并部署成可访问的链接。"),
    )

    rows = ""
    for i, (name, desc) in enumerate(features):
        last = i == len(features) - 1
        pad = "padding:0;" if last else "padding:0 0 16px 0;"
        rows += (
            f'<tr>'
            f'<td width="20" valign="top" style="width:20px;padding:3px 0 0;">{_marker(7)}</td>'
            f'<td style="{pad}padding-left:12px;font-family:{FONT_SANS};">'
            f'<div style="font-size:14px;font-weight:600;color:{TEXT_HI};">{_esc(name)}</div>'
            f'<div style="margin-top:3px;font-size:15px;line-height:1.6;color:#8aa398;">{_esc(desc)}</div>'
            f'</td></tr>'
        )

    body = (
        _h1(f"{_esc(user_name)}，<br>欢迎使用 AgenticOS。")
        + f'<div style="margin-top:18px;font-family:{FONT_SANS};font-size:15px;'
        f'line-height:1.85;color:{TEXT_MID};">'
        f"这是一个能把「说清楚的需求」直接变成交付物的工作台 —— 不只是聊天，"
        f"它会真的写出文件、建好网站、跑完分析。</div>"
        + f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin-top:30px;">{rows}</table>'
    )

    if login_url:
        body += f'<div style="margin-top:30px;">{_button("进入 AgenticOS", login_url)}</div>'

    return render(
        EmailShell(
            preheader=f"{user_name}，你的 AgenticOS 账号已经就绪。",
            header_left="AgenticOS",
            header_right="欢迎",
            body=body,
        )
    )


def _wrapped_stat(value: str, label: str) -> str:
    """年度报告里的一格大数字。"""
    return (
        f'<td width="50%" valign="top" style="padding:6px;">'
        f'<div style="background:{INSET_BG};border:1px solid {HAIRLINE};border-radius:10px;'
        f'padding:18px 16px;font-family:{FONT_SANS};">'
        f'<div style="font-size:30px;font-weight:800;line-height:1;color:{TEXT_HI};'
        f'letter-spacing:-0.02em;">{_esc(value)}</div>'
        f'<div style="margin-top:8px;font-size:13px;color:{TEXT_LOW};">{_esc(label)}</div>'
        f'</div></td>'
    )


def build_wrapped(stats: dict, frontend_base: str = "") -> str:
    """个人年度报告邮件。深底印刷视觉 + 大数字 + 一个查看完整报告的入口。

    ``stats`` 来自 ``wrapped_service.compute_wrapped``。无数据时调用方不应发信。
    """
    year = stats.get("year", "")
    name = stats.get("user_name") or "你"
    persona = stats.get("persona") or "全能探索者"
    report_url = f"{frontend_base}/wrapped/{year}" if frontend_base else ""

    def _fmt(n: int) -> str:
        return f"{n:,}"

    grid = (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:26px;">'
        f'<tr>{_wrapped_stat(_fmt(stats.get("total_runs", 0)), "次对话")}'
        f'{_wrapped_stat(str(stats.get("active_days", 0)), "天活跃")}</tr>'
        f'<tr>{_wrapped_stat(_fmt(stats.get("total_tokens", 0)), "Token 往来")}'
        f'{_wrapped_stat(str(stats.get("longest_streak", 0)), "天连续打卡")}</tr>'
        '</table>'
    )

    highlights: list[str] = []
    if stats.get("top_mode_name"):
        highlights.append(f"你最爱的功能是「{_esc(stats['top_mode_name'])}」")
    if stats.get("busiest_hour") is not None:
        highlights.append(f"{int(stats['busiest_hour'])} 点是你最活跃的时刻")
    if stats.get("top_tools"):
        top = stats["top_tools"][0]
        highlights.append(f"用得最多的工具是 {_esc(top['name'])}（{_fmt(top['count'])} 次）")
    highlight_html = ""
    if highlights:
        items = "".join(
            f'<div style="margin-top:8px;font-size:15px;line-height:1.6;color:{TEXT_MID};">'
            f'· {h}</div>' for h in highlights
        )
        highlight_html = f'<div style="margin-top:24px;font-family:{FONT_SANS};">{items}</div>'

    body = (
        _eyebrow(f"{year} 年度回顾")
        + _h1(f"{_esc(name)}，<br>这是你的 {_esc(str(year))}。")
        + f'<div style="margin-top:16px;font-family:{FONT_SANS};font-size:15px;line-height:1.8;'
        f'color:{TEXT_MID};">这一年，AI 眼中的你是 <span style="color:{AMBER};font-weight:700;">'
        f'{_esc(persona)}</span>。几个数字，记下我们一起走过的路。</div>'
        + grid
        + highlight_html
    )
    if report_url:
        body += f'<div style="margin-top:30px;">{_button("查看完整年度报告", report_url)}</div>'

    return render(
        EmailShell(
            preheader=f"{name}，你的 {year} 年度 AI 报告已生成。",
            header_left="AgenticOS",
            header_right=f"{year} Wrapped",
            body=body,
        )
    )


__all__ = [
    "CONTACT_ADDRESS",
    "CONTACT_LABEL",
    "CONTACT_MAILTO",
    "EmailShell",
    "USER_TEMPLATE_CHOICES",
    "USER_THEMES",
    "build_general_message",
    "build_task_notification",
    "build_verification_code",
    "build_welcome",
    "build_wrapped",
    "render",
    "render_user_email",
]


def build_general_message(
    title: str,
    paragraphs: list[str],
    *,
    eyebrow: str = "通知",
    button_label: str = "",
    button_url: str = "",
    signer: str = "",
) -> str:
    """通用商务邮件（供邮箱助手「用模板发」使用）。

    与三个系统模板共用同一套深底印刷视觉，但内容自由：一段标题、若干段落、
    可选一个行动按钮、可选署名。段落按空行切分已在调用方完成，这里逐段渲染。

    为什么不让模型直接写 HTML：模型手写邮件 HTML 几乎必然带 inline emoji、
    居中大标题、渐变按钮那套 AI 味，而且经常在客户端里崩。给它一个结构化
    模板，只填内容，成品稳定且和系统通知同一张脸。
    """
    title = (title or "").strip() or "消息"
    eyebrow = (eyebrow or "通知").strip()

    body = _eyebrow(eyebrow) + _h1(_esc(title))

    # 段落：第一段紧贴标题，其余段间距 16px
    para_html = ""
    for i, p in enumerate(paragraphs):
        text = (p or "").strip()
        if not text:
            continue
        top = 18 if i == 0 else 14
        para_html += (
            f'<div style="margin-top:{top}px;font-family:{FONT_SANS};font-size:15px;'
            f'line-height:1.85;color:{TEXT_MID};">{_esc(text).replace(chr(10), "<br>")}</div>'
        )

    body += para_html

    if button_label and button_url:
        body += f'<div style="margin-top:28px;">{_button(button_label, button_url)}</div>'

    if signer:
        body += (
            f'<div style="margin-top:26px;padding-top:18px;border-top:1px solid {HAIRLINE};'
            f'font-family:{FONT_SANS};font-size:13px;color:{TEXT_LOW};">{_esc(signer)}</div>'
        )

    # preheader：取第一段前 60 字
    first = next((p.strip() for p in paragraphs if p and p.strip()), "")
    preheader = first[:60] + ("…" if len(first) > 60 else "") if first else title

    return render(
        EmailShell(
            preheader=preheader,
            header_left="AgenticOS",
            header_right="通知",
            body=body,
            # 用户自己发的邮件：无反馈页脚、中性页脚文案
            show_feedback=False,
            footer_note="由 AgenticOS 邮箱助手代发",
        )
    )


# ══════════════════════════════════════════════════════════════════
# 用户可选主题（预览面板「瞬间切换模板」用）
#
# 这些是**纯函数渲染器**：给定主题 + 结构化内容，立刻产出 HTML，不经过 LLM。
# 前端切换模板时调 /email/templates/preview，毫秒级返回，用户能实时看到差异。
# 主题设计来自 data/skills/email-design/themes/*.md，那里有完整档案与说明。
# ══════════════════════════════════════════════════════════════════

USER_SANS = FONT_SANS
USER_SERIF = "Georgia,'Times New Roman','Songti SC','SimSun',serif"
USER_MONO = FONT_MONO


@dataclass(frozen=True)
class UserTheme:
    label: str
    page: str       # 页面底
    card: str       # 卡片底
    ink: str        # 标题
    body: str       # 正文
    faint: str      # 次要文字
    rule: str       # 分割线
    accent: str     # 强调色
    font: str       # 字体栈
    dark: bool = False
    border: str = ""      # 卡片描边
    title_size: int = 26
    pad: int = 32


USER_THEMES: dict[str, UserTheme] = {
    "swiss": UserTheme("瑞士网格 · 冷中性", "#f4f5f6", "#ffffff", "#111315", "#4a5259", "#6b737b", "#e3e6e9", "#2f6f4f", USER_SANS),
    "press": UserTheme("书卷编辑 · 衬线", "#e9e4da", "#fbf8f2", "#1c1a17", "#5c5549", "#6f665a", "#cfc6b6", "#9c4f2b", USER_SERIF),
    "terminal": UserTheme("暗底工程 · 等宽", INK_BG, "#0e1c18", "#f2f7f4", "#a9bfb4", "#7f9c90", "#1c302a", AMBER, USER_SANS, dark=True, border="#1c302a", title_size=28),
    "quiet": UserTheme("极简留白", "#ffffff", "#ffffff", "#1a1a1a", "#1a1a1a", "#6e6e6e", "#e6e6e6", "#6e6e6e", USER_SANS, title_size=20, pad=40),
    "warm": UserTheme("暖白明黄 · 有人味", "#f4efe4", "#fffdf7", "#2a2420", "#6b625a", "#9c928a", "#ece5d8", "#f4d63a", USER_SANS),
    "datatable": UserTheme("数字优先 · 扫描友好", "#f6f7f8", "#ffffff", "#1a1d21", "#5c636b", "#6b737b", "#e3e6ea", "#1a7a43", USER_SANS, border="#e3e6ea", title_size=20),
    "editorial": UserTheme("杂志版式 · 大标题", "#f2f2f4", "#ffffff", "#16161a", "#57575f", "#6b6b75", "#dcdce2", "#b0472f", USER_SANS, title_size=30),
    "tufte": UserTheme("数据墨水比 · 极致克制", "#fffefb", "#fffefb", "#111111", "#111111", "#6b6b6b", "#cccccc", "#8c2f2f", USER_SERIF, title_size=24, pad=48),
    "bodoni": UserTheme("报刊 Didone · 高反差", "#f4f2ed", "#ffffff", "#0c0c0c", "#4a4a4a", "#6a6a6a", "#d8d8d8", "#8a1c1c", USER_SERIF, title_size=38, pad=36),
}

#: 预览面板可切换的模板列表（顺序即界面顺序）
USER_TEMPLATE_CHOICES: tuple[tuple[str, str], ...] = (
    ("plain", "纯文本"),
    *[(k, v.label) for k, v in USER_THEMES.items()],
    ("notice", "系统通知（深底印刷）"),
    ("custom", "自定义（让 AI 按 skill 撰写）"),
)


def _user_paras(paragraphs: list[str], theme: UserTheme, *, lead: bool = True) -> str:
    """把纯文本段落渲染成自然段。段内换行转 <br>。"""
    out = ""
    for i, p in enumerate(paragraphs):
        text = (p or "").strip()
        if not text:
            continue
        top = 14 if i else (18 if lead else 0)
        out += (
            f'<div style="margin-top:{top}px;font-family:{theme.font};font-size:15px;'
            f'line-height:1.82;color:{theme.body};">'
            f"{_esc(text).replace(chr(10), '<br>')}</div>"
        )
    return out


def _user_button(label: str, url: str, theme: UserTheme) -> str:
    if not (label and url):
        return ""
    # 明黄/琥珀底要配深墨字，其余配白字
    dark_text = theme.accent.lower() in (AMBER.lower(), "#f4d63a")
    fg = "#1a1206" if dark_text else "#ffffff"
    return (
        f'<div style="margin-top:26px;"><table cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td style="background:{theme.accent};border-radius:6px;">'
        f'<a href="{_esc(url)}" style="display:inline-block;padding:11px 26px;color:{fg};'
        f'font-size:14px;font-weight:600;text-decoration:none;font-family:{USER_SANS};">'
        f"{_esc(label)}</a></td></tr></table></div>"
    )


def _user_signer(signer: str, theme: UserTheme) -> str:
    if not signer:
        return ""
    return (
        f'<div style="margin-top:26px;font-family:{theme.font};font-size:14px;'
        f'color:{theme.faint};">{_esc(signer)}</div>'
    )


def _user_footer_rule(theme: UserTheme) -> str:
    return (
        f'<div style="margin-top:28px;height:1px;background:{theme.rule};'
        f'font-size:0;line-height:0;">&nbsp;</div>'
        f'<div style="padding-top:14px;padding-bottom:22px;font-family:{USER_SANS};'
        f'font-size:12px;color:{theme.faint};">AGENTICOS</div>'
    )


def _user_header(theme_id: str, theme: UserTheme, subject: str) -> str:
    """各主题差异最大的部分：页眉记号 + 标题区 + 特殊强调块。"""
    title = _esc(subject)
    font = theme.font
    ink = theme.ink
    acc = theme.accent
    rule = theme.rule

    # ── swiss：2px 顶线 + 品牌行 + 单细线 ──
    if theme_id == "swiss":
        return (
            f'<tr><td style="height:2px;background:{ink};font-size:0;line-height:0;">&nbsp;</td></tr>'
            f'<tr><td class="px" style="padding:22px {theme.pad}px 14px;">'
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td style="font-family:{font};font-size:14px;font-weight:700;color:{ink};">AgenticOS</td>'
            f'</tr></table></td></tr>'
            f'<tr><td class="px" style="padding:0 {theme.pad}px;"><div style="height:1px;background:{rule};">&nbsp;</div></td></tr>'
            f'<tr><td class="px" style="padding:28px {theme.pad}px 0;">'
            f'<div style="font-family:{font};font-size:{theme.title_size}px;font-weight:600;line-height:1.3;color:{ink};">{title}</div>'
            f'</td></tr>'
        )

    # ── press：赭色短竖线报头 + 双细线 ──
    if theme_id == "press":
        return (
            f'<tr><td class="px" style="padding:26px {theme.pad}px 0;">'
            f'<table cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td style="width:3px;height:20px;background:{acc};">&nbsp;</td>'
            f'<td style="padding-left:10px;font-family:{font};font-size:19px;font-weight:700;color:{ink};">AgenticOS</td>'
            f'</tr></table></td></tr>'
            f'<tr><td class="px" style="padding:16px {theme.pad}px 0;">'
            f'<div style="height:1px;background:{ink};">&nbsp;</div>'
            f'<div style="height:3px;background:{theme.card};">&nbsp;</div>'
            f'<div style="height:1px;background:{ink};">&nbsp;</div></td></tr>'
            f'<tr><td class="px" style="padding:26px {theme.pad}px 0;">'
            f'<div style="font-family:{font};font-size:{theme.title_size}px;font-weight:700;line-height:1.35;color:{ink};">{title}</div>'
            f'</td></tr>'
        )

    # ── terminal：琥珀顶线 + 品牌行 + 立边内容牌由调用方加 ──
    if theme_id == "terminal":
        return (
            f'<tr><td style="height:3px;background:{acc};font-size:0;line-height:0;">&nbsp;</td></tr>'
            f'<tr><td class="px" style="padding:24px {theme.pad}px 0;">'
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td style="font-family:{font};font-size:14px;font-weight:700;color:{ink};">AgenticOS</td>'
            f'<td align="right" style="font-family:{font};font-size:12px;color:{theme.faint};">通知</td>'
            f'</tr></table></td></tr>'
            f'<tr><td class="px" style="padding:30px {theme.pad}px 0;">'
            f'<div style="font-family:{font};font-size:{theme.title_size}px;font-weight:800;line-height:1.25;color:{ink};letter-spacing:-0.01em;">{title}</div>'
            f'</td></tr>'
        )

    # ── quiet：字标 + 大留白 ──
    if theme_id == "quiet":
        return (
            f'<tr><td class="px" style="padding:0 {theme.pad}px;">'
            f'<div style="font-family:{font};font-size:14px;font-weight:600;letter-spacing:0.16em;color:{theme.faint};">AGENTICOS</div>'
            f'</td></tr><tr><td style="height:48px;">&nbsp;</td></tr>'
            f'<tr><td class="px" style="padding:0 {theme.pad}px;">'
            f'<div style="font-family:{font};font-size:{theme.title_size}px;font-weight:600;line-height:1.4;color:{ink};">{title}</div>'
            f'</td></tr>'
        )

    # ── warm：品牌行 + 标题里高亮最后一个词 ──
    if theme_id == "warm":
        # 把标题最后一个"词组"用明黄底高亮（荧光笔，不是文字色）
        parts = subject.rsplit(" ", 1)
        if len(parts) == 2 and len(parts[1]) <= 8:
            highlighted = (
                f"{_esc(parts[0])} "
                f'<span style="background:{acc};padding:0 4px;border-radius:3px;">{_esc(parts[1])}</span>'
            )
        else:
            highlighted = title
        return (
            f'<tr><td class="px" style="padding:28px {theme.pad}px 0;">'
            f'<div style="font-family:{font};font-size:15px;font-weight:700;color:{ink};">AgenticOS</div>'
            f'</td></tr>'
            f'<tr><td class="px" style="padding:14px {theme.pad}px 0;">'
            f'<div style="font-family:{font};font-size:{theme.title_size}px;font-weight:700;line-height:1.35;color:{ink};">{highlighted}</div>'
            f'</td></tr>'
        )

    # ── datatable：标题 + 周期 meta + 键值表占位（正文由段落渲染） ──
    if theme_id == "datatable":
        return (
            f'<tr><td class="px" style="padding:26px {theme.pad}px 0;">'
            f'<div style="font-family:{font};font-size:{theme.title_size}px;font-weight:600;color:{ink};">{title}</div>'
            f'<div style="margin-top:6px;font-family:{font};font-size:13px;color:{theme.faint};">数据摘要</div>'
            f'</td></tr>'
        )

    # ── editorial：砖红栏目记号 + 大标题 ──
    if theme_id == "editorial":
        return (
            f'<tr><td class="px" style="padding:28px {theme.pad}px 0;">'
            f'<table cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td style="width:3px;height:14px;background:{acc};">&nbsp;</td>'
            f'<td style="padding-left:8px;font-family:{font};font-size:12px;font-weight:700;letter-spacing:0.14em;color:{acc};">通知</td>'
            f'</tr></table></td></tr>'
            f'<tr><td class="px" style="padding:14px {theme.pad}px 0;">'
            f'<div style="font-family:{font};font-size:{theme.title_size}px;font-weight:700;line-height:1.25;color:{ink};letter-spacing:-0.01em;">{title}</div>'
            f'</td></tr>'
        )

    # ── tufte：衬线字标 + 发丝线 + 大页边标题 ──
    if theme_id == "tufte":
        return (
            f'<tr><td class="px" style="padding:0 {theme.pad}px;">'
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td style="font-family:{font};font-size:15px;color:{ink};">AgenticOS</td>'
            f'</tr></table><div style="height:1px;background:{rule};margin-top:10px;">&nbsp;</div></td></tr>'
            f'<tr><td class="px" style="padding:30px {theme.pad}px 0;">'
            f'<div style="font-family:{font};font-size:{theme.title_size}px;font-weight:600;line-height:1.4;color:{ink};">{title}</div>'
            f'</td></tr>'
        )

    # ── bodoni：粗细双线刊头 + 极高对比大标题 ──
    if theme_id == "bodoni":
        return (
            f'<tr><td class="px" style="padding:24px {theme.pad}px 0;">'
            f'<div style="height:3px;background:{ink};">&nbsp;</div>'
            f'<div style="height:1px;background:{ink};margin-top:4px;">&nbsp;</div></td></tr>'
            f'<tr><td class="px" style="padding:22px {theme.pad}px 0;">'
            f'<div style="font-family:{font};font-size:{theme.title_size}px;font-weight:700;line-height:1.12;color:{ink};letter-spacing:-0.01em;">{title}</div>'
            f'</td></tr>'
            f'<tr><td class="px" style="padding:18px {theme.pad}px 0;">'
            f'<div style="height:1px;background:{rule};">&nbsp;</div>'
            f'<div style="padding-top:10px;font-family:{font};font-size:11px;letter-spacing:0.22em;color:{theme.faint};">NOTICE&nbsp;&nbsp;·&nbsp;&nbsp;AGENTICOS</div>'
            f'</td></tr>'
        )

    raise ValueError(f"未知主题：{theme_id}")


def render_user_email(
    template: str,
    subject: str,
    body: str,
    *,
    button_label: str = "",
    button_url: str = "",
    signer: str = "",
) -> tuple[str, bool]:
    """把一封用户邮件按选定模板渲染成 (html, is_html)。

    **纯函数、无 IO、不经过 LLM** —— 前端切换模板时调用它，瞬间出结果。
    返回 ``is_html`` 告诉调用方该用哪种 MIME subtype 发送。

    - ``plain``：返回原始纯文本，is_html=False
    - ``notice``：复用系统通知模板 build_general_message
    - 其他：``USER_THEMES`` 里的 9 套主题
    - ``custom``：不在后端渲染（交给 AI 按 skill 手写），这里回退到 plain
    """
    paragraphs = [p for p in (body or "").split("\n\n") if p.strip()]
    subject = (subject or "").strip() or "（无主题）"

    if template in ("plain", "custom", ""):
        return body, False

    if template == "notice":
        return (
            build_general_message(
                subject, paragraphs,
                button_label=button_label, button_url=button_url, signer=signer,
            ),
            True,
        )

    theme = USER_THEMES.get(template)
    if theme is None:
        raise ValueError(f"未知模板：{template}")

    header = _user_header(template, theme, subject)
    paras = _user_paras(paragraphs, theme)
    btn = _user_button(button_label, button_url, theme)
    sign = _user_signer(signer, theme)
    footer = _user_footer_rule(theme)

    # 内容区统一包一层 td；dark 主题（terminal）给正文立边牌
    if theme.dark:
        content = (
            f'<tr><td class="px" style="padding:22px {theme.pad}px 0;">'
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="background:{INK_BG};border-left:3px solid {theme.accent};">'
            f'<tr><td style="padding:20px 22px;">{paras}</td></tr></table></td></tr>'
            f'<tr><td class="px" style="padding:22px {theme.pad}px 0;">{btn}{sign}{footer}</td></tr>'
        )
    else:
        content = (
            f'<tr><td class="px" style="padding:16px {theme.pad}px 0;">'
            f"{paras}{btn}{sign}{footer}</td></tr>"
        )

    html = _user_shell(theme, header + content, preheader=subject)
    return html, True


def _user_shell(theme: UserTheme, inner: str, *, preheader: str) -> str:
    """所有用户主题共用的外层：DOCTYPE / 页面底 / 居中卡片 / 页脚。"""
    border = f"border:1px solid {theme.border};" if theme.border else ""
    footer = (
        f'<div style="padding:18px 0 0;font-family:{USER_SANS};font-size:12px;'
        f'color:{theme.faint};text-align:center;">由 AgenticOS 邮箱助手代发</div>'
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="x-apple-disable-message-reformatting">
<title>{_esc(preheader)}</title>
<style>@media (max-width:480px){{.card{{width:100%!important}}.px{{padding-left:24px!important;padding-right:24px!important}}}}</style>
</head>
<body style="margin:0;padding:0;background:{theme.page};-webkit-text-size-adjust:100%;">
<div style="display:none;font-size:1px;color:{theme.page};line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;">{_esc(preheader)}</div>
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{theme.page};">
<tr><td align="center" style="padding:44px 16px;">
  <table class="card" width="600" cellpadding="0" cellspacing="0" border="0"
         style="width:600px;max-width:600px;background:{theme.card};{border}">
    {inner}
  </table>
  {footer}
</td></tr></table></body></html>"""
