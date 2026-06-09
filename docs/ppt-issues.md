# PPT 智能体已知问题与优化方案

> 创建日期：2026-06-10
> 状态：待实施

---

## 问题一：生成过程中无法实时预览

### 问题描述

用户发起 PPT 生成后，需要等待 **60-180 秒**（8-12 页）才能看到任何视觉内容。在此期间前端只显示"正在生成 PPT 内容与版式"文字状态，没有任何进度指示或预览。

### 当前流程时序

```
[0s]     前端显示 "generating_ppt" 状态文字
[5s]     LLM 开始思考
[8s]     save_slide 第1页 → tool_results（前端只显示工具调用记录）
[18s]    save_slide 第2页 → tool_results
[28s]    save_slide 第3页 → tool_results
...                         ↑ 用户在这里什么视觉反馈都没有
[150s]   save_slide 第12页 → tool_results
[150.3s] 后端运行 artifact pipeline（质量检查 + token 解析 + HTML 包装）~300ms
[150.5s] 发送 artifact_ready → 前端一次性渲染全部 12 页
```

### 根因分析

1. **`_create_ppt_artifact` 只在 agent 完全结束后执行**（`agent_service.py:1740`）。它是一个后处理步骤，不是增量的。
2. **前端不处理 `tool_results` 中的 SVG 内容**。`save_slide` 的返回值只有确认文字（如"第 3 页已保存"），不包含 SVG 内容。
3. **无增量 SSE 事件**。后端没有在 `save_slide` 完成后发送任何携带预览数据的 SSE 事件。

### 涉及文件

| 文件 | 角色 |
|------|------|
| `backend/app/tools/ppt_tools.py` | `save_slide` 工具定义，只返回确认文字 |
| `backend/app/services/agent_service.py:1740` | `_create_ppt_artifact` 在 `done` 事件后才执行 |
| `backend/app/services/ppt_artifact_service.py:185` | `create_from_slides_dir` 全量处理 pipeline |
| `frontend/src/hooks/useChatStream.ts:303` | `onDelta` 只更新文本，不处理工具结果中的 SVG |
| `frontend/src/components/ppt/PptArtifactPanel.tsx` | 只在 `artifact_ready` 后才渲染 |

### 推荐方案：方案 A — 前端直接渲染原始 SVG

**原理：** 在 `save_slide` 的 `tool_results` 中附带原始 SVG 内容，前端直接用 `<div dangerouslySetInnerHTML>` 渲染为缩略图列表。

**后端改动：**
```python
# ppt_tools.py — save_slide 返回时附带 SVG 内容
return f"第 {slide_num} 页已保存（共 {slide_num} 页）\n<svg_preview>{svg_content}</svg_preview>"
```

**前端改动：**
```tsx
// 从 tool_results 中提取 <svg_preview> 标签，渲染为缩略图列表
// 不需要 iframe，不需要 token 解析，不需要质量检查
```

**评估：**

| 维度 | 影响 |
|------|------|
| 后端改动 | ~20 行 |
| 前端改动 | ~100 行（缩略图列表组件） |
| SSE 带宽 | 每页多传 50-200KB SVG，12 页总计 ~1MB（gzip 后 ~200KB） |
| 渲染质量 | 原始 SVG，含 `var(--xxx)` 未解析（颜色可能不对） |
| 一致性风险 | 无 — 只是预览，最终渲染仍用完整 pipeline |
| 延迟增加 | 零 |

**备选方案：方案 B — 后端逐页处理 + 增量 SSE**

`save_slide` 后立即对该页运行轻量处理（token 解析 + XML 清洗），通过新 SSE 事件 `slide_preview` 发送。渲染质量更高（颜色正确），但实现成本增加（~200 行后端 + ~200 行前端），且存在逐页与全量解析的微小一致性差异。

**结论：推荐方案 A。** 投入产出比最高，零风险，"颜色不对"在预览阶段可接受。

---

## 问题二：参考文档未被 LLM 使用

### 问题描述

用户上传参考文档（PDF、Word、Excel 等），期望 PPT 内容基于文档数据生成，但 LLM 实际上没有参考文档内容，生成的 PPT 使用的是 LLM 自身的通用知识。

### 当前流程

```
用户上传 "2025年AI市场报告.pdf"
  → 后端存储文件，发送 user message: "文档文件，用 file_to_md(path=...) 读取内容"
  → LLM 看到提示，应该先调用 file_to_md
  → [问题1] LLM 可能跳过 file_to_md，直接开始规划
  → [问题2] 即使调用了 file_to_md，返回的 5000 字文档内容进入对话历史
  → 第 16 轮后 ContextCompressionMiddleware 触发
  → 文档内容被压缩为: "用户上传了一份关于AI市场的报告"
  → 后续幻灯片完全丢失原始数据
```

### 根因分析

**根因 A：无强制读取机制**

