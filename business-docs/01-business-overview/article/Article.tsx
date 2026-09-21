import { Article, Hero, Lead, Section, Quote, Table, Aside } from "reacticle";

export function ArticleDoc() {
  return (
    <Article toc width="regular">

      <nav style={{
        marginBottom: "var(--ra-space-4, 1rem)",
        fontSize: "var(--ra-text-sm, 0.875rem)",
      }}>
        <a href="../index.html"
          style={{ color: "var(--ra-color-muted, inherit)", textDecoration: "none",
            display: "inline-flex", alignItems: "center", gap: "0.3em" }}>
          ← 返回文档导航
        </a>
      </nav>

      <Hero
        title="AgenticOS 业务全景图"
        subtitle="一个自托管的多模态 AI 智能体平台，能对话、能做 PPT、能拍视频、能管邮件、能搭网站"
        meta={[
          { label: "项目", value: "AgenticOS" },
          { label: "生成日期", value: "2026-07-22" },
        ]}
      />

      <Lead>
        AgenticOS 是一个<strong>可自托管的通用 AI 智能体平台</strong>。它让用户通过自然语言对话就能完成
        PPT 设计、视频创作、邮件管理、网站开发等任务，同时为管理员提供了完善的后台管理、
        权限控制和审批流。无论是个人使用还是企业私有化部署，只需一个 Docker 命令即可启动。
      </Lead>

      <Section index="01" title="一句话认识 AgenticOS">
        <Quote who="项目定位">
          一个开箱即用、可自托管的多模态 AI 智能体平台，让用户通过对话就能生成 PPT、视频、网站和邮件回复。
        </Quote>
        <p>
          传统上，要用 AI 完成不同任务需要在多个工具之间来回切换——ChatGPT 写文案、Gamma 做 PPT、
          Canva 做视频、单独的邮件客户端……AgenticOS 把这些能力整合到一个统一的对话界面中。
        </p>
        <p>
          更重要的是，<strong>它是自托管的</strong>。数据在你的服务器上，模型可以对接自己的 API 网关，
          适合对数据安全有要求的企业场景。
        </p>
      </Section>

      <Section index="02" title="谁在使用 AgenticOS">
        <p>平台服务四类用户，每类用户的关注点和价值诉求各有不同：</p>
        <Table caption="四类用户画像"
          columns={[
            { key: "type", label: "用户类型", width: "16%" },
            { key: "role", label: "角色画像", width: "28%" },
            { key: "need", label: "核心诉求", width: "24%" },
            { key: "scene", label: "使用场景", width: "32%" },
          ]}
          rows={[
            { type: "👤 最终用户", role: "日常需要 AI 辅助的知识工作者", need: "省时省力，一键生成", scene: "用对话做 PPT、剪视频、回邮件" },
            { type: "🛡️ 管理员", role: "管理平台的企业 IT 或运维人员", need: "可控、可管、可审计", scene: "管理智能体权限、审批工具调用、看数据看板" },
            { type: "🔧 智能体开发者", role: "创建和发布自定义智能体的技术用户", need: "灵活配置、快速发布", scene: "编写 Agent Profile、上传 Skills 技能包" },
            { type: "☁️ 自托管运维者", role: "需要私有化部署的技术团队", need: "数据安全、自主可控", scene: "Docker 部署、对接内部 LDAP/OAuth 认证" },
          ]}
        />
      </Section>

      <Section index="03" title="五大核心能力">
        <h3>🗣️ 通用助手（General）</h3>
        <p>
          日常问答、资料整理和轻量工具调用。内置计算、时间、文件操作和记忆工具，适合多轮协作场景。
        </p>

        <h3>📊 PPT 设计师</h3>
        <p>
          使用 SVG 原生图形生成演示文稿，支持 <strong>20+ 品牌主题</strong>（Apple、GitHub、Stripe 等）、
          <strong>71 种图表模板</strong>、<strong>15 种核心布局</strong>。
          生成的 SVG 可导出为原生 .pptx 文件。
        </p>
        <Aside tone="note" label="亮点">
          每批 3 页通过 save_slides_batch 批量写入，减少 40-60% 的 LLM 调用次数。
          内置"反千篇一律"机制，强制主题和布局多样性。
        </Aside>

        <h3>🎬 视频创作</h3>
        <p>
          将想法转化为动画 MP4 视频。<strong>23 种专业模板</strong>涵盖数据可视化、社交短视频、
          产品展示、营销宣传、演示文稿、解说视频等 8 大类别。支持多帧 Storyboard 编排、
          Chromium 录制和 ffmpeg 编码。
        </p>

        <h3>📧 邮箱助手</h3>
        <p>
          通过 IMAP/SMTP 协议集成主流邮箱（Gmail、Outlook、QQ 邮箱、163/126、企业邮箱），
          支持邮件概览、搜索、阅读、统计和回复撰写。发送邮件需要用户确认。
        </p>

        <h3>🌐 网站工程师</h3>
        <p>
          对话式页面开发，支持三种技术栈：<strong>Vanilla</strong>（HTML+CSS+JS）、
          <strong>Vue 3 + Vite</strong>、<strong>React 18 + Vite</strong>。
          内置设计系统，一键构建部署，上线需要管理员审批。
        </p>
      </Section>

      <Section index="04" title="架构速览">
        <Table caption="技术栈概览"
          columns={[
            { key: "layer", label: "层次" },
            { key: "tech", label: "技术" },
            { key: "desc", label: "说明" },
          ]}
          rows={[
            { layer: "前端", tech: "React 19 + TypeScript + Vite", desc: "Tailwind 4 设计系统，SSE 流式接收 AI 响应" },
            { layer: "后端", tech: "FastAPI + wuwei 框架", desc: "AI Agent 编排引擎，支持多模式路由和中间件" },
            { layer: "数据库", tech: "SQLite（默认）/ MySQL", desc: "ORM 自动建表，22 张业务表" },
            { layer: "缓存", tech: "Redis（可选）", desc: "无 Redis 时自动降级到内存" },
            { layer: "部署", tech: "Docker Compose", desc: "nginx 代理前端，后端 :8001，前端 :3001" },
          ]}
        />
      </Section>

      <Section index="05" title="关键数字">
        <Table
          columns={[{ key: "metric", label: "指标" }, { key: "value", label: "数值" }]}
          rows={[
            { metric: "智能体模式", value: "5 种（通用/PPT/视频/邮箱/网站）" },
            { metric: "PPT 主题", value: "20+ 种品牌主题" },
            { metric: "PPT 图表模板", value: "71 种" },
            { metric: "视频模板", value: "23 种（8 大类别）" },
            { metric: "数据库表", value: "22 张" },
            { metric: "API 路由组", value: "17 组" },
          ]}
        />
      </Section>

      <Section index="06" title="部署方式">
        <p>AgenticOS 支持三种运行方式：</p>
        <ul>
          <li><strong>🖥️ 桌面应用</strong>（Tauri）：原生桌面窗口体验</li>
          <li><strong>🌐 Web 服务</strong>：浏览器端开发模式</li>
          <li><strong>🐳 Docker 部署</strong>：一条命令部署前后端</li>
        </ul>
        <p>默认端口：前端 <code>:3001</code>，后端 <code>:8001</code>。Vite 自动代理 <code>/api</code> 到后端。</p>
      </Section>

      <footer style={{
        marginTop: "var(--ra-space-7, 3rem)",
        paddingTop: "var(--ra-space-4, 1rem)",
        borderTop: "1px solid var(--ra-color-border, currentColor)",
        color: "var(--ra-color-muted, inherit)",
        fontSize: "var(--ra-text-xs, 0.78rem)",
        textAlign: "center",
        letterSpacing: "0.02em",
        opacity: 0.85,
      }}>
        Made with{" "}
        <a href="https://github.com/xiaojiaenen/business-analyzer" target="_blank" rel="noopener noreferrer"
          style={{ color: "inherit", textDecoration: "underline", textUnderlineOffset: "0.2em" }}>
          Business Analyzer
        </a> · press theme
      </footer>
    </Article>
  );
}
