# AgenticOS PPT 智能体优化方案

> 基于 `~/code/ppt-master` (v2.9.0) 和 `~/code/open-design` 的最新更新，对当前项目 PPT 系统的优化方案。
> 文档日期：2026-05-14

---

## 一、当前系统审查总结

### 1.1 现有架构

```
用户请求 (response_mode="ppt")
    │
    ▼
stream_chat() ── resolve profile ── ppt_mode = True
    │
    ├─ _inject_design_catalog()     ← 注入主题列表 + token 速查 + 技能加载指令
    ├─ _get_edit_hint()             ← 注入已有 PPT 的修改提示（如有）
    │
    ├─ 系统提示词 = PPT_SYSTEM_PROMPT (230 行)
    │   ├─ save_slide / read_slide 工具用法
    │   ├─ SVG 技术约束（viewBox、var(--token)、禁止元素）
    │   ├─ 分组规范（<g id="...">）
    │   ├─ 技能加载指令 → load_skill("ppt-design-guide") → load_skill("ppt-template-library")
    │   ├─ 创作 6 步流程
    │   ├─ 修改流程（read_slide → save_slide）
    │   ├─ 文件处理流程（file_to_md / convert_pptx_to_svg）
    │   ├─ 设计质量铁律（5 条）
    │   ├─ 内容质量铁律（7 条）
    │   ├─ 演讲者备注规范
    │   ├─ 叙事结构框架表
    │   └─ 输出步骤
    │
    ├─ 工具注册：save_slide, read_slide, search_icons, calc_chart_positions,
    │   check_svg_quality, convert_pptx_to_svg, load_skill, list_skills, + 通用工具
    │
    ▼
Agent 循环
    ├─ load_skill("ppt-design-guide")   → 361 行设计规范（SVG 约束、排版、颜色、动画、风格）
    ├─ load_skill("ppt-template-library") → 120 行模板索引（15 布局 + 71 图表）
    ├─ read_file("references/charts/bar_chart.svg") → 读取具体模板
    ├─ save_slide(1, svg="...")         → 写入 slide_1.svg
    ├─ save_slide(2, svg="...")         → 写入 slide_2.svg
    ├─ ... (重复 8-14 次)
    └─ done
    │
    ▼
Artifact 创建
    ├─ 读取 slide_*.svg (≥3 页)
    ├─ SVGQualityChecker (仅日志，不阻断)
    ├─ 检测 data-theme → 解析 CSS → resolve var(--token) → hex
    ├─ sanitize_svg_xml() → 构建预览 HTML → 存入 DB
    └─ SSE: artifact_ready
```

### 1.2 当前系统的优点

| 能力 | 状态 | 说明 |
|------|------|------|
| 71 个图表模板 | ✅ 已有 | 从 ppt-master 同步，含选型索引 |
| 15 个核心布局 | ✅ 已有 | cover/toc/section-divider/bullets 等 |
| 36+ 主题 CSS | ✅ 已有 | apple/github/stripe/dracula 等 |
| 8 种套装风格 | ✅ 已有 | editorial/modern_minimal/swiss_international 等 |
| 图标搜索工具 | ✅ 已有 | search_icons 集成 5 个图标库 |
| SVG→PPTX 导出 | ✅ 已有 | 完整 DrawingML 转换流水线 |
| PPTX→SVG 逆向 | ✅ 已有 | 上传 PPTX 自动转 SVG 编辑 |
| 设计规范技能 | ✅ 已有 | 361 行反 AI 规则 + 排版/颜色纪律 |
| 演讲者备注 | ✅ 已有 | `<!-- notes: ... -->` 标准 |

### 1.3 与 ppt-master 的差距

