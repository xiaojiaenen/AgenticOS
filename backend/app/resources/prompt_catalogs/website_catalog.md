
---
## Website 模式资源速查

### 致命错误警告

**在调用 `copy_template` 之前，项目目录根本不存在！**
直接 `read_text_file` 一个尚不存在的路径必然报错 FileNotFoundError。
正确流程永远是：先 `check_website_project()` → 再 `copy_template(stack)` → 然后才能操作文件。目录名自动生成，格式为 u<用户ID>_s<会话ID>_v<版本号>。

### 可用模板

{template_info}

### 工作流程（必须严格按顺序）

1. 分析需求 → 选择 vanilla/vue/react
2. `check_website_project()` 检查项目是否已存在
3. `copy_template(stack)` 复制模板（目录名自动生成）← 绝对不能跳过！
4. 用文件工具（write_text_file / replace_text_in_file）修改已存在的模板文件
5. 调用 `build_website(slug)` 验证构建
6. 告知用户项目路径和构建结果

### 依赖约束

- 模板 package.json 已包含所有必需依赖，**禁止调用 npm_install_package**
- **禁止 `npm_run_script` 和 `npm_list_scripts`** — 构建验证只用 `build_website(slug)`，不要直接调用 npm 工具
- 如需额外依赖，必须先告知用户获得同意
- 禁止安装 UI 组件库和 CSS 框架

### 设计主题（{theme_count} 套可用，与 PPT 主题库同源）

所有模板 CSS 使用 var(--bg) / var(--accent) / var(--text-1) 等 CSS 变量，禁止写死 hex。

**切换风格用工具，不要手改 :root**：

- `apply_design_theme(theme_name)` —— 把整块经过 WCAG 对比度审计的主题 token
  写进入口样式表（替换 Design Tokens 块）。页面里的 var() 引用自动换肤。
  主题名示例：apple / github / ink-wash / art-deco / ascii-art / mid-century-modern /
  risograph / constructivism / y2k-chrome …
- `list_design_themes()` —— 列出全部主题名。
- 传错主题名不会报错崩溃：返回值里会给最接近的候选。

选型建议（匹配内容气质）：企业官网 → apple / linear-app；艺术人文 → art-nouveau / ink-wash；
复古印刷 → risograph / mid-century-modern；极客/终端 → ascii-art / cyberpunk；
实验性 / 下一代 → liquid-chrome / point-cloud / generative-art。用户明确给了品牌色时不套主题，
把品牌色写进 :root 的同名变量（保持 var() 引用不变）。

### 项目目录结构

```
data/websites/u<用户ID>_s<会话ID>_v<版本号>/
  ├── index.html       # 入口 HTML
  ├── package.json     # 依赖配置（不要修改）
  ├── vite.config.js   # 构建配置（不要修改）
  ├── src/             # 源码目录（vue/react）
  ├── css/             # 样式目录（vanilla）
  ├── js/              # 脚本目录（vanilla）
  └── dist/            # 构建产物（build_website 后生成）
```

### 文件路径规则（极其重要）

文件工具已自动绑定到当前项目目录，**只需提供相对路径**：

```
✅ 正确：write_text_file(path="index.html", ...)
✅ 正确：write_text_file(path="src/main.js", ...)
✅ 正确：replace_text_in_file(path="css/style.css", ...)
❌ 错误：write_text_file(path="data/websites/u1_xxx_v1/index.html", ...)
❌ 错误：write_text_file(path="D:/code/AgenticOS/data/websites/...", ...)
```

**绝对不要在文件路径中包含 `data/websites/` 前缀或完整目录名！**

---
