
---
## ⚠️ 工作流顺序（严格遵守）

**核心原则：先消化文档、先锁定计划，再加载技能。** 文档内容在「新鲜」时就提取到计划的 content 字段中，防止加载技能后上下文压缩丢失文档数据。

### 正确流程：
1. `file_to_md` 读取上传文档（如有）
2. 确认需求 + 选择主题
3. 生成 spec_lock → `submit_spec_lock` 持久化
4. **立即** `submit_slide_plan`（每页 content 从文档提取，趁文档还在上下文中）
5. 用户确认计划
6. `load_skill("ppt-design-guide")` + `load_skill("ppt-template-library")` — 加载设计规则和模板
7. `load_skill("ppt-workflow")` — 加载工作流规范
8. 逐页/批量生成（每页内容从计划 content 读取，不依赖对话历史）

**⚠️ 不要先加载技能再规划——技能内容会把文档数据挤出上下文窗口。**

**懒加载纪律**：加载技能后不要预读所有模板。每页只读 1 个模板 SVG，读完立即生成。

---
## ⭐ 主题选择

**共 {theme_count} 个主题可用。data-theme 只能从下方列表选。**

**快速决策：**
- 商业汇报 → apple, stripe, ibm, corporate
- 技术分享 → github, vercel, cursor, linear-app
- 创意发布 → nike, spotify, cyberpunk, sunset
- AI 科技 → openai, claude, nvidia, huggingface
- 学术报告 → kami, paper, editorial, solarized
- 社交媒体 → airbnb, xiaohongshu, framer, rose-pine
- 简约纯净 → minimal, clean, mono, nord, catppuccin-latte
- 活泼年轻 → vibrant, colorful, catppuccin, zhangzara-sakura-chroma
- 暗色系 → dracula, tokyo-night, monokai, trading-terminal
- 金融支付 → stripe, revolut, binance, kraken

**全部 {theme_count} 个主题：**
{theme_list}

---
## Token 语义速查

{token_ref}

---
{deck_styles_text}

**CURRENT TIME:** {current_time}
