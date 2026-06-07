# AgenticOS 前端重构方案：安静的助手

> 面向普通用户，不是开发者。
> 保留亮色基调，做减法，去噪音。

---

## 设计哲学

一个办公室里的普通用户，白天打开 AgenticOS 让 AI 帮她写邮件、做 PPT。
界面应该是温暖、友好、不吓人的。
像一个安静地坐在旁边帮忙的同事，不像一个全程大喊的推销员。

---

## 问题诊断

| 问题 | 严重度 | 具体表现 |
|------|--------|---------|
| 三重边框堆叠 | 🔴 | border + ring + shadow 同时用在卡片上 |
| 字体粗细失控 | 🔴 | 80% 文字 font-bold/font-black |
| 每页独立背景 | 🟡 | Chat/Admin/Home/Login 各自定义渐变+光斑 |
| 装饰元素过多 | 🟡 | 动画光斑、噪点纹理、3% 透明 mascot |
| 玻璃态滥用 | 🟡 | 每个表面都用 backdrop-blur |
| 按钮风格冲突 | 🟡 | 近黑渐变按钮放在浅色 UI 上 |
| 圆角过大 | 🟡 | rounded-2xl/3xl/[2rem] 统治一切 |

---

## 已完成的改动

### 1. CSS Token 系统（index.css）

**改了什么：**
- 品牌色从高饱和 sky 降到柔和 #2b87c2
- 表面层次简化为 4 级（#f8fafc → #ffffff）
- 边框统一为 rgba(15,23,42, 0.06/0.10/0.15)
- 阴影全部降低（最大 shadow-xl 从 56px 降到 40px）
- 删除 blob 动画、噪点纹理
- glass 工具类只用于 sidebar/modal
- Admin 不再有独立的背景系统

**删除了什么：**
- body 背景的 5 层径向渐变
- body::after 噪点纹理
- .admin-dashboard-backdrop 的 ::before 网格线和 ::after 渐变
- .admin-page-header 的 ::before 渐变线和 ::after 光斑
- .admin-data-panel 的 ::before 和 ::after 装饰
- .admin-modal-shell 的 ::before 和 ::after 多层渐变
- .admin-modal-panel 的 ::before 装饰渐变
- mascot 背景装饰
- blob 动画 keyframe

### 2. Button 组件

**之前：**
- primary: 近黑渐变 (#1f2937 → #020617) + shadow + hover 抬升
- 所有按钮 font-black
- rounded-2xl (16px)

**现在：**
- primary: 纯色 brand-500 + hover brand-600
- font-medium / font-semibold
- rounded-md (8px)

### 3. Card 组件

**之前：**
- border-white/65 + glass-medium + shadow-lg + ring-1 ring-white/35（四层）
- rounded-3xl (24px)
- CardTitle font-bold

**现在：**
- border-slate-200 + bg-white + shadow-xs（两层）
- rounded-lg (12px)
- CardTitle font-semibold

### 4. Input 组件

**之前：**
- rounded-2xl + border-white/75 + bg-white/72 + inset shadow + ring-4
- label: font-bold uppercase tracking-[0.12em]

**现在：**
- rounded-md + border-slate-200 + bg-white
- focus: border-brand-400 + 3px glow shadow（不用 ring）
- label: font-medium（不大写）

---

## 设计原则

1. **每个元素只用一种边框处理** — border 或 shadow，不同时用
2. **字体粗细有梯度** — 600/500/400，不用 700/800/900
3. **所有页面共用同一套背景** — 不自定义渐变
4. **backdrop-blur 只用于 sidebar 和 modal** — 不是每个表面
5. **动画只用于状态反馈** — 不用于装饰

---

## 还需要改的（Phase 2）

### 页面级清理
- 删除 Chat.tsx 的内联背景渐变
- 删除 Home.tsx 的背景渐变和动画光斑
- 删除 Login.tsx / Signup.tsx 的渐变背景
- 删除 AgentStore.tsx 的渐变背景
- 统一为 body 的 surface-0 背景

### 组件级清理
- ChatMessage.tsx — 气泡样式简化
- Sidebar.tsx — 去掉多余 glass 效果
- ChatInput.tsx — 输入区样式简化
- Toast.tsx — 暗色适配删除
- Modal.tsx — 遮罩层简化

### 字体粗细全局替换
- 搜索所有 font-bold → 评估是否需要改为 font-medium
- 搜索所有 font-black → 全部改为 font-semibold
- 搜索 uppercase tracking-[0.15em] → 改为 tracking-[0.08em]

---

## 效果预期

| 指标 | 之前 | 之后 |
|------|------|------|
| 视觉噪音 | 高（多层边框+阴影+装饰） | 低（单层边框+轻阴影） |
| 一致性 | 每页不同风格 | 统一 Token 系统 |
| GPU 负担 | 高（blur×N + 动画 + 噪点） | 低（仅 sidebar/modal blur） |
| 字体层级 | 扁平（全 bold） | 清晰（梯度 400/500/600） |
| 友好度 | 略显冰冷（高对比硬边框） | 温暖（柔和色彩+轻边框） |
