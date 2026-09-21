import { Article, Hero, Lead, Section, Table, Aside } from "reacticle";

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
        title="系统架构（业务视角）"
        subtitle="前后端部署拓扑、多 Agent 模式路由、外部系统集成模式"
        meta={[{ label: "生成日期", value: "2026-07-22" }]}
      />

      <Lead>
        本文从业务视角出发，不展开代码细节，而是回答"系统各部分如何协作"——
        前端如何与后端通信、AI 智能体如何工作、外部系统怎么接入、Docker 部署怎么跑。
      </Lead>

      <Section index="01" title="整体架构">
        <p>
          AgenticOS 采用经典的前后端分离架构：
        </p>
        <Table
          columns={[{ key: "layer", label: "层次" }, { key: "tech", label: "技术" }, { key: "port", label: "端口" }, { key: "desc", label: "职责" }]}
          rows={[
            { layer: "前端", tech: "React 19 + Vite", port: ":3001", desc: "聊天界面、管理后台、智能体商店" },
            { layer: "后端 API", tech: "FastAPI + wuwei", port: ":8001", desc: "AI 智能体编排、认证、数据持久化" },
            { layer: "数据库", tech: "SQLite / MySQL", port: "—", desc: "22 张业务表存储所有数据" },
            { layer: "缓存", tech: "Redis（可选）", port: ":6379", desc: "会话缓存、速率限制、历史加载" },
            { layer: "消息队列", tech: "SSE 流", port: "—", desc: "AI 响应实时推送到前端" },
          ]}
        />

        <h3>Docker 部署架构</h3>
        <p>
          Docker Compose 部署 nginx 作为反向代理：nginx 监听 :3001，将静态资源交给前端，
          将 /api 请求代理到后端 :8001。后端通过 SQLite 或 MySQL 存储数据。
          Redis 作为可选的缓存层。
        </p>
      </Section>

      <Section index="02" title="前端架构">
        <p>
          前端使用 React 19 + TypeScript + Vite + Tailwind 4，主要结构：
        </p>
        <ul>
          <li><strong>路由</strong>：React Router，6 个页面（首页 / 聊天 / 智能体商店 / 登录 / 注册 / 管理后台）</li>
          <li><strong>聊天页面</strong>（Chat.tsx）：最核心的页面，包含消息列表、输入框、侧边栏、审批面板、产物展示</li>
          <li><strong>管理后台</strong>（AdminDashboard.tsx）：用户管理、智能体管理、技能管理、工具配置、数据看板</li>
          <li><strong>SSE 客户端</strong>（useChatStream.ts / agentService.ts）：管理 SSE 连接、审批决策提交</li>
          <li><strong>会话缓存</strong>（useChatSessions.ts）：localStorage 缓存最近 24 个会话，保证刷新不丢数据</li>
        </ul>
        <p>构建时 vendor 分拆为 react-core、motion-vendor、markdown-vendor、admin-vendor。</p>
      </Section>

      <Section index="03" title="后端架构">
        <p>后端基于 FastAPI + wuwei 框架，核心架构分层：</p>

        <h3>API 层（17 组路由）</h3>
        <p>
          路由按业务模块划分：auth（认证）、agent（AI 对话、审批）、agent-profiles（智能体配置）、
          skills（技能）、tool-config（工具配置）、dashboard（看板）、email（邮箱）、
          video（视频）、website（网站）、memory（记忆）、announcements（公告）、
          external-systems（外部系统集成）、files（文件）、settings（系统设置）等。
        </p>

        <h3>Service 层</h3>
        <p>
          核心服务 <strong>AgentService</strong> 是枢纽，负责创建 AI Agent、管理 SSE 流、
          协调审批、记录用量。其他服务如 SkillService、AuthService、ApprovalManager 等各司其职。
        </p>

        <h3>Middleware 层</h3>
        <p>
          后端在 wuwei 框架之上叠加了多个自定义中间件：
        </p>
        <Table
          columns={[{ key: "mw", label: "中间件" }, { key: "desc", label: "职责" }]}
          rows={[
            { mw: "LenientHitlMiddleware", desc: "拦截高风险工具调用，触发 HITL 审批" },
            { mw: "ThinkingHistoryCompatibilityMiddleware", desc: "兼容 provider thinking-mode 的合成回复" },
            { mw: "SkillInstructionMiddleware", desc: "将绑定的 Skill 注入到智能体上下文中" },
            { mw: "AsyncSubAgentMiddleware", desc: "支持后台异步子任务（代码分析、文件处理）" },
          ]}
        />
      </Section>

      <Section index="04" title="AI 智能体编排引擎">
        <p>
          平台的智能体引擎基于 <strong>wuwei 框架</strong>，核心工作流程：
        </p>
        <ol>
          <li>用户选择智能体模式（general / ppt / video / email / website）</li>
          <li>Engine 加载对应的 Agent Profile（系统提示词 + 工具列表）</li>
          <li>LLM 处理用户输入，决定回复或调用工具</li>
          <li>工具调用经过中间件链（审批 → 技能注入 → 并发执行 → 结果返回）</li>
          <li>LLM 根据工具结果生成最终回复</li>
        </ol>
        <Aside tone="principle" label="设计哲学">
          每个 Agent 模式是一个独立的"能力包"，由系统提示词 + 工具白名单 + 中间件链共同定义。
          这种设计让平台能轻松扩展新的智能体类型。
        </Aside>

        <h3>多智能体编排</h3>
        <p>
          除了单 Agent 模式，平台还支持 Multi-Agent Graph（Leader-Worker 模式）：
          Leader 分解任务 → Workers（researcher / writer / reviewer）并行执行 → Leader 汇总。
          适用于复杂任务如多页 PPT 生成。
        </p>
      </Section>

      <Section index="05" title="外部系统集成模式">
        <p>
          平台设计了完整的外部系统集成框架，支持管理员注册第三方系统并为用户提供统一调用入口：
        </p>
        <Table
          columns={[{ key: "step", label: "步骤" }, { key: "actor", label: "执行者" }, { key: "action", label: "操作" }]}
          rows={[
            { step: "1", actor: "管理员", action: "注册外部系统（名称、URL、认证配置）" },
            { step: "2", actor: "管理员", action: "定义 API（method、path、参数 Schema）" },
            { step: "3", actor: "管理员", action: "绑定到 Agent 模式" },
            { step: "4", actor: "用户", action: "授权自己的凭据" },
            { step: "5", actor: "AI 智能体", action: "在对话中调用外部 API" },
          ]}
        />

        <h3>支持的认证协议</h3>
        <Table
          columns={[{ key: "auth", label: "认证方式" }, { key: "flow", label: "流程" }]}
          rows={[
            { auth: "API Key", flow: "固定密钥在 HTTP Header 中传递" },
            { auth: "Bearer Token", flow: "动态令牌认证" },
            { auth: "Basic Auth", flow: "用户名 + 密码 Base64 编码" },
            { auth: "OAuth2", flow: "授权码流程 + Token 刷新" },
            { auth: "JWT Login", flow: "用户名密码换取 JWT，支持自动续期" },
            { auth: "Custom", flow: "自定义签名/加密方案" },
          ]}
        />
      </Section>

      <Section index="06" title="SSE 通信协议">
        <p>
          前端与后端的 AI 对话全部通过 Server-Sent Events（SSE）实时通信。
          相比 WebSocket，SSE 更轻量、天然支持 HTTP 和重连。
        </p>
        <p>连接方式：<code>POST /api/v1/agent/stream</code>，请求体包含 session_id、消息内容和智能体选择。</p>
        <p>完整事件时序见"核心业务流程"文档。</p>
        <ul>
          <li><strong>流式输出</strong>：AI token 通过 delta 事件逐字推送</li>
          <li><strong>工具调用</strong>：tool_calls + tool_results 配对出现</li>
          <li><strong>审批交互</strong>：approval_required 触发前端审批面板</li>
          <li><strong>产物通知</strong>：artifact_ready 推送 PPT/视频渲染结果</li>
        </ul>
      </Section>

      <Section index="07" title="数据库架构">
        <p>
          22 张业务表覆盖 9 大实体。默认使用 SQLite 零配置启动，
          生产环境可切换为 MySQL。ORM 用 SQLAlchemy，建表自动执行。
        </p>
        <Table
          columns={[{ key: "group", label: "分组" }, { key: "tables", label: "表名" }, { key: "count", label: "数量" }]}
          rows={[
            { group: "用户与认证", tables: "users, auth_sessions, auth_rate_limits", count: "3" },
            { group: "AI 智能体", tables: "agent_profiles, agent_profile_tools, agent_profile_skills, agent_profile_audiences, user_installed_agents, agent_sessions, agent_messages, agent_usage_events", count: "8" },
            { group: "工具与审批", tables: "agent_tool_configs, agent_approvals", count: "2" },
            { group: "技能", tables: "skills, agent_profile_skills", count: "2" },
            { group: "产物品类", tables: "ppt_artifacts, video_artifacts, website_deploys, memories", count: "4" },
            { group: "邮箱", tables: "user_email_credentials", count: "1" },
            { group: "外部系统", tables: "external_systems, external_apis, external_api_params, external_user_credentials, agent_profile_external_systems", count: "5" },
            { group: "系统管理", tables: "announcements, system_settings", count: "2" },
          ]}
        />
      </Section>

      <Section index="08" title="部署与运维">
        <h3>环境要求</h3>
        <ul>
          <li>Python 3.13+（后端），Node.js 22+（前端）</li>
          <li>包管理：uv（Python）、pnpm（前端）</li>
          <li>可选的 Redis 和 MySQL</li>
        </ul>

        <h3>关键环境变量</h3>
        <Table
          columns={[{ key: "var", label: "变量" }, { key: "desc", label: "说明" }]}
          rows={[
            { var: "OPENAI_API_KEY", desc: "LLM 访问密钥" },
            { var: "AUTH_SECRET_KEY", desc: "JWT 签名密钥" },
            { var: "DATABASE_URL", desc: "数据库连接字符串" },
            { var: "REDIS_URL", desc: "Redis 连接（留空=内存）" },
            { var: "HITL_ENABLED", desc: "是否启用审批流" },
            { var: "LDAP_ENABLED", desc: "是否启用 LDAP 认证" },
          ]}
        />

        <h3>Docker 部署</h3>
        <p>
          一条命令启动：<code>docker compose up -d --build</code>。
          nginx 同时承载前端静态资源和 API 反向代理。生产环境建议配置 HTTPS。
        </p>
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
        </a> · tufte theme
      </footer>
    </Article>
  );
}
