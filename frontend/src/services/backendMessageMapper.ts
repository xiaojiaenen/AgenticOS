/**
 * 后端消息 → 前端消息的纯映射。
 *
 * 从 agentService.getSessionMessages 抽出来独立成模块：这段逻辑是
 * "会话刷新/重载后能看到什么"的唯一入口，必须是可单测的纯函数 ——
 * 之前内联在请求函数里，历史加载的回归（如图表刷新后消失）只能靠
 * 手工点页面才能发现。
 */
import { toolCallIdOf } from '../lib/messageBlocks';
import type { Message, MessageBlock } from '../types';

/** 后端消息原始格式 */
export type BackendMessage = {
  role: string;
  content: string;
  tool_calls?: Array<{ id?: string; name: string; arguments?: Record<string, unknown> }>;
  tool_call_id?: string;
  name?: string;
  metadata?: Record<string, unknown>;
  /** 思考内容（AIMessage.reasoning_content，5.5 起后端透传） */
  reasoning_content?: string | null;
  /** 落库时间（ISO 字符串）。只在 DB 行上有，wuwei 的 Message 对象没有 */
  created_at?: string | null;
};

/**
 * 数据图表消息的落库/下发格式（chart_events.push_chart 的产物）：
 * ``{version, chart: {title, option}}``。前端 chartMessages 类型是
 * ``{title?, option}``，这里统一解包，并兼容已是扁平结构的旧数据。
 *
 * 为什么导出：SSE 实时路径（agentService 的 chart 事件）和会话恢复路径
 * （mapBackendMessages）拿到的是**同一份后端格式**，解包必须只有这一处 ——
 * 只修一边就会出现「实时是空白卡片、刷新后反而正常」这种互相矛盾的现场。
 */
export function unwrapChartMessage(item: unknown): { title?: string; option: unknown } | null {
  if (!item || typeof item !== 'object') return null;
  const wrapped = item as { chart?: { title?: string; option?: unknown }; title?: string; option?: unknown };
  if (wrapped.chart && typeof wrapped.chart === 'object') {
    return { title: wrapped.chart.title, option: wrapped.chart.option };
  }
  if ('option' in wrapped) return { title: wrapped.title, option: wrapped.option };
  return null;
}

/**
 * 把后端 metadata.artifact 还原成前端 Message 上的四个 xxxArtifact 字段。
 *
 * 后端存的是**产物原始 dict**（`artifact_ready` 事件的 data），字段是
 * snake_case（artifact_id / slide_count / project_slug）。前端流式路径用的是
 * camelCase（artifactId / slideCount / projectSlug），两边必须对齐，
 * 否则「实时生成正常、刷新后按钮全失效」。
 *
 * 只恢复「有标识」的产物：没有 artifactId / projectSlug 的条目点了也回源
 * 不到，留着反而让 UI 显示一个打不开的面板。
 */
