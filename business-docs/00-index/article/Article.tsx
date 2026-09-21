import { Article, Hero, Lead, Raw } from "reacticle";

export function ArticleDoc() {
  return (
    <Article toc={false} width="regular">

      {/* ─── Colophon-style nav bar ─── */}
      <Raw title="">
        <nav style={{
          marginBottom: "var(--ra-space-4, 1rem)",
          fontSize: "var(--ra-text-sm, 0.875rem)",
          textAlign: "center",
          color: "var(--ra-color-muted, inherit)",
          letterSpacing: "0.02em",
        }}>
          <a
            href="../index.html"
            style={{
              color: "var(--ra-color-muted, inherit)",
              textDecoration: "none",
              display: "inline-flex",
              alignItems: "center",
              gap: "0.3em",
            }}
          >
            ← 返回文档导航
          </a>
        </nav>
      </Raw>

      <Hero
        title="AgenticOS · 业务知识库"
        subtitle="面向零基础读者的全业务领域文档 —— 从智能体对话到 PPT 设计，从视频创作到外部系统集成"
        meta={[
          { label: "项目", value: "AgenticOS" },
          { label: "版本", value: "0.1.0" },
          { label: "生成日期", value: "2026-07-22" },
        ]}
      />
      <Lead>
        AgenticOS 是一个开箱即用、可自托管的多模态 AI 智能体平台。用户通过对话就能完成
        PPT 设计、视频创作、邮件管理、网站开发等任务，管理员可在后台统一管理智能体、
        工具权限和审批流。本文档从业务视角出发，帮助新人快速理解"这个项目是做什么的"。
      </Lead>

      {/* ─── 推荐阅读顺序 ─── */}
      <Raw title="📖 推荐阅读顺序">
        <div style={{
          background: "var(--ra-color-surface, #f8f7f4)",
          borderRadius: "var(--ra-radius-md, 8px)",
          padding: "var(--ra-space-5, 1.5rem)",
          margin: "var(--ra-space-5, 1.5rem) 0",
        }}>
          <ol style={{
            margin: 0,
            paddingLeft: "var(--ra-space-5, 1.5rem)",
            lineHeight: 2,
            fontSize: "var(--ra-text-base, 1rem)",
          }}>
            <li><strong>业务全景图</strong> ← 从这里开始，了解项目全貌</li>
            <li><strong>系统架构（业务视角）</strong> ← 理解前后端部署、外部集成方式</li>
            <li><strong>领域模型</strong> ← 掌握 9 大核心实体及其关系</li>
            <li><strong>核心业务流程</strong> ← 8 条端到端流程含异常分支</li>
            <li><strong>关键概念词汇表</strong> ← 随时查阅的术语速查手册</li>
          </ol>
        </div>
      </Raw>

      {/* ─── 文档卡片列表 ─── */}
      <Raw title="📄 文档列表">
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: "var(--ra-space-4, 1rem)",
          margin: "var(--ra-space-5, 1.5rem) 0",
        }}>

          {/* 卡片：业务全景图 */}
          <a href="../01-business-overview/article/article.html"
             style={{ textDecoration: "none", color: "inherit" }}>
            <div style={{
              border: "1px solid var(--ra-color-border, #ddd)",
              borderRadius: "var(--ra-radius-lg, 12px)",
              padding: "var(--ra-space-4, 1rem)",
              background: "var(--ra-color-surface, #fff)",
              transition: "box-shadow 0.2s",
              cursor: "pointer",
            }}
            onMouseOver={e => e.currentTarget.style.boxShadow = "var(--ra-shadow-md, 0 4px 12px rgba(0,0,0,0.1))"}
            onMouseOut={e => e.currentTarget.style.boxShadow = "none"}>
              <h3 style={{ margin: "0 0 0.5rem" }}>📄 业务全景图</h3>
              <p style={{ margin: 0, fontSize: "0.9rem", opacity: 0.8 }}>
                项目概览、目标用户画像、5 大核心能力速览、价值主张。
                新人理解项目全貌的第一站。
              </p>
            </div>
          </a>

          {/* 卡片：领域模型 */}
          <a href="../02-domain-model/article/article.html"
             style={{ textDecoration: "none", color: "inherit" }}>
            <div style={{
              border: "1px solid var(--ra-color-border, #ddd)",
              borderRadius: "var(--ra-radius-lg, 12px)",
              padding: "var(--ra-space-4, 1rem)",
              background: "var(--ra-color-surface, #fff)",
              transition: "box-shadow 0.2s",
              cursor: "pointer",
            }}
            onMouseOver={e => e.currentTarget.style.boxShadow = "var(--ra-shadow-md, 0 4px 12px rgba(0,0,0,0.1))"}
            onMouseOut={e => e.currentTarget.style.boxShadow = "none"}>
              <h3 style={{ margin: "0 0 0.5rem" }}>🧩 领域模型</h3>
              <p style={{ margin: 0, fontSize: "0.9rem", opacity: 0.8 }}>
                9 大核心实体详解（用户、智能体、对话、技能、工具、PPT、视频、
                外部系统、公告）、ER 关系、3 个子域边界。
              </p>
            </div>
          </a>

          {/* 卡片：核心业务流程 */}
          <a href="../03-business-processes/article/article.html"
             style={{ textDecoration: "none", color: "inherit" }}>
            <div style={{
              border: "1px solid var(--ra-color-border, #ddd)",
              borderRadius: "var(--ra-radius-lg, 12px)",
              padding: "var(--ra-space-4, 1rem)",
              background: "var(--ra-color-surface, #fff)",
              transition: "box-shadow 0.2s",
              cursor: "pointer",
            }}
            onMouseOver={e => e.currentTarget.style.boxShadow = "var(--ra-shadow-md, 0 4px 12px rgba(0,0,0,0.1))"}
            onMouseOut={e => e.currentTarget.style.boxShadow = "none"}>
              <h3 style={{ margin: "0 0 0.5rem" }}>🔄 核心业务流程</h3>
              <p style={{ margin: 0, fontSize: "0.9rem", opacity: 0.8 }}>
                用户注册登录、AI 对话 SSE 流、PPT 智能生成管线、视频创作流程、
                网站工程、邮箱管理、HITL 审批流、外部系统集成 —— 8 条端到端流程。
              </p>
            </div>
          </a>

          {/* 卡片：关键概念词汇表 */}
          <a href="../06-glossary/article/article.html"
             style={{ textDecoration: "none", color: "inherit" }}>
            <div style={{
              border: "1px solid var(--ra-color-border, #ddd)",
              borderRadius: "var(--ra-radius-lg, 12px)",
              padding: "var(--ra-space-4, 1rem)",
              background: "var(--ra-color-surface, #fff)",
              transition: "box-shadow 0.2s",
              cursor: "pointer",
            }}
            onMouseOver={e => e.currentTarget.style.boxShadow = "var(--ra-shadow-md, 0 4px 12px rgba(0,0,0,0.1))"}
            onMouseOut={e => e.currentTarget.style.boxShadow = "none"}>
              <h3 style={{ margin: "0 0 0.5rem" }}>📖 关键概念词汇表</h3>
              <p style={{ margin: 0, fontSize: "0.9rem", opacity: 0.8 }}>
                60+ 业务术语定义（中英对照），涵盖智能体、工具、审批、外部系统等领域，
                新人速查必备。
              </p>
            </div>
          </a>

          {/* 卡片：系统架构 */}
          <a href="../07-system-architecture/article/article.html"
             style={{ textDecoration: "none", color: "inherit" }}>
            <div style={{
              border: "1px solid var(--ra-color-border, #ddd)",
              borderRadius: "var(--ra-radius-lg, 12px)",
              padding: "var(--ra-space-4, 1rem)",
              background: "var(--ra-color-surface, #fff)",
              transition: "box-shadow 0.2s",
              cursor: "pointer",
            }}
            onMouseOver={e => e.currentTarget.style.boxShadow = "var(--ra-shadow-md, 0 4px 12px rgba(0,0,0,0.1))"}
            onMouseOut={e => e.currentTarget.style.boxShadow = "none"}>
              <h3 style={{ margin: "0 0 0.5rem" }}>🏗️ 系统架构（业务视角）</h3>
              <p style={{ margin: 0, fontSize: "0.9rem", opacity: 0.8 }}>
                前后端部署拓扑、FastAPI + React 技术栈、Docker 部署方案、
                外部系统 6 种认证协议集成模式、多 Agent 模式路由。
              </p>
            </div>
          </a>

        </div>
      </Raw>

      {/* ─── Colophon ─── */}
      <Raw title="">
        <footer
          style={{
            marginTop: "var(--ra-space-7, 3rem)",
            paddingTop: "var(--ra-space-4, 1rem)",
            borderTop: "1px solid var(--ra-color-border, currentColor)",
            color: "var(--ra-color-muted, inherit)",
            fontSize: "var(--ra-text-xs, 0.78rem)",
            textAlign: "center",
            letterSpacing: "0.02em",
            opacity: 0.85,
          }}
        >
          Made with{" "}
          <a
            href="https://github.com/xiaojiaenen/business-analyzer"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              color: "inherit",
              textDecoration: "underline",
              textUnderlineOffset: "0.2em",
            }}
          >
            Business Analyzer
          </a>{" "}
          · press theme
        </footer>
      </Raw>
    </Article>
  );
}
