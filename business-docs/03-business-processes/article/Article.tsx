import { Article, Hero, Lead, Section, Table, Aside, Quote } from "reacticle";

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
        title="AgenticOS 核心业务流程"
        subtitle="8 条端到端业务操作链路，含异常分支和状态迁移"
        meta={[{ label: "生成日期", value: "2026-07-22" }]}
      />

      <Lead>
        AgenticOS 的核心是"对话即服务"——用户通过自然语言对话驱动 AI 完成各种任务。
        本文档展示 8 条核心业务流程，每条包含触发条件、主流程、分支/异常处理和完成标志。
      </Lead>

      {/* ─── 流程 1 ─── */}
      <Section index="01" title="流程 1：用户注册与登录">
        <p><strong>触发条件</strong>：用户访问登录/注册页面</p>

        <h3>本地注册流程</h3>
        <ol>
          <li>用户填写邮箱、姓名、密码</li>
          <li>后端验证邮箱唯一性，PBKDF2 加密存储密码</li>
          <li>如果是系统中第一个用户，自动赋予 admin 角色</li>
          <li>生成 JWT Token，返回用户信息</li>
        </ol>

        <h3>本地登录流程</h3>
        <ol>
          <li>用户提交邮箱+密码</li>
          <li>校验密码哈希 → 失败返回 401</li>
          <li>同一 IP/邮箱 5 次失败触发速率限制，封锁 15 分钟</li>
          <li>验证通过 → 创建会话记录（auth_sessions），返回 JWT</li>
        </ol>

        <h3>LDAP 企业登录</h3>
        <p>
          当 LDAP_ENABLED=true 时，系统自动禁用密码登录和注册入口。
          用户通过 LDAP 网关认证，首次登录时可自动创建本地用户记录。
        </p>

        <Aside tone="note" label="异常分支">
          LDAP 模式下仍有 AUTH_SECRET_KEY 用于 JWT 签发；
          LDAP_AUTO_CREATE_USERS=false 时需管理员预先创建用户账号。
        </Aside>
      </Section>

      {/* ─── 流程 2 ─── */}
      <Section index="02" title="流程 2：AI 对话交互（核心流程）">
        <p><strong>触发条件</strong>：用户在聊天页面输入消息并提交</p>

        <h3>主流程</h3>
        <ol>
          <li>前端 POST /api/v1/agent/stream 发起请求（含 session_id、消息、选择的智能体）</li>
          <li>AgentService 解析请求，选择对应的 Agent Profile，拼接系统提示词</li>
          <li>Wuwei Agent 调用 LLM → 流式输出 token（通过 SSE 实时推送）</li>
          <li>如果 LLM 决定调用工具：
            <ul>
              <li>检查该工具是否需要审批 → 需要则触发 HITL 审批流程</li>
              <li>审批通过后执行工具，结果返回给 LLM</li>
              <li>LLM 继续生成回复</li>
            </ul>
          </li>
          <li>完整回复推送给前端，消息存入 agent_messages</li>
          <li>用量记录写入 agent_usage_events</li>
        </ol>

        <h3>SSE 事件流时序</h3>
        <p>客户端收到的事件按以下顺序：</p>
        <Table
          columns={[{ key: "seq", label: "顺序" }, { key: "event", label: "事件" }, { key: "meaning", label: "含义" }]}
          rows={[
            { seq: "1", event: "session", meaning: "连接成功，返回 session_id" },
            { seq: "2", event: "run_status", meaning: "状态切换（thinking / streaming / done）" },
            { seq: "3", event: "reasoning_delta", meaning: "推理过程 token（如开启 thinking 模式）" },
            { seq: "4", event: "delta", meaning: "AI 回复文本流式输出" },
            { seq: "5", event: "tool_calls", meaning: "AI 决定调用工具" },
            { seq: "6", event: "approval_required", meaning: "工具需要用户审批" },
            { seq: "7", event: "tool_results", meaning: "工具执行完成" },
            { seq: "8", event: "artifact_ready", meaning: "PPT/视频等产物就绪" },
            { seq: "9", event: "done / error", meaning: "流程结束 / 异常终止" },
          ]}
        />

        <Aside tone="note" label="异常分支">
          Agent max_steps（默认 10）耗尽时终止；LLM 超时（300s）时触发 error 事件；
          工具调用失败时告知 LLM 重试或给出替代方案。
        </Aside>
      </Section>

      {/* ─── 流程 3 ─── */}
      <Section index="03" title="流程 3：PPT 智能生成">
        <p><strong>触发条件</strong>：用户在 PPT 模式中描述演示需求</p>
        <ol>
          <li>AI 解析用户需求，确定主题（从 20+ 品牌主题中选择）</li>
          <li>规划幻灯片结构，推荐 8-14 页</li>
          <li>每 3 页调用一次 save_slides_batch 写入 SVG（减少 40-60% LLM 调用）</li>
          <li>SVG 经过后处理管线：
            <ul>
              <li>嵌入图片/图标（search_images 搜索在线图片）</li>
              <li>裁剪、修复宽高比</li>
              <li>扁平化 tspan 文本</li>
              <li>SVG Rect 转 Path</li>
            </ul>
          </li>
          <li>系统触发 artifact_ready SSE 事件，返回 deck_json + preview_html</li>
          <li>用户预览 → 可继续编辑 → 导出原生 .pptx</li>
        </ol>
        <Aside tone="principle" label="核心约束">
          禁止使用 style/foreignObject/mask/animate/rgba——不兼容 PPTX 导出。
          颜色必须通过 var(--token) 引用主题变量，禁止硬编码。
        </Aside>
      </Section>

      {/* ─── 流程 4 ─── */}
      <Section index="04" title="流程 4：视频创作">
        <p><strong>触发条件</strong>：用户在视频模式中描述视频创意</p>
        <ol>
          <li>video_create_project 创建项目</li>
          <li>video_set_template 选择模板（23 种），注入设计指南</li>
          <li>video_write_content_graph 编写 Storyboard（多场景编排）</li>
          <li>逐帧调用 video_write_frame_html 编写 HTML</li>
          <li>video_write_preview_html 生成预览</li>
          <li>video_export_mp4 → Chromium 无头浏览器录制 → ffmpeg 编码 → MP4 输出</li>
        </ol>
        <p><strong>模板类别</strong>：数据可视化、社交短视频、产品展示、营销宣传、演示文稿、解说视频、片头片尾、氛围背景</p>
      </Section>

      {/* ─── 流程 5 ─── */}
      <Section index="05" title="流程 5：网站工程">
        <p><strong>触发条件</strong>：用户在网站模式中描述页面需求</p>
        <ol>
          <li>用户选择技术栈（Vanilla / Vue 3 / React 18）</li>
          <li>copy_template 复制项目模板到本地工作区</li>
          <li>多轮对话中通过 write_text_file / replace_text_in_file 构建页面</li>
          <li>npm install + build_website 构建</li>
          <li>deploy_website 触发审批 → 管理员批准 → 部署到目标域名</li>
        </ol>
        <Aside tone="note" label="审批节点">
          网站部署需要管理员批准后才能生效，防止未授权的代码发布。
        </Aside>
      </Section>

      {/* ─── 流程 6 ─── */}
      <Section index="06" title="流程 6：邮箱管理">
        <p><strong>触发条件</strong>：用户在邮箱模式中请求邮件操作</p>
        <ol>
          <li>setup_email 配置 IMAP/SMTP 凭据（加密存储）</li>
          <li>连接邮箱服务器（支持 Gmail、Outlook、QQ、163、企业邮箱）</li>
          <li>操作矩阵：
            <ul>
              <li>count_emails → 收件箱概览（总数、未读、重要）</li>
              <li>read_emails → 分页查看邮件列表</li>
              <li>search_emails → 按发件人/主题/日期/关键词搜索</li>
              <li>get_email → 读取单封邮件详情</li>
              <li>send_email → 撰写并发送（需用户确认）</li>
            </ul>
          </li>
        </ol>
      </Section>

      {/* ─── 流程 7 ─── */}
      <Section index="07" title="流程 7：HITL 审批流（Human-in-the-Loop）">
        <p><strong>触发条件</strong>：Agent 调用了一个需要审批的工具</p>
        <ol>
          <li>LenientHitlMiddleware 拦截工具调用请求</li>
          <li>ApprovalManager.request_approval() 创建 agent_approvals 记录（status=pending）</li>
          <li>通过 SSE 推送 approval_required 事件到前端</li>
          <li>前端弹出 PendingApprovalPanel，显示：
            <ul>
              <li>工具名称（如 file_to_md、run_skill_python_script）</li>
              <li>调用参数和上下文</li>
              <li>子工具级别的审批信息</li>
            </ul>
          </li>
          <li>用户操作：
            <ul>
              <li>✅ 批准 → Future 解析，Agent 继续执行工具</li>
              <li>❌ 拒绝 → 携带原因，Agent 收到拒绝后终止或调整</li>
              <li>⏱️ 超时（300 秒）→ 自动视为拒绝</li>
            </ul>
          </li>
        </ol>
        <Quote who="设计意图">
          HITL 机制让企业在"AI 自主性"和"人工控制"之间取得平衡。
          高风险操作（如执行脚本、文件导出）必须有人确认。
        </Quote>
      </Section>

      {/* ─── 流程 8 ─── */}
      <Section index="08" title="流程 8：外部系统集成调用">
        <p><strong>触发条件</strong>：管理员注册外部系统，用户在对话中调用外部 API</p>
        <ol>
          <li>管理员注册外部系统（名称、URL、认证方式、OAuth/JWT 配置）</li>
          <li>管理员为系统定义 API（method、path、参数 schema）</li>
          <li>管理员将外部系统绑定到 Agent 模式</li>
          <li>用户授权自己的凭据（API Key / OAuth / JWT 登录）</li>
          <li>用户在对话中通过 tool 调用外部系统 API → 系统自动注入凭据 → 执行请求</li>
        </ol>
        <p><strong>支持 6 种认证协议</strong>：API Key、Bearer Token、Basic Auth、OAuth2 授权码流程、JWT Login、自定义签名</p>
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