系统提示词（`prompts.py:78`）说"必须先调用 `file_to_md` 读取所有上传文件"，但这只是提示词层面的指令。没有代码级强制：没有 Middleware 检查 `file_to_md` 是否被调用，没有 guard 在 `save_slide` 前验证文档是否已读取。

**根因 B：上下文压缩销毁文档内容**

`ContextCompressionMiddleware` 在 ~16 轮后触发，将旧消息替换为 LLM 生成的摘要。`file_to_md` 返回的完整文档文本（可能 5000+ tokens）会被压缩为几个要点，丢失所有具体数据、统计数字和引用。

- 配置：`context_compress_after_turns=16`，`context_keep_recent_turns=6`（`config.py`）
- 8-12 页 PPT 轻松超过 16 轮（每页至少 2 轮：`save_slide` + 工具结果）
- 压缩摘要只保留"Resolved Questions / Pending Questions / Active Task / Key Findings"，不保留原始数据

**根因 C：`file_to_md` 输出可能非常大**

大 PDF 转 Markdown 可能产生数千 tokens。这些内容占据对话历史中间位置，压缩时首先被摘要化。

### 涉及文件

| 文件 | 角色 |
|------|------|
| `backend/app/services/agent_service.py:1238` | `_build_user_message` 构建文件描述消息 |
| `backend/app/services/agent_service.py:1613` | 文件描述追加到 user message |
| `backend/app/prompts.py:78` | PPT 系统提示词要求先读文件 |
| `backend/app/tools/file_to_md_tool.py` | `file_to_md` 工具实现 |
| `data/skills/ppt-workflow/SKILL.md:236-253` | 文件上传处理指引 |
| `wuwei/middleware/context_compression.py` | 上下文压缩中间件（外部依赖） |
| `backend/app/core/config.py` | 压缩轮次配置 |

---

## 问题三：生成计划未被 LLM 遵循

### 问题描述

LLM 在规划阶段输出了 spec_lock（设计参数锁定表）和幻灯片计划（每页标题、布局），但在后续生成过程中偏离计划：使用不同的配色、改变布局、跳过计划中的页面、或添加计划外的页面。

### 当前流程

```
LLM 输出 spec_lock（主题、配色、字体、图标库）
  → LLM 调用 submit_slide_plan(slides='[{slide_num:1, layout:"cover", ...}, ...]')
  → 计划存入模块级变量 _pending_slide_plan（ppt_tools.py:138）
  → 触发用户决策面板，用户确认
  → 计划仅存在于对话历史中
  → LLM 开始逐页生成（10+ 轮工具调用）
  → 第 16 轮后 ContextCompressionMiddleware 触发
  → spec_lock 被压缩为: "使用了 executive 主题"
  → 计划被压缩为: "计划生成 10 页 PPT"
  → LLM 丢失详细参数，凭"记忆"生成后续页面
  → 偏离计划
```

### 根因分析

**根因 A：计划从未被持久化或重新注入**

`submit_slide_plan` 将计划存入 `_pending_slide_plan` 模块级变量，注释说"由 agent_service 在 phase transition 时同步到 session metadata"。但这个同步**从未实现**：

- `pop_pending_slide_plan()` 函数存在但**生产代码中从未被调用**
- 搜索整个 `backend/app/` 目录，`ppt_spec_lock` 和 `ppt_slide_plan` 只出现在测试 mock 中
- 计划仅作为 tool call 的参数和返回值存在于对话历史中

**根因 B：无生成时验证**

没有代码在 `save_slide` 前后：
- 检查当前生成的页面是否匹配计划中的布局
- 验证 `save_slide` 调用次数是否与计划页数一致
- 阻止 LLM 偏离计划

spec_lock 的"每页生成前回顾 spec_lock"只是提示词建议，LLM 必须主动从对话历史中找回自己的早期输出。

**根因 C：上下文压缩销毁计划**

与问题二相同的机制。spec_lock 文本和计划 JSON 作为 assistant 消息存在于对话历史中，16 轮后被压缩为模糊摘要。

**根因 D：`_pending_slide_plan` 在每次 stream 开始时被重置**

`reset_slides_dir_cache()`（ppt_tools.py:22-26）将 `_pending_slide_plan` 设为 `None`。

### 涉及文件

| 文件 | 角色 |
|------|------|
| `backend/app/tools/ppt_tools.py:112-158` | `submit_slide_plan` 工具定义 |
| `backend/app/tools/ppt_tools.py:29` | `pop_pending_slide_plan` 存在但未使用 |
| `backend/app/tools/ppt_tools.py:22-26` | `reset_slides_dir_cache` 重置计划 |
| `backend/app/prompts.py:74-87` | PPT 7 步工作流提示词 |
| `data/skills/ppt-workflow/SKILL.md:97-149` | spec_lock 机制定义 |
| `wuwei/middleware/context_compression.py` | 上下文压缩中间件 |

---

## 共享根因

三个问题共享同一个架构缺陷：

> **系统完全依赖 LLM 自律来维持关键不变量，没有代码级强制；上下文压缩进一步破坏了这种自律，因为压缩会销毁参考材料。**