| 维度 | 当前 AgenticOS | ppt-master | 差距 |
|------|---------------|------------|------|
| **防漂移机制** | ❌ 无 | spec_lock.md 每页重读 + 质量检查门禁 | 🔴 严重 |
| **策略师→执行者流水线** | ❌ 无（一次性生成） | 8 项确认 → design_spec + spec_lock → 逐页执行 | 🔴 严重 |
| **质量检查强制性** | 日志级别，不阻断 | 错误必须修复后才能继续 | 🟠 中等 |
| **页面节奏** | 无 | page_rhythm: anchor/dense/breathing | 🟠 中等 |
| **多画布格式** | 仅 1280×720 | 8 种（16:9/4:3/小红书/方形/故事等） | 🟡 轻度 |
| **视觉审查** | 无 | 逐页 rubric 自检（硬规则+软规则） | 🟡 轻度 |
| **图表坐标校准** | calc_chart_positions（未深度集成） | chart-plot-area 注释 + verify-charts 工作流 | 🟡 轻度 |
| **TTS 演讲** | 无 | 5 后端 TTS + 音频注入 PPTX | 🟢 可选 |
| **模板填充** | 无 | 分析→规划→填充现有 PPTX | 🟢 可选 |

---

## 二、优化方案

### 第一期：防漂移 + 质量门禁（核心修复）

#### 2.1 引入 spec_lock.md 机制

**问题**：当前系统没有任何机制约束 AI 在生成 10+ 页 SVG 时的颜色/字体一致性。随着页面增多，AI 会逐渐偏离初始选择的配色和字体，导致 deck 视觉不统一。

**方案**：在创作流程中增加 spec_lock.md 生成 + 每页重读。

**具体改动：**

**A) PPT_SYSTEM_PROMPT 中增加 spec_lock 步骤**（插入到"创作 6 步"的第 3 步和第 4 步之间）

```markdown
### 第 3.5 步：生成 spec_lock（执行锁）

在规划页面序列后、开始生成 SVG 前，**先用 save_slide 工具写一个 spec_lock 块**（或在回复中输出），包含：

| 字段 | 说明 | 示例 |
|------|------|------|
| canvas | viewBox + 格式 | 0 0 1280 720 · PPT 16:9 |
| colors | bg / primary / accent / text / border 等 | bg: var(--bg), accent: var(--accent) |
| typography | 字体族 + 字号层级 | title: 48px 700, body: 16px 400 |
| icons | 图标库 + 关键图标清单 | chunk-filled: target, bolt, shield |
| page_rhythm | 每页节奏标签 | P01:anchor, P02:dense, P03:breathing |

**每生成一页 SVG 前，重新确认 spec_lock 中的值。** 颜色/字体/icon 必须来自 spec_lock，不能凭记忆使用。
```

**B) 修改现有提示词中的"创作 6 步"**

当前：
1. 加载技能
2. 理解需求
3. 选择主题
4. 规划页面序列
5. 逐页构建
6. 自检

改为：
1. 加载技能
2. 理解需求
3. 选择主题
4. **生成 spec_lock**（颜色/字体/图标/节奏 → 锁定）
5. 规划页面序列
6. **逐页构建（每页前重读 spec_lock）**
7. 自检

**C) 在 `_inject_design_catalog()` 中注入当前 session 的 spec_lock**

如果当前会话已有 spec_lock，将其注入到用户消息中，让 AI 每次 save_slide 前都能看到。

---

#### 2.2 质量检查从日志升级为阻断

**问题**：当前 `SVGQualityChecker` 仅输出日志，不阻止 artifact 创建。AI 生成的有缺陷 SVG 会被直接使用。

**方案**：在 `ppt_artifact_service.py` 的 `create_from_slides_dir()` 中，将质量检查的关键错误升级为阻断。

**具体改动文件**：`backend/app/services/ppt_artifact_service.py`

```python
# 当前（非阻断）：
quality = SVGQualityChecker()
for svg_path in sorted(slides_dir.glob("slide_*.svg")):
    quality.check_file(svg_path)

# 改为（关键错误阻断）：
quality = SVGQualityChecker()
errors = []
for svg_path in sorted(slides_dir.glob("slide_*.svg")):
    result = quality.check_file(svg_path)
    if result.has_critical_errors():
        errors.append((svg_path.name, result.critical_errors))

if errors:
    # 阻断：记录错误，返回 None 触发 fallback
    logger.error("SVG quality gate blocked: %s", errors)
    return None
```

**关键错误定义**（从 `svg_quality_checker.py` 中提取）：
- viewBox 不匹配 canvas 格式
- 包含 `<style>` / `<foreignObject>` / `<mask>` / `<animate>` 等禁止元素
- 使用 `rgba()` 而非 `fill-opacity`
- `<svg>` 根下有裸元素（无 `<g>` 分组）

