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
        title="AgenticOS 领域模型"
        subtitle="9 大核心实体、22 张数据库表、3 个子域边界"
        meta={[{ label: "生成日期", value: "2026-07-22" }]}
      />

      <Lead>
        本文档从数据库 Schema 和代码模型中提取 AgenticOS 的全部核心业务实体，
        梳理每个实体的属性、生命周期、状态迁移和实体间关系，帮助读者快速建立
        对平台业务结构的完整认知。
      </Lead>

      {/* ─── 1. 用户 ─── */}
      <Section index="01" title="🔐 用户（User）">
        <p>
          用户是平台的核心主体，分为<strong>普通用户</strong>和<strong>管理员</strong>两种角色。
          支持本地注册和 LDAP 企业认证两种登录方式。
        </p>
        <p>一张表，7 个核心字段：</p>
        <Table
          columns={[{ key: "f", label: "字段" }, { key: "t", label: "类型" }, { key: "d", label: "说明" }]}
          rows={[
            { f: "id", t: "Integer", d: "主键，自增" },
            { f: "email", t: "String(255)", d: "邮箱，唯一标识，登录凭证" },
            { f: "name", t: "String(120)", d: "显示名称" },
            { f: "password_hash", t: "String(255)", d: "密码哈希（PBKDF2）" },
            { f: "role", t: "String(32)", d: "user / admin" },
            { f: "is_active", t: "Boolean", d: "是否启用" },
            { f: "auth_source", t: "String(32)", d: "local / ldap" },
          ]}
        />
        <p><strong>状态机</strong>：注册时 is_active=true（LDAP 自动创建）→ 管理员手动禁用 → is_active=false</p>
      </Section>

      {/* ─── 2. 智能体配置 ─── */}
      <Section index="02" title="🧠 智能体配置（Agent Profile）">
        <p>
          智能体是平台提供 AI 能力的单位。每个智能体有自己的身份设定、能力范围和行为模式。
          支持 5 种工作模式。
        </p>
        <Table
          columns={[{ key: "f", label: "模式" }, { key: "d", label: "用途" }, { key: "t", label: "典型工具" }]}
          rows={[
            { f: "general", d: "日常问答、资料整理", t: "计算、时间、文件、记忆" },
            { f: "ppt", d: "演示文稿设计", t: "save_slide、search_images、batch_edit" },
            { f: "video", d: "视频创作", t: "video_create_project、set_template、export_mp4" },
            { f: "email", d: "邮箱管理", t: "read_emails、search_emails、send_email" },
            { f: "website", d: "网站开发", t: "copy_template、build_website、deploy_website" },
          ]}
        />
        <p><strong>关键属性</strong>：name（名称）、slug（唯一标识）、system_prompt（系统提示词）、
        enabled（启用）、listed（商店展示）、is_builtin（系统内置）</p>
        <p><strong>关联资产</strong>：工具绑定（agent_profile_tools）、技能绑定（agent_profile_skills）、
        可见范围（agent_profile_audiences）、外部系统绑定（agent_profile_external_systems）</p>
      </Section>

      {/* ─── 3. 对话会话 ─── */}
      <Section index="03" title="💬 对话会话（Agent Session）">
        <p>用户与 AI 智能体的每一次交互会话。包含系统提示词、最大步数、对话摘要和用量统计。</p>
        <Table
          columns={[{ key: "f", label: "字段" }, { key: "d", label: "说明" }]}
          rows={[
            { f: "session_id", d: "主键（128 位字符串）" },
            { f: "user_id", d: "所属用户" },
            { f: "agent_profile_id", d: "使用的智能体" },
            { f: "system_prompt", d: "智能体系统提示词" },
            { f: "max_steps", d: "最大工具调用步数（默认 10）" },
            { f: "summary", d: "对话摘要" },
            { f: "metadata_json", d: "扩展元数据" },
          ]}
        />
        <p><strong>关联表</strong>：agent_messages（消息列表）、agent_usage_events（用量记录）</p>
      </Section>

      {/* ─── 4. Skill 技能包 ─── */}
      <Section index="04" title="📦 Skill 技能包">
        <p>
          上传到平台的本地技能文件集合，可以绑定到智能体上增强其能力。
          Skill 由文件目录和描述信息组成。
        </p>
        <p>
          核心字段：name（名称）、slug（唯一标识）、root_dir（文件路径）、enabled（启用状态）。
          通过 agent_profile_skills 中间表关联到智能体。
        </p>
      </Section>

      {/* ─── 5. 工具配置 ─── */}
      <Section index="05" title="🔧 工具配置（Tool Config）">
        <p>
          工具是智能体可以调用的功能单元。系统按模式（mode）对工具进行分组管理，
          支持细粒度的子工具审批。
        </p>
        <Table
          columns={[{ key: "f", label: "字段" }, { key: "d", label: "说明" }]}
          rows={[
            { f: "mode", d: "所属模式（general/ppt/video/email/website）" },
            { f: "tool_name", d: "工具名称" },
            { f: "enabled", d: "启用状态" },
            { f: "requires_approval", d: "是否需要管理员审批" },
            { f: "approval_sub_tools_json", d: "子工具级别的审批配置" },
          ]}
        />
        <Aside tone="principle" label="关键机制">
          支持子工具粒度的审批控制。例如文件读取操作需要审批但文件写入不需要，
          可在同一个工具（file）下分别配置。
        </Aside>
      </Section>

      {/* ─── 6. PPT 产物 ─── */}
      <Section index="06" title="📊 PPT 产物（PPT Artifact）">
        <p>AI 生成的演示文稿产物，包含完整的幻灯片数据和预览 HTML。</p>
        <p>
          核心字段：title（标题）、slide_count（页数）、deck_json（完整的 SVG 幻灯片 JSON）、
          preview_html（渲染预览 HTML）。关联到 agent_sessions。
        </p>
      </Section>

      {/* ─── 7. 视频产物 ─── */}
      <Section index="07" title="🎬 视频产物（Video Artifact）">
        <p>AI 生成的视频产物，记录从创作到导出的完整信息。</p>
        <Table
          columns={[{ key: "f", label: "字段" }, { key: "d", label: "说明" }]}
          rows={[
            { f: "project_id", d: "视频项目 ID" },
            { f: "title", d: "视频标题" },
            { f: "template_id", d: "使用的模板" },
            { f: "duration_sec", d: "时长（秒）" },
            { f: "resolution", d: "分辨率（默认 1920x1080）" },
            { f: "fps", d: "帧率（默认 30）" },
            { f: "video_path", d: "MP4 文件路径" },
          ]}
        />
      </Section>

      {/* ─── 8. 外部系统 ─── */}
      <Section index="08" title="🌐 外部系统（External System）">
        <p>
          平台可集成的第三方系统（如 JIRA、Dinky 等），支持 6 种认证协议。
          管理员注册系统并定义 API，用户授权凭据后可在对话中调用。
        </p>
        <Table
          columns={[{ key: "auth", label: "认证方式" }, { key: "desc", label: "说明" }]}
          rows={[
            { auth: "api_key", d: "API Key 在 Header 中传递" },
            { auth: "bearer", d: "Bearer Token 认证" },
            { auth: "basic", d: "Basic Auth（用户名+密码）" },
            { auth: "oauth2", d: "OAuth2 授权码流程" },
            { auth: "jwt", d: "JWT Login（用户名密码换取令牌）" },
            { auth: "custom", d: "自定义签名/加密方案" },
          ]}
        />
        <p><strong>关联表链</strong>：external_systems → external_apis → external_api_params（API 定义与参数）
        → external_user_credentials（用户凭据）</p>
      </Section>

      {/* ─── 9. 公告 ─── */}
      <Section index="09" title="📢 公告（Announcement）">
        <p>系统管理员发布的通知公告，支持定时发布、主题风格和多种展示策略。</p>
        <p>
          核心字段：title（标题）、body（正文）、theme（主题风格）、is_published（发布状态）、
          starts_at / ends_at（发布窗口）、dismissible（可关闭）、show_once（仅展示一次）。
        </p>
      </Section>

      {/* ─── 实体关系总览 ─── */}
      <Section index="10" title="实体关系总览">
        <p>22 张数据库表之间的核心关联关系：</p>
        <Table
          columns={[{ key: "from", label: "源表" }, { key: "rel", label: "关系" }, { key: "to", label: "目标表" }, { key: "note", label: "说明" }]}
          rows={[
            { from: "users", rel: "1:N", to: "auth_sessions", note: "一个用户可有多台设备登录" },
            { from: "users", rel: "1:N", to: "agent_sessions", note: "一个用户可发起多次对话" },
            { from: "users", rel: "1:N", to: "memories", note: "一个用户有多条记忆" },
            { from: "users", rel: "N:M", to: "agent_profiles", note: "通过 user_installed_agents 关联" },
            { from: "agent_profiles", rel: "1:N", to: "agent_sessions", note: "一个智能体配置可被多个会话使用" },
            { from: "agent_profiles", rel: "N:M", to: "skills", note: "通过 agent_profile_skills 关联" },
            { from: "agent_profiles", rel: "N:M", to: "external_systems", note: "通过 agent_profile_external_systems 关联" },
            { from: "agent_sessions", rel: "1:N", to: "agent_messages", note: "一个会话有多条消息" },
            { from: "agent_sessions", rel: "1:N", to: "agent_approvals", note: "一个会话有多个审批" },
            { from: "agent_sessions", rel: "1:N", to: "ppt_artifacts", note: "PPT 产物归属会话" },
            { from: "external_systems", rel: "1:N", to: "external_apis", note: "一个系统有多个 API 定义" },
            { from: "external_apis", rel: "1:N", to: "external_api_params", note: "一个 API 有多个参数" },
          ]}
        />
      </Section>

      {/* ─── 子域划分 ─── */}
      <Section index="11" title="子域划分">
        <p>业务被划分为 3 个 bounded context：</p>

        <h3>🎯 AI 智能体编排（核心子域）</h3>
        <p>
          平台最核心的差异化竞争力。包含多模式 Agent 引擎（基于 wuwei 框架）、
          工具注册与调用、审批中间件（HITL）、上下文压缩、多智能体编排和 Skill 注入。
        </p>

        <h3>🛠️ 内容生产服务（支撑子域）</h3>
        <p>
          PPT 模板引擎、视频渲染管线、网站构建器、邮箱连接器和外部系统集成。
          每种生产模式共享底层 AI 编排框架，但各自有独立的渲染引擎和模板系统。
        </p>

        <h3>🔧 平台管理（支撑子域）</h3>
        <p>
          用户与认证管理、智能体商店（Agent Store）、数据看板与用量统计、
          公告系统、系统设置。
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