export function mapArtifactMetadata(raw: unknown): {
  pptArtifact?: NonNullable<Message['pptArtifact']>;
  websiteArtifact?: NonNullable<Message['websiteArtifact']>;
  documentArtifact?: NonNullable<Message['documentArtifact']>;
  sheetArtifact?: NonNullable<Message['sheetArtifact']>;
} {
  if (!raw || typeof raw !== 'object') return {};
  const byKind = raw as Record<string, unknown>;
  const pick = (kind: string): Record<string, unknown> | null => {
    const entry = byKind[kind];
    return entry && typeof entry === 'object' ? (entry as Record<string, unknown>) : null;
  };
  const str = (v: unknown): string | undefined =>
    typeof v === 'string' && v ? v : undefined;
  const num = (v: unknown): number | undefined =>
    typeof v === 'number' && Number.isFinite(v) ? v : undefined;

  const out: ReturnType<typeof mapArtifactMetadata> = {};

  const ppt = pick('ppt');
  if (ppt) {
    const artifactId = str(ppt.artifact_id) ?? str(ppt.artifactId);
    if (artifactId) {
      out.pptArtifact = {
        status: 'ready',
        artifactId,
        title: str(ppt.title),
        slideCount: num(ppt.slide_count) ?? num(ppt.slideCount),
        theme: str(ppt.theme),
        // html 是预览快照，可能上百 KB —— 不进 localStorage 缓存，
        // 靠 getPptPreviewHtml 回源（与 sheet/document 同一策略）。
      };
    }
  }

  const website = pick('website');
  if (website) {
    const projectSlug = str(website.project_slug) ?? str(website.projectSlug);
    const artifactId = str(website.artifact_id) ?? str(website.artifactId);
    if (projectSlug || artifactId) {
      out.websiteArtifact = {
        status: 'ready',
        artifactId: artifactId ?? projectSlug,
        projectSlug,
        stack: str(website.stack),
        title: str(website.title),
      };
    }
  }

  const document = pick('document');
  if (document) {
    const artifactId = str(document.artifact_id) ?? str(document.artifactId);
    if (artifactId) {
      out.documentArtifact = {
        status: 'ready',
        artifactId,
        title: str(document.title),
        charCount: num(document.char_count) ?? num(document.charCount),
      };
    }
  }

  const sheet = pick('sheet');
  if (sheet) {
    const artifactId = str(sheet.artifact_id) ?? str(sheet.artifactId);
    if (artifactId) {
      out.sheetArtifact = {
        status: 'ready',
        artifactId,
        title: str(sheet.title),
        sheetNames: Array.isArray(sheet.sheet_names)
          ? (sheet.sheet_names as unknown[]).filter((n): n is string => typeof n === 'string')
          : Array.isArray(sheet.sheetNames)
            ? (sheet.sheetNames as unknown[]).filter((n): n is string => typeof n === 'string')
            : undefined,
        sheetCount: num(sheet.sheet_count) ?? num(sheet.sheetCount),
      };
    }
  }

  return out;
}