**非关键警告**（仍然仅日志）：
- 字体不在 PPT-safe 列表中
- 颜色未使用 var(--token)（直接 hex）
- 缺少演讲者备注

---

#### 2.3 增加 spec_lock 一致性检查

**问题**：`SVGQualityChecker` 不检查颜色/字体是否与 spec_lock 一致。

**方案**：在 `svg_quality_checker.py` 中增加 `check_spec_lock_consistency()` 方法。

**具体改动文件**：`backend/app/services/ppt/svg_quality_checker.py`

新增检查项：

```python
def check_spec_lock_consistency(self, svg_content: str, spec_lock: dict) -> list[str]:
    """检查 SVG 中的颜色/字体是否与 spec_lock 一致"""
    warnings = []
    
    # 1. 检查是否使用了 spec_lock 外的颜色
    hex_colors = re.findall(r'fill="(#[0-9a-fA-F]{3,8})"', svg_content)
    hex_colors += re.findall(r'stroke="(#[0-9a-fA-F]{3,8})"', svg_content)
    allowed_colors = set(spec_lock.get("colors", {}).values())
    for color in set(hex_colors):
        if color not in allowed_colors and not color.startswith("#0000000"):
            warnings.append(f"颜色 {color} 不在 spec_lock 中")
    
    # 2. 检查是否使用了正确的字体族
    fonts = re.findall(r'font-family="([^"]+)"', svg_content)
    expected_font = spec_lock.get("typography", {}).get("font_family", "")
    for font in fonts:
        if expected_font and expected_font not in font:
            warnings.append(f"字体 {font} 与 spec_lock 不一致")
    
    # 3. 检查字号是否在合理范围内
    font_sizes = [int(s) for s in re.findall(r'font-size="(\d+)"', svg_content)]
    # ... 检查是否在 spec_lock 定义的层级范围内
    
    return warnings
```

---

### 第二期：流程优化（中优先级）

#### 2.4 增加页面节奏（page_rhythm）

**来源**：ppt-master 的 `spec_lock.md` 中 `page_rhythm` 节

**方案**：在 PPT_SYSTEM_PROMPT 的叙事结构框架中增加节奏标签。

**具体改动**（修改 `backend/app/prompts.py` 中的叙事结构表）：

```markdown
## 叙事结构框架

每页有一个节奏标签，控制视觉密度：

| 节奏 | 含义 | 典型页面 |
|------|------|---------|
| `anchor` | 结构性页面，视觉稳定 | cover, toc, section-divider, thanks |
| `dense` | 信息密集，允许卡片网格和图表 | 数据页、方案页、对比页 |
| `breathing` | 低密度冲击页，留白为主 | big-quote, stat-highlight（单数据） |

**节奏规则**：
- 8 页至少 2 个 anchor + 2 个 breathing
- 不允许连续 3 页同节奏
- 数据密集页（dense）后必须接 breathing 或 anchor
- section-divider 固定为 anchor 节奏

| 阶段 | 推荐页数 | 常用 layout | 节奏 |
|------|---------|------------|------|
| 开场 | 1 页 | cover | anchor |
| 目录 | 1 页 | toc | anchor |
| 章节 1 分隔 | 1 页 | section-divider | anchor |
| 背景/问题 | 1-2 页 | bullets, kpi-grid | dense |
| 章节 2 分隔 | 1 页 | section-divider | anchor |
| 方案/产品 | 2-3 页 | two-column, comparison | dense |
| 章节 3 分隔 | 1 页 | section-divider | anchor |
| 证据/数据 | 1-2 页 | chart-bar, kpi-grid | dense |
| 冲击点 | 1 页 | big-quote, stat-highlight | breathing |
| 落地路径 | 1-2 页 | timeline, roadmap | dense |
| 总结/行动 | 1-2 页 | cta, thanks | anchor |
```

---

#### 2.5 多画布格式支持

**来源**：ppt-master 的 `canvas-formats.md`

**方案**：扩展 `svg_quality_checker.py` 的 viewBox 验证 + 在提示词中增加画布选择。

