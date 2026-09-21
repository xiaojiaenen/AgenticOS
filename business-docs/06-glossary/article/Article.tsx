import { Article, Hero, Lead, Section, Table } from "reacticle";

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
        title="关键概念词汇表"
        subtitle="60+ 业务术语中英对照，覆盖智能体、工具、审批、外部系统等核心领域"
        meta={[{ label: "生成日期", value: "2026-07-22" }]}
      />

      <Lead>
        本文档整理了 AgenticOS 项目的全部关键术语。每个词条包含英文原名、中文翻译和业务解释。
        新人可在阅读其他文档时随时查阅。
      </Lead>

      <Section index="01" title="🔄 平台核心概念">
        <Table
          columns={[{ key: "en", label: "英文" }, { key: "cn", label: "中文" }, { key: "desc", label: "业务解释" }]}
          rows={[
            { en: "Agent", cn: "智能体", desc: "一个 AI 驱动的虚拟助手，有自己的身份设定、能力和行为模式" },
            { en: "Agent Profile", cn: "智能体配置", desc: "定义智能体行为的配置模板，包含系统提示词、工具集、模式等" },
            { en: "Response Mode", cn: "响应模式", desc: "智能体的工作模式，决定其工具集和行为方式（general / ppt / video / email / website）" },
            { en: "Session", cn: "对话会话", desc: "用户与智能体的一次完整对话，包含多轮消息交互" },
            { en: "Tool", cn: "工具", desc: "智能体可以调用的功能单元，如计算、文件操作、搜索等" },
            { en: "Tool Catalog", cn: "工具目录", desc: "系统所有可用工具的注册表，按模式分组" },
            { en: "Skill", cn: "技能包", desc: "上传到平台的本地技能文件集合，可绑定到智能体增强能力" },
            { en: "System Prompt", cn: "系统提示词", desc: "定义智能体行为规则的系统级指令" },
            { en: "SSE", cn: "服务器推送事件", desc: "Server-Sent Events，用于实时推送 AI 响应到前端的流式协议" },
            { en: "Context Compression", cn: "上下文压缩", desc: "对话超过 16 轮后，自动用 LLM 压缩历史记录以节省 token" },
          ]}
        />
      </Section>

      <Section index="02" title="🔐 认证与安全">
        <Table
          columns={[{ key: "en", label: "英文" }, { key: "cn", label: "中文" }, { key: "desc", label: "业务解释" }]}
          rows={[
            { en: "JWT", cn: "JSON Web Token", desc: "用户登录后签发的身份令牌，用于 API 鉴权" },
            { en: "PBKDF2", cn: "密码哈希算法", desc: "用户密码的加密存储算法" },
            { en: "LDAP", cn: "轻量目录访问协议", desc: "企业统一认证协议，启用后平台改用 LDAP 网关验证身份" },
            { en: "HITL", cn: "人在回路", desc: "Human-in-the-Loop，AI 调用高风险工具时需人工确认的机制" },
            { en: "Rate Limit", cn: "频率限制", desc: "5 次失败尝试后封锁 15 分钟，防暴力破解" },
            { en: "Auth Source", cn: "认证来源", desc: "用户的认证方式：local（本地注册）或 ldap（企业认证）" },
            { en: "Admin", cn: "管理员", desc: "平台最高权限角色，可管理用户、智能体、工具配置和系统设置" },
          ]}
        />
      </Section>

      <Section index="03" title="📊 PPT 领域">
        <Table
          columns={[{ key: "en", label: "英文" }, { key: "cn", label: "中文" }, { key: "desc", label: "业务解释" }]}
          rows={[
            { en: "SVG Slide", cn: "SVG 幻灯片", desc: "用 SVG 矢量图形绘制的单页幻灯片，可导出为原生 .pptx" },
            { en: "save_slides_batch", cn: "批量保存幻灯片", desc: "推荐的方式，一次保存 3 页 SVG，减少 40-60% LLM 调用" },
            { en: "Theme Token", cn: "主题变量", desc: "品牌主题定义的颜色、字体等 CSS 变量，SVG 通过 var(--token) 引用" },
            { en: "Preview HTML", cn: "预览 HTML", desc: "系统的 PPT 预览渲染 HTML" },
            { en: "Deck JSON", cn: "幻灯片 JSON", desc: "包含所有幻灯片数据的 JSON，用于渲染和导出" },
            { en: "Chart Template", cn: "图表模板", desc: "71 种预定义的图表样式（柱状图、折线图、饼图等）" },
            { en: "Brand Theme", cn: "品牌主题", desc: "20+ 预置品牌设计主题（Apple、GitHub、Stripe、Notion 等）" },
            { en: "SVG Finalize Pipeline", cn: "SVG 后处理管线", desc: "自动嵌入图片、裁剪、扁平化文本、修复宽高比的管线" },
          ]}
        />
      </Section>

      <Section index="04" title="🎬 视频领域">
        <Table
          columns={[{ key: "en", label: "英文" }, { key: "cn", label: "中文" }, { key: "desc", label: "业务解释" }]}
          rows={[
            { en: "Storyboard", cn: "分镜板", desc: "多场景视频的每个镜头的文字/视觉描述" },
            { en: "Frame", cn: "帧", desc: "Storyboard 中的单个镜头，有自己的 HTML 内容和动画" },
            { en: "Template", cn: "模板", desc: "23 种预定义的视频风格模板（数据可视化、营销、解说等）" },
            { en: "Content Graph", cn: "内容图", desc: "多场景 Storyboard 的编排结构描述" },
            { en: "Chromium Recording", cn: "Chromium 录制", desc: "使用无头浏览器录制 HTML 动画为视频帧" },
            { en: "ffmpeg Encoding", cn: "ffmpeg 编码", desc: "将录制的帧序列编码为最终 MP4 视频" },
          ]}
        />
      </Section>

      <Section index="05" title="📧 邮箱领域">
        <Table
          columns={[{ key: "en", label: "英文" }, { key: "cn", label: "中文" }, { key: "desc", label: "业务解释" }]}
          rows={[
            { en: "IMAP", cn: "邮件接收协议", desc: "用于读取和搜索邮件的互联网协议" },
            { en: "SMTP", cn: "邮件发送协议", desc: "用于发送邮件的互联网协议" },
            { en: "Fernet Encryption", cn: "Fernet 加密", desc: "邮箱密码的对称加密存储方式" },
            { en: "Email Credentials", cn: "邮箱凭据", desc: "用户配置的 IMAP/SMTP 连接参数（加密存储）" },
          ]}
        />
      </Section>

      <Section index="06" title="🌐 网站领域">
        <Table
          columns={[{ key: "en", label: "英文" }, { key: "cn", label: "中文" }, { key: "desc", label: "业务解释" }]}
          rows={[
            { en: "Website Deploy", cn: "网站部署", desc: "将构建好的网站发布到目标域名的操作" },
            { en: "Stack", cn: "技术栈", desc: "网站的底层技术选择：Vanilla / Vue 3 / React 18" },
            { en: "Template Copy", cn: "模板复制", desc: "从预置模板创建新项目的操作" },
            { en: "Deploy Approval", cn: "部署审批", desc: "网站上线前需要管理员审批" },
          ]}
        />
      </Section>

      <Section index="07" title="🔗 外部系统集成">
        <Table
          columns={[{ key: "en", label: "英文" }, { key: "cn", label: "中文" }, { key: "desc", label: "业务解释" }]}
          rows={[
            { en: "External System", cn: "外部系统", desc: "平台可集成的第三方 API 服务（如 JIRA、Dinky）" },
            { en: "External API", cn: "外部 API 定义", desc: "外部系统的一个 API 接口的方法、路径和参数定义" },
            { en: "API Key Auth", cn: "API 密钥认证", desc: "通过固定 API Key 在请求头中认证" },
            { en: "Bearer Auth", cn: "Bearer 令牌认证", desc: "通过动态 Bearer Token 认证" },
            { en: "OAuth2", cn: "OAuth2 授权", desc: "标准的授权码认证流程" },
            { en: "JWT Login", cn: "JWT 登录认证", desc: "通过用户名密码换取 JWT 令牌的认证方式" },
            { en: "Credential Proxy", cn: "凭据代理", desc: "加密存储和代理传递用户的外部系统凭据" },
            { en: "Integration Category", cn: "集成类别", desc: "外部系统的业务分类，如数据平台、项目管理等" },
          ]}
        />
      </Section>

      <Section index="08" title="🛡️ 管理后台">
        <Table
          columns={[{ key: "en", label: "英文" }, { key: "cn", label: "中文" }, { key: "desc", label: "业务解释" }]}
          rows={[
            { en: "Dashboard", cn: "数据看板", desc: "管理员查看平台用量、活跃用户、趋势图的统计面板" },
            { en: "Announcement", cn: "系统公告", desc: "管理员发布的通知，支持定时发布和多样化主题风格" },
            { en: "Agent Store", cn: "智能体商店", desc: "智能体配置的展示和安装市场" },
            { en: "Agent Profile Audience", cn: "智能体可见范围", desc: "控制哪些用户可以看到和使用某个智能体" },
            { en: "System Settings", cn: "系统设置", desc: "键值对格式的系统级配置项" },
            { en: "Usage Event", cn: "用量事件", desc: "每次 AI 对话的 token 消耗、工具调用、延迟等记录" },
          ]}
        />
      </Section>

      <Section index="09" title="🧠 记忆与知识">
        <Table
          columns={[{ key: "en", label: "英文" }, { key: "cn", label: "中文" }, { key: "desc", label: "业务解释" }]}
          rows={[
            { en: "Memory", cn: "记忆", desc: "用户告诉 AI 并希望记住的信息（偏好、事实等）" },
            { en: "Memory Type", cn: "记忆类型", desc: "记忆的分类：fact（事实）、preference（偏好）" },
            { en: "Memory Importance", cn: "记忆重要性", desc: "0-1 的浮点数，决定记忆在检索时的权重" },
            { en: "Memory Source", cn: "记忆来源", desc: "auto（AI 自动提取）/ manual（用户手动）/ tool（工具调用）" },
          ]}
        />
      </Section>

      <Section index="10" title="📋 审批流">
        <Table
          columns={[{ key: "en", label: "英文" }, { key: "cn", label: "中文" }, { key: "desc", label: "业务解释" }]}
          rows={[
            { en: "Approval Request", cn: "审批请求", desc: "Agent 调用需审批工具时创建的待审批记录" },
            { en: "Sub-tool Approval", cn: "子工具审批", desc: "对工具内部的细分操作进行独立审批控制" },
            { en: "Approval Timeout", cn: "审批超时", desc: "300 秒无响应自动视为拒绝" },
            { en: "Pending Approval", cn: "待审批", desc: "审批请求的初始状态，等待用户决策" },
          ]}
        />
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