export function mapBackendMessages(raw: BackendMessage[]): Message[] {  const messages: Message[] = [];
  // 按 tool_call_id 分组 tool 消息
  const toolResultsMap = new Map<string, BackendMessage[]>();

  for (const msg of raw) {
    if (msg.role === 'tool' && msg.tool_call_id) {
      const existing = toolResultsMap.get(msg.tool_call_id) || [];
      existing.push(msg);
      toolResultsMap.set(msg.tool_call_id, existing);
    }
  }

  for (const msg of raw) {
    if (msg.role === 'system') continue; // 跳过 system prompt
    if (msg.role === 'tool') continue;   // tool 结果合并到 assistant 的 toolCalls 中

    if (msg.role === 'user') {
      messages.push({
        id: `backend-${messages.length}`,
        role: 'user',
        createdAt: msg.created_at || undefined,
        text: msg.content || '',
      });
    } else if (msg.role === 'assistant') {
      const toolCalls: import('../types').ToolCall[] | undefined = msg.tool_calls?.map((tc) => {
        const resultMsg = toolResultsMap.get(tc.id || '');
        return {
          id: tc.id,
          name: tc.name,
          status: 'success' as const,
          arguments: tc.arguments,
          result: resultMsg?.map(r => r.content).join('\n') || undefined,
        };
      });
      const metadata = (msg as { metadata?: Record<string, unknown> }).metadata;

      // A2UI 界面消息随助手消息持久化在 metadata.a2ui 里（后端落库时挂上的）。
      // 取回来才能重载会话后继续看到界面 —— 之前只在内存里，刷新即失。
      const a2uiRaw = metadata?.a2ui;
      const a2uiMessages = Array.isArray(a2uiRaw)
        ? (a2uiRaw as import('../types').A2uiMessagePayload[])
        : undefined;

      // 图表走独立通道：metadata.chart 里是 {version, chart:{title,option}} 序列。
      // 之前这里只恢复了 A2UI，图表刷新后消失（用户看到的"图表不见了"的
      // 第二种形态 —— 出图了，但刷新一次就没了）。
      const chartRaw = metadata?.chart;
      const chartMessages = Array.isArray(chartRaw)
        ? chartRaw
            .map(unwrapChartMessage)
            .filter((c): c is { title?: string; option: unknown } => c !== null)
        : undefined;

      // 产物恢复：metadata.artifact 是 {ppt?: {...}, website?: {...}, ...}。
      //
      // 这是「刷新后 PPT 导不出、主题切换无效、侧边栏没有主题/导出/编辑按钮」
      // 三个症状的同一个根因 —— artifact_ready 只是 SSE 事件，从不落库，
      // 重载会话时前端拿不到 artifactId，于是：
      //   * handleExport 在无 artifactId 时静默 return（点了没反应）
      //   * handleThemeChange 同理 early-return
      //   * IdeSidebar 只渲染预览 HTML，工具栏长在 PptArtifactPanel 上
      // 后端现已把产物挂进 metadata.artifact（见 artifact_events.py），
      // 这里按 xxxArtifact 字段还原成与流式路径完全一致的结构。
      const { pptArtifact, websiteArtifact, documentArtifact, sheetArtifact } =
        mapArtifactMetadata(metadata?.artifact);

      // 思考内容：后端透传 AIMessage.reasoning_content（5.5）。流式阶段
      // 用户实时看到了思考，刷新后如果没有它，"停止"打断的轮次没有
      // 最终文本，气泡里就什么都没有。
      const reasoningText = msg.reasoning_content || undefined;

      // ── 5.5 空 assistant 气泡过滤 ──
      // agent 是多轮工具循环，被打断（点停止 / 撞步骤上限）后停在 tool_calls
      // 中间，没有最终文本落库；此时这条 assistant 只剩过渡 content（'\n\n'
      // 之类）或干脆为空。有实际内容的才保留：
      //   - 有可见文本 → 正常保留
      //   - 有 A2UI/图表产物 → 保留（产物就是这条消息的内容）
      //   - 有思考内容 → 保留（思考就是可见内容）
      //   - 有工具调用 → 保留（工具链本身就是内容；且它的 tool 结果消息
      //     要靠这条 assistant 的 tool_call_id 才能配对，丢掉 = 工具历史断链）
      //   - 什么都没有 → 跳过
      const hasVisibleText = Boolean(msg.content?.trim());
      const hasArtifacts =
        (a2uiMessages && a2uiMessages.length > 0) ||
        (chartMessages && chartMessages.length > 0) ||
        // 产物就是这条消息的全部内容 —— PPT 模式收尾时 orchestrator 明确
        // 把 visible_text 置空（"artifact_ready" 之后没有正文），不带产物
        // 判定就会把这条消息整条丢掉，刷新后 PPT 从会话里消失。
        Boolean(pptArtifact || websiteArtifact || documentArtifact || sheetArtifact);
      const hasToolCalls = Boolean(toolCalls && toolCalls.length > 0);
      if (!hasVisibleText && !hasArtifacts && !reasoningText && !hasToolCalls) {
        continue;
      }

      // blocks 必须生成：ChatMessage 的按序渲染（正文/工具/思考交错、
      // 工具链嵌在气泡内）要求 message.blocks 非空 —— 缺失会回退到
      // **弃用的旧式三桶布局**（工具链在气泡外、样式与流式完全不同），
      // 用户看到的"刷新后变成旧风格、工具在外面"就是它。
      // 顺序按后端 raw 序：一条 assistant = 思考 + 它的 tool_calls + 正文。
      const blocks: MessageBlock[] = [];
      if (reasoningText) blocks.push({ kind: 'reasoning', text: reasoningText });
      (toolCalls || []).forEach((tc, i) => {
        blocks.push({ kind: 'tool', toolCallId: toolCallIdOf(tc, i) });
      });
      if (msg.content?.trim()) blocks.push({ kind: 'text', text: msg.content });

      messages.push({
        id: `backend-${messages.length}`,
        role: 'model',
        // 时间戳必须显式透传：ChatMessage 原来靠 parseInt(message.id) 从
        // 流式 id 里抠时间，历史消息 id 是 "backend-0"，parseInt 得到 NaN，
        // 于是刷新后整片时间消失。
        createdAt: msg.created_at || undefined,
        text: msg.content || '',
        reasoningText,
        toolCalls: toolCalls && toolCalls.length > 0 ? toolCalls : undefined,
        a2uiMessages,
        chartMessages: chartMessages && chartMessages.length > 0 ? chartMessages : undefined,
        // 产物（PPT/网站/文档/表格）：刷新后靠它恢复 artifactId，
        // 否则导出/主题切换/侧栏工具栏全部失联（见 mapArtifactMetadata 注释）
        ...(pptArtifact ? { pptArtifact } : {}),
        ...(websiteArtifact ? { websiteArtifact } : {}),
        ...(documentArtifact ? { documentArtifact } : {}),
        ...(sheetArtifact ? { sheetArtifact } : {}),
        blocks: blocks.length > 0 ? blocks : undefined,
      });
    }
  }
  return messages;
}