**新增支持的格式**（从 ppt-master 复制）：

| 格式 | viewBox | 用途 |
|------|---------|------|
| `ppt169` | 0 0 1280 720 | 默认，16:9 投影 |
| `ppt43` | 0 0 1024 768 | 4:3 传统投影 |
| `xiaohongshu` | 0 0 1242 1660 | 小红书分享（3:4） |
| `moments` | 0 0 1080 1080 | 朋友圈/Instagram 方形 |
| `story` | 0 0 1080 1920 | 竖屏故事（9:16） |

**具体改动**：

**A) `svg_quality_checker.py`**：修改 viewBox 验证逻辑

```python
SUPPORTED_VIEWBOXES = {
    "ppt169": "0 0 1280 720",
    "ppt43": "0 0 1024 768",
    "xiaohongshu": "0 0 1242 1660",
    "moments": "0 0 1080 1080",
    "story": "0 0 1080 1920",
}

def validate_canvas_format(self, viewBox: str, expected_format: str = "ppt169") -> bool:
    expected = SUPPORTED_VIEWBOXES.get(expected_format, SUPPORTED_VIEWBOXES["ppt169"])
    return viewBox.strip() == expected
```

**B) `PPT_SYSTEM_PROMPT`**：在确认步骤中增加画布选择

```markdown
### 第 2.5 步：确认画布格式

默认 PPT 16:9 (1280×720)。如果用户明确要求其他格式：
- 4:3 传统投影 → viewBox="0 0 1024 768"
- 小红书分享 → viewBox="0 0 1242 1660"
- 朋友圈/Instagram → viewBox="0 0 1080 1080"
- 竖屏故事 → viewBox="0 0 1080 1920"

所有页面必须使用相同 viewBox。
```

---

#### 2.6 排版纪律强化（从 open-design 引入）

**来源**：open-design 的 `pptx-html-fidelity-audit` 中的 5 层字体审计 + footer-rail 机制

**方案**：在 `svg_quality_checker.py` 中增加 3 项新检查。

```python
def check_layout_discipline(self, svg_content: str) -> list[str]:
    """排版纪律检查"""
    warnings = []
    
    # 1. Footer-rail 检查：内容不得侵入底部 64px 区域（页码/水印区）
    FOOTER_RAIL_Y = 720 - 64  # = 656
    texts_in_footer = re.findall(
        r'<text[^>]*y="(\d+)"[^>]*>(?!.*pagenum|.*footer|.*chrome)',
        svg_content
    )
    for y in texts_in_footer:
        if int(y) > FOOTER_RAIL_Y:
            warnings.append(f"文本 y={y} 侵入 footer-rail 区域 (>{FOOTER_RAIL_Y})")
    
    # 2. 字体层级检查：同一页面字号种类不超过 4 种
    font_sizes = set(re.findall(r'font-size="(\d+)"', svg_content))
    if len(font_sizes) > 4:
        warnings.append(f"页面使用了 {len(font_sizes)} 种字号，建议不超过 4 种")
    
    # 3. Accent 密度检查：accent 色使用不超过 2 处
    accent_uses = len(re.findall(r'(?:fill|stroke)="var\(--accent\)"', svg_content))
    if accent_uses > 2:
        warnings.append(f"accent 色使用了 {accent_uses} 处，建议不超过 2 处")
    
    return warnings
```

---

#### 2.7 演讲者备注改进

**当前状态**：提示词要求每页写 `<!-- notes: ... -->`，150-300 字。这个已经做得不错。

**优化**：增加 notes 质量验证（从 ppt-master 的 shared-standards 复制规则）。

**具体改动**：在自检步骤中增加：

```markdown
### 自检补充
- notes 每页都有？（<!-- notes: ... -->）
- notes 长度在 150-300 字？
- notes 用口语而非书面语？
- notes 中加粗了核心关键词？
- 没有把演讲者描述性文字放在 SVG 可见文字中？
```

---

### 第三期：差异化能力（可选）

#### 2.8 视觉自检 Rubric

**来源**：ppt-master 的 `visual-review.md` 工作流

**方案**：在 PPT 生成完成后，增加可选的逐页自检步骤。