```
                    对话轮次
    1─────6──────12──────16──────20──────→
    │     │       │       │       │
    │  读文档  生成1-6页  压缩触发  生成7-12页
    │  输出spec_lock      │       │
    │  提交计划            │       │
    │     │       │       │       │
    │  ✅ 正常    ✅ 正常  │  ❌ 丢失文档
    │                     │  ❌ 丢失计划
    │                     │  ❌ 丢失spec_lock
```

---

## 解决方案概述

### 核心思路：内容型计划 + 持久化注入

**不在中间存文档原文，而是在计划阶段就把文档内容"消化"到每一页的描述里。**

```
当前：文档 → 对话历史 → 被压缩 → 丢失
优化：文档 → LLM 提取关键数据 → 写入计划每页 content 字段 → 持久化 → 每页注入
```

### 改造后的计划格式

**当前（太粗糙）：**
```json
[
  {"slide_num": 1, "layout": "cover", "title": "AI市场分析"},
  {"slide_num": 2, "layout": "bullets", "title": "市场背景"},
  {"slide_num": 3, "layout": "kpi-grid", "title": "关键数据"}
]
```

**改造后（携带内容）：**
```json
[
  {
    "slide_num": 1,
    "layout": "cover",
    "title": "2025年AI市场分析报告",
    "content": "副标题: 基于行业调研的深度洞察 | 日期: 2025年6月"
  },
  {
    "slide_num": 2,
    "layout": "bullets",
    "title": "市场背景",
    "content": "• 全球AI市场规模达5500亿美元(来源: 报告P3)\n• 年增长率42%，预计2028年突破1.5万亿\n• 中国AI市场占全球28%，增速领先\n• 生成式AI是增长最快的细分领域"
  },
  {
    "slide_num": 3,
    "layout": "kpi-grid",
    "title": "关键数据",
    "content": "KPI1: 5500亿 | 全球AI市场规模\nKPI2: 42% | 年复合增长率\nKPI3: 3x | 推理速度提升\nKPI4: 60% | 成本降低幅度"
  }
]
```

每页的 `content` 字段是从参考文档中提取的、该页需要展示的具体数据。生成该页时直接注入上下文，不需要回头读文档。

### 注入约束指令

每次 `save_slide` 前，向 LLM 注入当前页的计划内容，并附带约束：

```markdown
## 当前任务：生成第3页

**数据来源（必须使用，不可编造、不可修改数据值）：**
- 全球AI市场规模: 5500亿美元 (来源: 报告P3)
- 年复合增长率: 42% (来源: 报告P5)
- 中国AI市场占比: 28%，约1540亿美元

**允许优化：**
- 可以调整文案格式（如 "5500亿" → "¥5,500亿"）
- 可以精简描述（如 "年复合增长率" → "CAGR"）
- 可以调整排版层次（标题/副标题/正文分配）

**禁止：**
- 禁止编造计划中没有的数据
- 禁止忽略计划中的数据点
- 禁止用"等"、"约"模糊处理具体数字
```

本质是 **RAG**：计划 = 检索结果，LLM = 生成器。数据来自计划，表达交给 LLM。

### 需要改动的文件

| 文件 | 改动 |
|------|------|
| `data/skills/ppt-workflow/SKILL.md` | 强化计划格式要求，每页必须有 `content` 字段 |
| `backend/app/services/ppt_session_context.py` | **新增**，~60 行，PPT 会话上下文存储 |
| `backend/app/services/ppt_context_middleware.py` | **新增**，~50 行，save_slide 前注入上下文 |
| `backend/app/tools/ppt_tools.py` | submit_slide_plan 持久化到 context，~10 行 |
| `backend/app/services/agent_service.py` | 注册中间件，~5 行 |

**总改动：~130 行新代码 + skill 提示词调整**

### 问题二（参考文档）的额外处理

上述方案已覆盖问题二的大部分场景：用户上传文档 → LLM 在计划阶段读取并提取数据到 `content` 字段 → 数据持久化不丢失。

但还需解决"LLM 可能跳过 `file_to_md`"的问题。建议在 `ppt_context_middleware.py` 中增加强制检查：

```python
async def before_tool_call(self, ctx, tool_name, args):
    # 如果调用 submit_slide_plan 但尚未调用 file_to_md（有上传文件时），拒绝
    if tool_name == "submit_slide_plan" and has_uploaded_files(session_id):
        if not file_to_md_called(session_id):
            return "错误：有上传文件未读取，请先调用 file_to_md 读取所有文档再提交计划"
```

---

## 优先级

| 优化项 | 优先级 | 原因 |
|--------|--------|------|
| 内容型计划格式 | P0 | 同时解决问题二和问题三 |
| 计划持久化 + 注入 | P0 | 核心机制，没有这个其他都白搭 |
| file_to_md 强制检查 | P0 | 防止 LLM 跳过文档读取 |
| 实时 SVG 预览（方案 A） | P1 | 体验优化，独立于上述方案 |
