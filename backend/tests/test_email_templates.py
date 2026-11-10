"""邮件模板回归测试。

这些是踩过的坑，不是形状测试：
1. 邮件里不能出现 class 选择器（Gmail 剥掉，样式全失效）；
2. 关键样式必须内联，布局必须 table（Outlook 不支持 flex/grid）；
3. 用户可控文本必须转义，否则摘要里的 `<` 会打破结构；
4. 深底模板必须保证正文对比度（本次改版的核心可读性红线）；
5. 失败/完成状态要靠颜色区分，但按钮不能写死一种色。
"""
from __future__ import annotations

import re

import pytest

from app.services import email_templates as et


ALL_BUILDERS = [
    ("code", lambda: et.build_verification_code("482913", "login")),
    ("code-signup", lambda: et.build_verification_code("111222", "signup")),
    ("task-ok", lambda: et.build_task_notification("做完了", "1 分", "sid1", "http://x")),
    ("task-err", lambda: et.build_task_notification("失败了", "1 分", "sid2", "http://x", is_error=True)),
    ("welcome", lambda: et.build_welcome("张三", "http://x")),
    ("welcome-no-base", lambda: et.build_welcome("李四", "")),
    ("task-no-base", lambda: et.build_task_notification("无链接", "1 分", "sid3", "")),
]


@pytest.mark.parametrize("name,builder", ALL_BUILDERS)
def test_no_style_element_class_selectors(name, builder):
    """不能依赖 class 选择器：Gmail 会剥掉 <style>，主体必须靠内联样式。"""
    page = builder()
    # <style> 里只允许媒体查询（渐进增强的窄屏微调），不允许任何非媒体查询的文字样式
    styles = re.findall(r"<style>(.*?)</style>", page, re.S)
    for block in styles:
        # 去掉 @media 块后应基本为空（只剩空白 / 花括号）
        stripped = re.sub(r"@media[^{]*\{(?:[^{}]|\{[^{}]*\})*\}", "", block).strip()
        assert stripped in ("", "}"), f"{name}: <style> 里出现了媒体查询之外的规则：{stripped[:80]}"
    # 主体样式必须内联：用 style= 的数量做下限（一封最简邮件也有 20+ 处）
    assert page.count('style="') > 15, f"{name}: 内联样式太少，可能在依赖 <style>"


@pytest.mark.parametrize("name,builder", ALL_BUILDERS)
def test_layout_uses_tables_not_flex_or_grid(name, builder):
    page = builder().lower()
    assert "display:flex" not in page, f"{name}: 不能用 flex"
    assert "display:grid" not in page, f"{name}: 不能用 grid"
    assert "<table" in page, f"{name}: 必须用 table 布局"


@pytest.mark.parametrize("name,builder", ALL_BUILDERS)
def test_has_preheader_and_no_external_images(name, builder):
    page = builder()
    assert "display:none" in page.replace(" ", ""), f"{name}: 缺少 preheader"
    assert "<img" not in page.lower(), f"{name}: 不应依赖外链图片"
    # 品牌记号是纯 CSS 色块，不是图片
    assert et.AMBER in page


def test_dark_background_and_amber_accent():
    """整套视觉：深墨绿底 + 琥珀强调，深底模板的核心。"""
    page = et.build_verification_code("482913", "login")
    assert et.INK_BG.lower() in page.lower()
    assert et.AMBER.lower() in page.lower()


def test_task_summary_is_escaped():
    """摘要里的 HTML 标签必须被转义，否则会破坏邮件结构。"""
    page = et.build_task_notification(
        '用户输入 <script>alert("x")</script> 与 & 符号',
        "1 分", "sid", "http://x",
    )
    assert "<script>" not in page
    assert "&lt;script&gt;" in page
    assert "&amp;" in page


def test_status_distinguished_by_color_not_hardcoded_button():
    """完成与失败用不同状态色；按钮是琥珀实心，不随状态写死一种品牌色。"""
    ok = et.build_task_notification("ok", "1s", "s", "http://x")
    err = et.build_task_notification("err", "1s", "s", "http://x", is_error=True)
    # 两种状态色不同
    assert "#4f9d72" in ok   # 成功绿点
    assert "#c15a54" in err  # 失败红点
    # 按钮始终是琥珀（品牌色），不是状态色
    assert f"background:{et.AMBER}" in ok
    assert f"background:{et.AMBER}" in err


def test_verification_code_renders_and_escapes():
    page = et.build_verification_code("482913", "login", ttl_minutes=5)
    for ch in "482913":
        assert ch in page
    assert "5 分钟内有效" in page


def test_welcome_lists_exactly_three_features():
    """欢迎邮件列出三条能力（每条一个琥珀记号）。"""
    page = et.build_welcome("张三", "http://x")
    # 页眉记号 + 三条能力记号 = 至少 4 枚琥珀色块
    amber_blocks = page.count(f"background:{et.AMBER};")
    assert amber_blocks >= 4, f"琥珀记号数量不足：{amber_blocks}"
    for name in ("对话", "文档", "建站"):
        assert name in page