```markdown
### 可选：视觉自检

PPT 生成后，可执行逐页自检：

**硬规则**（必须修复）：
- [ ] 内容超出画布边界
- [ ] 文字溢出或重叠
- [ ] 可读性（文字与背景对比度 ≥ 4.5:1）
- [ ] 元素碰撞（卡片/图标/文字互相遮挡）

**软规则**（建议修复）：
- [ ] 垂直节奏均匀（无过大空隙或拥挤）
- [ ] 视觉重心合理（不在角落）
- [ ] 对齐一致性（左对齐/居中混用？）
- [ ] 网格均匀性（卡片间距一致）
```

---

#### 2.9 Presenter Mode（演示模式）

**来源**：open-design 的 Presenter Mode

**方案**：在前端 `PptArtifactPanel.tsx` 增加全屏演示功能。

**具体改动**：

**A) 新增组件**：`frontend/src/components/ppt/PptPresenterMode.tsx`

功能：
- 全屏显示 SVG 幻灯片
- 左右键 / 空格翻页
- 底部浮动计数器（`01 / 08`）
- 侧边面板显示：当前页预览、下一页预览、演讲者备注、计时器
- ESC 退出

**B) 修改 `PptArtifactPanel.tsx`**：增加"演示"按钮

```tsx
<button onClick={() => setPresenterMode(true)} className="...">
  <PlayIcon className="w-4 h-4" />
  演示
</button>
```

---

#### 2.10 图表选型索引增强

**当前状态**：`charts_index.json` 已有 71 条选型规则（"Pick for ... Skip if ..."），但提示词中未充分利用。

**方案**：在 `PPT_SYSTEM_PROMPT` 的创作步骤中增加图表选型指引。

```markdown
### 数据页面图表选型

规划数据页面时，不要凭直觉选图表。按以下步骤：

1. 识别页面的**内容形状**：对比？趋势？占比？排名？流程？层级？
2. 在 `ppt-template-library` 的 `charts_index.json` 中，用 "Pick for ... Skip if ..." 规则匹配
3. 优先选最具体的图表（如 Porter's Five Forces → `hub_inward_arrows`，而非通用 `icon_grid`）
4. 如果没有完全匹配，回退到：数据型 → `basic_table`；概念型 → `big-quote`；结构型 → 自定义布局

**选型示例**：
- 3-8 个类别的数值对比 → `bar_chart`
- 两个镜像数据集（A/B 测试） → `butterfly_chart`
- 逐步加减的数值桥接 → `waterfall_chart`
- 4-6 阶段循环（PDCA/飞轮） → `circular_stages`
- 1 个核心 + 4-8 个辐射能力 → `hub_spoke`
- 2×2 优先级矩阵 → `matrix_2x2`
```

---

## 三、可直接复用的内容（无需手动编写）

### 3.1 已有且完善（无需修改）

以下内容已从 ppt-master 同步到当前项目，无需再做：

| 内容 | 当前位置 | 状态 |
|------|---------|------|
| 71 个图表 SVG 模板 | `data/skills/ppt-template-library/references/charts/` | ✅ 完整 |
| 71 条图表选型索引 | `data/skills/ppt-template-library/references/charts/charts_index.json` | ✅ 完整 |
| 15 个核心布局 SVG | `data/skills/ppt-template-library/references/core-layouts/` | ✅ 完整 |
| 36+ 主题 CSS 文件 | `data/design-themes/*.css` | ✅ 完整 |
| 8 种套装风格预设 | `backend/app/services/ppt/deck_styles.py` | ✅ 完整 |
| 设计规范技能 | `data/skills/ppt-design-guide/SKILL.md` | ✅ 完整（361 行） |
| 模板库技能 | `data/skills/ppt-template-library/SKILL.md` | ✅ 完整（120 行） |
| SVG 后处理流水线 | `backend/app/services/ppt/finalize_svg.py` | ✅ 完整 |
| SVG→PPTX 转换 | `backend/app/services/ppt/svg_to_pptx/` | ✅ 完整 |
| PPTX→SVG 逆向转换 | `backend/app/services/ppt/pptx_to_svg/` | ✅ 完整 |
| 图标搜索工具 | `backend/app/tools/ppt_tools.py` 中的 `search_icons` | ✅ 完整 |
| 图表坐标计算工具 | `backend/app/services/ppt/svg_position_calculator.py` | ✅ 完整 |

