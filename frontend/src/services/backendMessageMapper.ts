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
  /**
   * 工具调用。后端落库是 **OpenAI 兼容格式**：
   * ``{id, type: 'function', function: {name, arguments}}``；
   * 但早期/其他路径也可能给扁平形态 ``{id, name, arguments}``。
   * 两种都要认（见 normalizeToolCall）—— 只读 tc.name 会让工具名全变
   * undefined，工具块渲染成空白行（用户报"空气泡"的一类）。
   */
  tool_calls?: Array<{
    id?: string;
    name?: string;
    arguments?: Record<string, unknown>;
    function?: { name?: string; arguments?: Record<string, unknown> | string };
  }>;
  tool_call_id?: string;
  name?: string;
  metadata?: Record<string, unknown>;
  /** 思考内容（AIMessage.reasoning_content，5.5 起后端透传） */
  reasoning_content?: string | null;
  /** 落库时间（ISO 字符串）。只在 DB 行上有，wuwei 的 Message 对象没有 */
  created_at?: string | null;
};

/** 把两种 tool_call 形态归一成前端要的扁平结构。 */
export function normalizeToolCall(
  tc: NonNullable<BackendMessage['tool_calls']>[number],
  index: number,
): { id?: string; name: string; arguments?: Record<string, unknown> } {
  const fn = tc.function;
  const rawArgs = fn?.arguments ?? tc.arguments;
  let args: Record<string, unknown> | undefined;
  if (typeof rawArgs === 'string') {
    // arguments 可能是 JSON 字符串（OpenAI 格式）—— 解不出来就不带参数，
    // 不要让一个坏参数把整条消息渲染打断
    try {
      args = rawArgs ? (JSON.parse(rawArgs) as Record<string, unknown>) : undefined;
    } catch {
      args = undefined;
    }
  } else {
    args = rawArgs;
  }
  return {
    id: tc.id,
    // 嵌套形态优先；都没有时给一个稳定占位名，避免 UI 出现空白行
    name: fn?.name || tc.name || `tool_${index + 1}`,
    arguments: args,
  };
}

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

    /**
     * 连续「无正文」assistant 合并。
     *
     * 一次 agent 跑动会产生很多轮 assistant：每轮只是发起若干工具调用、
     * 正文为空（``"\n\n\n"``）。把它们各自渲染成一个气泡，就是用户看到的
     * "一整屏空气泡"（截图里连续十几个只有头像和时间的气泡）——尤其是
     * 上游限流打断后，正文永远补不上。
     *
     * 判定：正文为空 且 没有产物/A2UI/图表 → 视为空壳，把它的
     * toolCalls / reasoning / 产物挂到**上一条模型消息**上一起渲染；
     * 上一条不是模型消息（或还没有）时，才新建一条承载。
     */
    if (msg.role === 'user') {
      messages.push({
        id: `backend-${messages.length}`,
        role: 'user',
        createdAt: msg.created_at || undefined,
        text: msg.content || '',
      });
    } else if (msg.role === 'assistant') {
      const toolCalls: import('../types').ToolCall[] | undefined = msg.tool_calls?.map((tc, i) => {
        // 归一 OpenAI 嵌套格式：后端落库是 {function:{name,arguments}}，
        // 只读 tc.name 会全是 undefined（工具块变成空白行）
        const normalized = normalizeToolCall(tc, i);
        const resultMsgs = toolResultsMap.get(normalized.id || '');
        // **状态必须取自 tool 结果的 metadata.tool_outcome**，不能硬编码。
        // 曾经写死 `status: 'success'`：实时看到的红色「失败」刷新后全变绿
        // （用户报「刷新了页面，error 的工具都变成功了」）。后端在 tool 消息
        // 的 metadata 里明确记了 {status: 'success'|'error', executed, ...}。
        const outcome = resultMsgs?.find((r) => r.metadata?.tool_outcome)?.metadata?.tool_outcome as
          | { status?: string }
          | undefined;
        const isError = outcome?.status === 'error';
        return {
          id: normalized.id,
          name: normalized.name,
          status: (isError ? 'error' : 'success') as 'success' | 'error',
          arguments: normalized.arguments,
          result: resultMsgs?.map(r => r.content).join('\n') || undefined,
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
      // agent 是多轮工具循环，被打断（点停止 / 撞步骤上限 / 上游限流）后
      // 停在 tool_calls 中间，没有最终文本落库；此时这条 assistant 只剩
      // 过渡 content（'\n\n' 之类）或干脆为空。有实际内容的才保留：
      //   - 有可见文本 → 正常保留
      //   - 有 A2UI/图表产物 → 保留（产物就是这条消息的内容）
      //   - 有工具调用 → 保留（工具链本身就是内容；且它的 tool 结果消息
      //     要靠这条 assistant 的 tool_call_id 才能配对，丢掉 = 工具历史断链）
      //   - 只有思考、没有正文也没有工具 → **跳过**
      //     曾经这条是「有思考就保留」，结果一轮 PPT 生成中断后落库了十几条
      //     「空正文 + 只有 reasoning」的 assistant 行，刷新后整屏空气泡
      //     （用户报的"中断后刷新出现这么多空气泡"）。思考是过程性内容，
      //     没有正文/工具可依附时不该单独占一个气泡。
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
      if (!hasVisibleText && !hasArtifacts && !hasToolCalls) {
        continue;
      }
      // 思考只在确有其它内容（正文或工具）时作为块保留 —— 纯思考壳已被上面跳过
      const reasoningBlock = hasVisibleText || hasToolCalls ? reasoningText : undefined;

      // blocks 必须生成：ChatMessage 的按序渲染（正文/工具/思考交错、
      // 工具链嵌在气泡内）要求 message.blocks 非空 —— 缺失会回退到
      // **弃用的旧式三桶布局**（工具链在气泡外、样式与流式完全不同），
      // 用户看到的"刷新后变成旧风格、工具在外面"就是它。
      // 顺序按后端 raw 序：一条 assistant = 思考 + 它的 tool_calls + 正文。
      const newBlocks: MessageBlock[] = [];
      if (reasoningBlock) newBlocks.push({ kind: 'reasoning', text: reasoningBlock });
      (toolCalls || []).forEach((tc, i) => {
        newBlocks.push({ kind: 'tool', toolCallId: toolCallIdOf(tc, i) });
      });
      if (msg.content?.trim()) newBlocks.push({ kind: 'text', text: msg.content });

      const snapshot = {
        createdAt: msg.created_at || undefined,
        text: msg.content?.trim() ? msg.content : '',
        reasoningText: reasoningBlock,
        toolCalls: toolCalls && toolCalls.length > 0 ? toolCalls : undefined,
        a2uiMessages,
        chartMessages: chartMessages && chartMessages.length > 0 ? chartMessages : undefined,
        // 产物（PPT/网站/文档/表格）：刷新后靠它恢复 artifactId，
        // 否则导出/主题切换/侧栏工具栏全部失联（见 mapArtifactMetadata 注释）
        ...(pptArtifact ? { pptArtifact } : {}),
        ...(websiteArtifact ? { websiteArtifact } : {}),
        ...(documentArtifact ? { documentArtifact } : {}),
        ...(sheetArtifact ? { sheetArtifact } : {}),
        newBlocks,
      };

      // 同一轮回答的所有 assistant 行合并成一个气泡（与流式表现对齐）。
      //
      // 后端把每个 LLM 步骤各存一条 assistant：第一轮给了正文、中间几轮
      // 发起工具、最后一轮再给正文 + 解释。实时流式时这些 delta 全部累积
      // 到一条消息里，所以用户只看到一个气泡；但历史映射此前只合并
      // 「空壳」（无正文无产物）行，最后那条有正文的会另起一个气泡 ——
      // 用户刷新后就看到「一个气泡分裂成两个」。
      //
      // 规则：以 user 消息为轮次分界。user 之后的第一条 assistant 新建气泡；
      // 同一轮里后续的 assistant（无论空壳还是带正文）全部并入它。
      const prev = messages[messages.length - 1];
      if (prev && prev.role === 'model') {
        prev.blocks = [...(prev.blocks ?? []), ...newBlocks];
        if (snapshot.toolCalls) {
          prev.toolCalls = [...(prev.toolCalls ?? []), ...snapshot.toolCalls];
        }
        if (snapshot.text) {
          prev.text = prev.text ? `${prev.text}\n\n${snapshot.text}` : snapshot.text;
        }
        if (snapshot.reasoningText) {
          prev.reasoningText = prev.reasoningText
            ? `${prev.reasoningText}\n\n${snapshot.reasoningText}`
            : snapshot.reasoningText;
        }
        // 后续轮次可能带产物（PPT/网站等），一并挂到同一气泡上
        if (snapshot.pptArtifact) prev.pptArtifact = snapshot.pptArtifact;
        if (snapshot.websiteArtifact) prev.websiteArtifact = snapshot.websiteArtifact;
        if (snapshot.documentArtifact) prev.documentArtifact = snapshot.documentArtifact;
        if (snapshot.sheetArtifact) prev.sheetArtifact = snapshot.sheetArtifact;
        if (snapshot.a2uiMessages?.length) {
          prev.a2uiMessages = [...(prev.a2uiMessages ?? []), ...snapshot.a2uiMessages];
        }
        if (snapshot.chartMessages?.length) {
          prev.chartMessages = [...(prev.chartMessages ?? []), ...snapshot.chartMessages];
        }
        continue;
      }

      messages.push({
        id: `backend-${messages.length}`,
        role: 'model',
        createdAt: snapshot.createdAt,
        text: snapshot.text,
        reasoningText: snapshot.reasoningText,
        toolCalls: snapshot.toolCalls,
        a2uiMessages: snapshot.a2uiMessages,
        chartMessages: snapshot.chartMessages,
        ...(snapshot.pptArtifact ? { pptArtifact: snapshot.pptArtifact } : {}),
        ...(snapshot.websiteArtifact ? { websiteArtifact: snapshot.websiteArtifact } : {}),
        ...(snapshot.documentArtifact ? { documentArtifact: snapshot.documentArtifact } : {}),
        ...(snapshot.sheetArtifact ? { sheetArtifact: snapshot.sheetArtifact } : {}),
        blocks: newBlocks.length > 0 ? newBlocks : undefined,
      });
    }
  }
  return messages;
}