def test_welcome_without_base_url_has_no_broken_link():
    page = et.build_welcome("李四", "")
    assert 'href=""' not in page


def test_task_mail_without_base_url_has_no_button():
    page = et.build_task_notification("x", "1s", "s", "")
    assert 'href=""' not in page
    assert "回到对话查看" not in page


def test_no_css_keyframes_and_no_emoji():
    """动效只能靠 transition / SMIL；emoji 一律不要（AI 味的典型来源）。"""
    for name, builder in ALL_BUILDERS:
        page = builder()
        assert "@keyframes" not in page, f"{name}: 不应有 @keyframes"
        # 常见 emoji 范围粗筛
        assert not re.search(r"[\U0001F300-\U0001FAFF\u2705\u274C]", page), f"{name}: 出现了 emoji"


def test_all_emails_carry_unobtrusive_contact_link():
    """每封邮件页脚都要有不显眼的「联系 731302」mailto 链接。

    - mailto: 点击唤起本机邮件客户端，是邮件里唯一可靠的「联系」交互；
    - **收件人必须是完整邮箱** 731302@gree.com.cn，只写工号客户端会当成无效地址；
    - 必须做得不显眼：12px + 低对比色，不能抢主信息。
    """
    for name, builder in ALL_BUILDERS:
        page = builder()
        assert f"mailto:{et.CONTACT_ADDRESS}" in page, f"{name}: 缺少联系链接"
        assert "@gree.com.cn" in page, f"{name}: mailto 收件人缺域名"
        assert "731302" in page, f"{name}: 缺少联系人标识"
        # 不显眼：链接所在行是 12px 低对比
        link_line = re.search(r"<a href=\"mailto:[^\"]*@gree\.com\.cn[^\"]*\"[^>]*>", page)
        assert link_line, f"{name}: mailto 链接格式异常"


def test_general_message_has_no_system_feedback_footer():
    """用户自己发的邮件不该带系统反馈链接 / 「系统自动发出」文案。

    反馈入口是给平台用户的通知邮件用的；私人邮件塞平台页脚会很怪。
    """
    page = et.build_general_message("会议调整", ["正文。"])
    assert f"mailto:{et.CONTACT_ADDRESS}" not in page, "用户邮件不该带平台反馈链接"
    assert "系统自动发出" not in page, "用户邮件不该宣称「系统自动发出」"
    # 但仍是完整邮件
    assert page.startswith("<!DOCTYPE html>") and page.rstrip().endswith("</html>")


def test_system_mails_keep_feedback_link():
    """系统通知邮件保留反馈入口（收信人是平台用户），且收件人是完整邮箱。"""
    assert f"mailto:{et.CONTACT_ADDRESS}" in et.build_verification_code("482913", "login")
    assert f"mailto:{et.CONTACT_ADDRESS}" in et.build_welcome("张三", "http://x")
    assert f"mailto:{et.CONTACT_ADDRESS}" in et.build_task_notification("x", "1s", "s", "http://x")
    assert et.CONTACT_ADDRESS == "731302@gree.com.cn", "反馈收件人必须是完整邮箱"


def test_general_message_template_for_email_assistant():
    """邮箱助手「用模板发」用的通用模板：段落切分、按钮、署名、转义。"""
    page = et.build_general_message(
        "会议调整",
        ["第一段。", "第二段\n带换行。"],
        button_label="查看日程",
        button_url="https://example.com/meeting/1",
        signer="邮箱助手",
    )
    assert "会议调整" in page
    assert "第一段" in page and "第二段" in page
    assert "<br>" in page, "段内换行应转成 <br>"
    assert "查看日程" in page and "meeting/1" in page
    assert "邮箱助手" in page
    # 用户自己发的邮件不带平台反馈链接
    assert f"mailto:{et.CONTACT_ADDRESS}" not in page
    opens = len(re.findall(r"<table\b", page))
    closes = len(re.findall(r"</table>", page))
    assert opens == closes


def test_general_message_escapes_injection():
    page = et.build_general_message("<script>", ["<img src=x onerror=1>"])
    assert "<script>" not in page
    assert "&lt;script&gt;" in page
    assert "onerror=1>" not in page  # 原始标签被转义


def test_general_message_without_button_or_signer_stays_clean():
    page = et.build_general_message("简短", ["一段话。"])
    assert 'href="http' not in page  # 无按钮时不生成外链


def test_output_is_wellformed_enough():
    """基本结构检查 —— 邮件里标签错位会整封渲染乱掉。"""
    for name, builder in ALL_BUILDERS:
        page = builder()
        assert page.startswith("<!DOCTYPE html>"), f"{name}: 缺少 DOCTYPE"
        assert page.rstrip().endswith("</html>"), f"{name}: 未正确闭合"
        opens = len(re.findall(r"<table\b", page))
        closes = len(re.findall(r"</table>", page))
        assert opens == closes, f"{name}: table 未配对（{opens} 开 / {closes} 闭）"