### 3.2 可直接从 ppt-master 复制的内容

| 内容 | 来源文件 | 目标位置 | 复制方式 |
|------|---------|---------|---------|
| spec_lock 模板结构 | `ppt-master/skills/ppt-master/templates/spec_lock_reference.md` | 写入 PPT_SYSTEM_PROMPT | 直接复制结构，适配当前 var(--token) 体系 |
| 画布格式定义 | `ppt-master/skills/ppt-master/references/canvas-formats.md` | `svg_quality_checker.py` | 直接复制 viewBox 映射表 |
| 图表选型规则 | 已在 `charts_index.json` 中 | PPT_SYSTEM_PROMPT | 直接引用，无需复制 |
| 反漂移执行纪律 | `ppt-master/skills/ppt-master/SKILL.md` Rule 8 | PPT_SYSTEM_PROMPT | 直接复制规则文案 |
| 视觉审查 rubric | `ppt-master/skills/ppt-master/references/visual-review.md` | PPT_SYSTEM_PROMPT | 提取硬规则/软规则表 |

### 3.3 可直接从 open-design 复制的内容

| 内容 | 来源文件 | 目标位置 | 复制方式 |
|------|---------|---------|---------|
| Footer-rail 不变量 | `open-design/skills/pptx-html-fidelity-audit/references/layout-discipline.md` | `svg_quality_checker.py` | 直接复制规则 |
| 5 层字体审计 | `open-design/skills/pptx-html-fidelity-audit/references/font-discipline.md` | `svg_quality_checker.py` | 提取字体栈规则 |
| Presenter Mode 键盘导航 | `open-design/templates/deck-framework.html` | 新前端组件 | 复制 JS 逻辑 |

---

## 四、实施路线图

### Phase 1：防漂移 + 质量门禁 ✅ 已完成

| 步骤 | 文件 | 改动 | 状态 |
|------|------|------|------|
| 1 | `backend/app/prompts.py` | PPT_SYSTEM_PROMPT 增加 spec_lock 步骤（第 2 步）+ page_rhythm + 图表选型指引 | ✅ |
| 2 | `backend/app/prompts.py` | 创作 6 步 → 7 步（插入 spec_lock 生成 + 每页重读） | ✅ |
| 3 | `backend/app/services/agent_service.py` | `_inject_design_catalog()` 增加 spec_lock 注入逻辑 | ✅ |
| 4 | `backend/app/services/ppt/svg_quality_checker.py` | 新增 `check_spec_lock_consistency()` + `check_layout_discipline()` + `check_canvas_format()` + `SUPPORTED_VIEWBOXES` | ✅ |
| 5 | `backend/app/services/ppt/svg_quality_checker.py` | 多画布格式验证（5 种格式） | ✅ |
| 6 | `backend/app/services/ppt_artifact_service.py` | 质量检查关键错误升级为阻断 + 新增 spec_lock/layout 检查 | ✅ |
| 7 | `backend/examples/test_ppt_optimizations.py` | 8 项测试（含端到端 LLM 生成）全部通过 | ✅ |

### Phase 2：体验提升（2-3 天）

| 步骤 | 文件 | 改动 |
|------|------|------|
| 7 | `backend/app/prompts.py` | 增加页面节奏规则 + 演讲者备注质量验证 |
| 8 | `frontend/src/components/ppt/PptPresenterMode.tsx` | 新增演示模式组件 |
| 9 | `frontend/src/components/ppt/PptArtifactPanel.tsx` | 增加演示按钮 + 调用演示模式 |
| 10 | `backend/app/prompts.py` | 增加视觉自检 rubric（可选步骤） |

### Phase 3：差异化能力（按需）

| 步骤 | 文件 | 改动 |
|------|------|------|
| 11 | 新增 `backend/app/tools/ppt_template_tools.py` | PPTX 模板分析 + 填充工具 |
| 12 | `frontend/src/components/ppt/PptArtifactPanel.tsx` | 增加 @media print PDF 导出 |

---

## 五、核心改动代码参考

### 5.1 PPT_SYSTEM_PROMPT 中插入的 spec_lock 步骤

> 此段直接插入到当前 `prompts.py` 的"第 1 步：创作前必须确认"之后、"创作 6 步"之前

```markdown
---

## spec_lock：执行锁（必须）

开始生成 SVG 前，先输出一个 spec_lock 块，锁定本 deck 的所有设计参数。之后每生成一页 SVG 前，重新确认这些值。

### spec_lock 格式

用表格形式输出（不用 Markdown 代码块）：

**画布**
- viewBox: 0 0 1280 720
- 格式: PPT 16:9

**颜色**（从注入的 Token 速查中选取，用 var(--token) 表示）
- bg: var(--bg)
- primary: var(--text-1)
- accent: var(--accent)
- secondary: var(--text-2)
- border: var(--border)
- surface: var(--surface)

**字体**
- title: "Playfair Display, Noto Serif SC, serif" · 48px · 700
- body: "Inter, Noto Sans SC, sans-serif" · 16px · 400
- mono: "JetBrains Mono, monospace" · 14px · 400

**图标**
- 库: chunk-filled
- 清单: target, bolt, shield, users, chart-bar, lightbulb

**页面节奏**
- P01: anchor (cover)
- P02: anchor (toc)
- P03: anchor (section-divider)
- P04: dense (背景/数据)
- P05: dense (方案)
- P06: anchor (section-divider)
- P07: dense (证据)
- P08: breathing (金句/冲击)
- P09: dense (落地路径)
- P10: anchor (cta/thanks)

### 执行纪律

1. 每页 SVG 生成前，回顾 spec_lock 中的颜色/字体/icon 值
2. 所有 SVG 中的颜色必须使用 var(--token)，值来自 spec_lock
3. 字体族必须与 spec_lock 一致
4. 如果发现某页需要 spec_lock 之外的颜色，说明 spec_lock 不完整——先更新 spec_lock，再继续
5. **绝不凭记忆使用颜色/字体，每次都从 spec_lock 确认**
```

### 5.2 svg_quality_checker.py 新增方法

```python
# 在 SVGQualityChecker 类中新增：

SUPPORTED_VIEWBOXES = {
    "ppt169": "0 0 1280 720",
    "ppt43": "0 0 1024 768",
    "xiaohongshu": "0 0 1242 1660",
    "moments": "0 0 1080 1080",
    "story": "0 0 1080 1920",
}

FOOTER_RAIL_Y = 656  # 720 - 64

def check_spec_lock_consistency(
    self, svg_content: str, spec_lock: dict
) -> list[str]:
    """检查 SVG 是否与 spec_lock 一致"""
    warnings = []

    # 1. 检查是否使用了未声明的硬编码颜色
    hex_in_fill = re.findall(r'(?:fill|stroke)="(#[0-9a-fA-F]{3,8})"', svg_content)
    # 背景色和 chrome 元素排除
    allowed_hardcoded = {"#FFFFFF", "#F8FAFC", "#FAFBFC", "#000000", "#0F172A"}
    for color in set(hex_in_fill):
        if color.upper() not in {c.upper() for c in allowed_hardcoded}:
            warnings.append(f"⚠️ 硬编码颜色 {color} — 应使用 var(--token)")

    # 2. 检查字体一致性
    fonts_used = set(re.findall(r'font-family="([^"]+)"', svg_content))
    expected_sans = spec_lock.get("typography", {}).get("body", "")
    expected_serif = spec_lock.get("typography", {}).get("title", "")

    # 3. 检查字号范围
    sizes = [int(s) for s in re.findall(r'font-size="(\d+)"', svg_content)]
    if sizes:
        if max(sizes) > 80:
            warnings.append(f"⚠️ 最大字号 {max(sizes)}px 过大（建议 ≤72px）")
        if min(sizes) < 10:
            warnings.append(f"⚠️ 最小字号 {min(sizes)}px 过小（建议 ≥12px）")

    return warnings


def check_layout_discipline(self, svg_content: str) -> list[str]:
    """排版纪律检查（从 open-design 引入）"""
    warnings = []

    # 1. Footer-rail：内容不得侵入底部 64px
    text_y_positions = [
        int(m) for m in re.findall(r'<text[^>]*\sy="(\d+)"', svg_content)
    ]
    for y in text_y_positions:
        if y > self.FOOTER_RAIL_Y:
            warnings.append(f"⚠️ 文本 y={y} 侵入 footer-rail 区域 (>{self.FOOTER_RAIL_Y})")
            break  # 只报一次

    # 2. 字号种类 ≤ 4
    unique_sizes = set(re.findall(r'font-size="(\d+)"', svg_content))
    if len(unique_sizes) > 4:
        warnings.append(f"⚠️ 使用了 {len(unique_sizes)} 种字号，建议 ≤4 种")

    # 3. Accent 使用 ≤ 2 处
    accent_count = len(re.findall(r'(?:fill|stroke)="var\(--accent\)"', svg_content))
    if accent_count > 2:
        warnings.append(f"⚠️ accent 色使用了 {accent_count} 处，建议 ≤2")

    # 4. 分组检查：svg 直接子元素应全部是 <g>
    direct_children = re.findall(r'<svg[^>]*>(.*?)</svg>', svg_content, re.DOTALL)
    if direct_children:
        # 简单检查：是否有裸 <rect> 或 <text> 直接在 <svg> 下
        content = direct_children[0].strip()
        # 跳过注释和空白
        non_comment = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL).strip()
        if non_comment and not non_comment.startswith('<g'):
            # 可能有裸元素（需更精确的 XML 解析，此处简化）
            pass

    return warnings
```

### 5.3 ppt_artifact_service.py 质量门禁改动

```python
# 在 create_from_slides_dir() 方法中，将质量检查改为阻断式：

async def create_from_slides_dir(self, session_id: str, slides_dir: Path):
    # ... 读取 SVG 文件 ...

    # 质量检查（关键错误阻断）
    quality = SVGQualityChecker()
    critical_errors = []
    all_warnings = []

    for svg_path in sorted(slides_dir.glob("slide_*.svg")):
        svg_content = svg_path.read_text(encoding="utf-8")
        result = quality.check_file(svg_path)

        # 收集关键错误
        for err in result.errors:
            if any(keyword in err for keyword in [
                "forbidden element", "viewBox mismatch",
                "rgba()", "no <g> grouping"
            ]):
                critical_errors.append(f"{svg_path.name}: {err}")
            else:
                all_warnings.append(f"{svg_path.name}: {err}")

    # 关键错误 → 阻断，返回 None 触发 fallback
    if critical_errors:
        logger.error("SVG quality gate blocked: %s", critical_errors)
        return None

    # 警告 → 记录但继续
    for w in all_warnings:
        logger.warning("SVG quality warning: %s", w)

    # ... 继续原有逻辑 ...
```

---

## 六、风险与注意事项

| 风险 | 缓解措施 |
|------|---------|
| spec_lock 增加上下文长度 | spec_lock 用表格格式，控制在 30 行以内 |
| 质量门禁误阻断 | 仅阻断 PPTX 不兼容的严重问题，排版问题仍为警告 |
| 多画布格式增加复杂度 | 默认仍为 1280×720，其他格式仅在用户明确要求时使用 |
| Presenter Mode 增加前端复杂度 | 作为独立组件，不影响现有渲染逻辑 |
| 提示词过长影响 AI 理解 | spec_lock 和图表选型指引放在技能文件中，通过 load_skill 按需加载 |

---

## 七、总结

本方案的核心思想：**不造轮子，只补齐流程**。

当前项目的模板库（71 图表 + 15 布局）、主题系统（36+）、SVG→PPTX 流水线、技能系统都已经很完善。最大的差距不在模板数量，而在**执行纪律**——ppt-master 的 spec_lock 防漂移机制和质量门禁是保证 10+ 页 deck 视觉一致性的关键。

**实施优先级**：
1. ✅ **spec_lock + 质量门禁**（已完成）→ 立即提升 deck 一致性
2. 🟠 **演示模式**（2 天）→ 提升用户体验
3. 🟡 **视觉自检 + 模板填充**（按需）→ 增强功能深度
