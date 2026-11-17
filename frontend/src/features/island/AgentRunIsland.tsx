/**
 * AI 对话运行中的实时状态岛（本项目最核心的「耗时长任务」）。
 *
 * 这个应用里一次 agent 运行可能持续几十秒到几分钟，期间经历
 * thinking → streaming → generating_ppt → rendering_ppt 几个阶段，
 * 而且**用户在滚动/切会话时看不到输入区那条进度提示**。
 *
 * 映射依据（skill §3 三问）：
 * - 是什么：一个笔尖 glyph（它在替你干活）
 * - 一眼要看什么：步数（第 3/10 步）或流式百分比
 * - 展开看什么：当前阶段 + 智能体名 + 已输出的字数 + 步进条
 *
 * 用 `group="agent-run"`：同一个会话的多次运行应当轮流显示，而不是并排。
 * 结束时不 alert（常规完成不该抢注意力），失败时 alert（用户必须知道）。
 */
import * as React from 'react';

import { Glyph } from '@/components/islandcn/glyph';
import { PencilGlyph, WarningGlyph, CheckGlyph } from '@/components/islandcn/glyphs';
import { BottomBar, ExpandedBottom, SensorRow } from '@/components/islandcn/island-layout';
import {
  CompactText,
  ContextLabel,
  ExpandedSubtitle,
  ExpandedValue,
  MinimalPair,
  NumberText,
} from '@/components/islandcn/island-text';
import { LinearProgress } from '@/components/islandcn/linear-progress';
import { islandAccent, islandInk, islandMono } from '@/components/islandcn/theme';
import { useActivity } from '@/components/islandcn/use-activity';
import { useChatStore } from '@/stores/chatStore';

/** 阶段 → 人类可读的进行中措辞 + 进度权重（用于算总体百分比）。 */
const PHASES: Record<
  string,
  { verb: string; weight: number; accent: string }
> = {
  thinking: { verb: '思考中', weight: 0.15, accent: islandAccent.blue },
  streaming: { verb: '生成回答', weight: 0.6, accent: islandAccent.blue },
  generating_ppt: { verb: '生成幻灯片', weight: 0.35, accent: islandAccent.purple },
  rendering_ppt: { verb: '渲染预览', weight: 0.85, accent: islandAccent.purple },
  rendering_website: { verb: '构建网站', weight: 0.85, accent: islandAccent.green },
};

/**
 * 用 `label` 细分同一 phase 内的子状态。
 *
 * 后端把「正在上传文件」也归在 thinking 阶段（先传文件、再推理）。岛上
 * 措辞要跟着 label 变，否则用户在传一个 20MB 附件时只看到"思考中"。
 */
function verbFor(phase: string, label: string): string {
  if (label.includes('上传')) return '上传文件';
  if (label.includes('读取') || label.includes('解析')) return '读取文档';
  return PHASES[phase]?.verb ?? (label || '处理中');
}

/** 这段脏活只在这一个组件里：把 runStatus 变成 island 的四个槽位。 */
export const AgentRunIsland: React.FC = () => {
  const runStatus = useChatStore((s) => s.runStatus);
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const sessions = useChatStore((s) => s.sessions);

  const { phase, label, step, maxSteps } = runStatus;
  const running = phase !== 'idle' && phase !== 'done' && phase !== 'error';

  // 当前会话的智能体名（展开视图里显示"谁在干活"）
  const currentSession = React.useMemo(
    () => sessions.find((s) => s.id === currentSessionId),
    [sessions, currentSessionId],
  );
  const agentName = currentSession?.agentName || '智能体';

  // 已输出的字数：流式阶段最直观的"在动"的指标
  const outputChars = React.useMemo(() => {
    const last = [...(currentSession?.messages ?? [])].reverse().find((m) => m.role === 'model');
    return (last?.text ?? '').length;
  }, [currentSession]);

  // 上下文状态（展开视图）：第几轮对话 + 是否已压缩。
  // 数据是真实的：轮数 = 会话里用户消息数；压缩标记来自后端每轮回传的会话状态。
  const turnCount = React.useMemo(
    () => (currentSession?.messages ?? []).filter((m) => m.role === 'user').length,
    [currentSession],
  );
  const contextCompressed = currentSession?.contextCompressed ?? false;

  const base = PHASES[phase] ?? { weight: 0.3, accent: islandAccent.blue };
  const info = { ...base, verb: verbFor(phase, label) };
  const stepText = step && maxSteps ? `${step}/${maxSteps}` : '';
  // 总体进度：阶段基线 + 阶段内的步数推进
  const progress = step && maxSteps
    ? Math.min(0.95, info.weight + (step / maxSteps) * (1 - info.weight))
    : info.weight;

  // 非运行态（done/error/idle）不渲染 —— 结束由外层 effect 驱动
  if (!running) return null;

  return (
    <AgentRunActivity
      phase={phase}
      verb={info.verb}
      accent={info.accent}
      progress={progress}
      stepText={stepText}
      agentName={agentName}
      outputChars={outputChars}
      turnCount={turnCount}
      contextCompressed={contextCompressed}
    />
  );
};

/**
 * 真正的 activity 组件：只在运行中挂载，卸载即结束活动。
 * （`useActivity` 的语义就是「渲染即开始，卸载即结束」。）
 */
const AgentRunActivity: React.FC<{
  phase: string;
  verb: string;
  accent: string;
  progress: number;
  stepText: string;
  agentName: string;
  outputChars: number;
  turnCount: number;
  contextCompressed: boolean;
}> = ({ phase, verb, accent, progress, stepText, agentName, outputChars, turnCount, contextCompressed }) => {
  useActivity(
    () => ({
      id: 'agent-run',
      // 同一会话的多次运行轮流显示，不并排
      group: 'agent-run',
      // 屏幕阅读器读这句
      label: `${agentName}${verb}${stepText ? `，第 ${stepText} 步` : ''}${turnCount > 0 ? `，第 ${turnCount} 轮对话` : ''}${contextCompressed ? '，上下文已压缩' : ''}`,
      compact: {
        leading: <Glyph icon={PencilGlyph} color={accent} />,
        // 胶囊只有约 20pt 的余量：放步数（"3/10" 四个字符刚好）或省略
        trailing: stepText ? (
          <CompactText>
            <NumberText value={stepText} />
          </CompactText>
        ) : undefined,
      },
      minimal: (
        <MinimalPair
          leading={<Glyph icon={PencilGlyph} color={accent} />}
          trailing={
            <CompactText>
              <NumberText value={stepText || '…'} />
            </CompactText>
          }
        />
      ),
      expanded: {
        leading: (
          <SensorRow glyph={<Glyph icon={PencilGlyph} color={accent} size={18} />}>
            <ContextLabel>{verb}</ContextLabel>
          </SensorRow>
        ),
        bottom: (
          <ExpandedBottom gap={6}>
            <ExpandedValue>
              {/* 流式阶段用字数当"大数字"：它是真在变的量 */}
              <NumberText value={outputChars} />
            </ExpandedValue>
            <ExpandedSubtitle color={islandInk.primary}>
              {agentName}
              {stepText ? ` · 第 ${stepText} 步` : ''}
              {turnCount > 0 ? ` · 第 ${turnCount} 轮对话` : ''}
              {contextCompressed ? ' · 上下文已压缩' : ''}
            </ExpandedSubtitle>
            <BottomBar>
              <LinearProgress value={progress} color={accent} height={5} />
            </BottomBar>
          </ExpandedBottom>
        ),
      },
    }),
    [phase, verb, accent, progress, stepText, agentName, outputChars, turnCount, contextCompressed],
  );

  return null;
};

/** 运行失败时的短促提示：用户必须注意到，所以 alert。 */
export const AgentRunErrorIsland: React.FC = () => {
  const runStatus = useChatStore((s) => s.runStatus);
  const [armed, setArmed] = React.useState(false);

  // phase 变成 error 的那一刻 armed=true；用户看到后 6 秒自动收掉
  React.useEffect(() => {
    if (runStatus.phase !== 'error') {
      setArmed(false);
      return;
    }
    setArmed(true);
    const timer = window.setTimeout(() => setArmed(false), 6000);
    return () => window.clearTimeout(timer);
  }, [runStatus.phase]);

  if (!armed) return null;
  return <AgentErrorActivity message={runStatus.label || '本轮回复失败'} />;
};

const AgentErrorActivity: React.FC<{ message: string }> = ({ message }) => {
  useActivity(
    () => ({
      id: 'agent-run-error',
      label: `运行失败：${message}`,
      // 失败必须让用户注意到
      alert: true,
      compact: {
        leading: <Glyph icon={WarningGlyph} color={islandAccent.red} />,
      },
      minimal: <Glyph icon={WarningGlyph} color={islandAccent.red} />,
      expanded: {
        leading: (
          <SensorRow glyph={<Glyph icon={WarningGlyph} color={islandAccent.red} size={18} />}>
            <ContextLabel>失败</ContextLabel>
          </SensorRow>
        ),
        bottom: (
          <ExpandedBottom gap={4}>
            <ExpandedSubtitle color={islandInk.primary}>{message}</ExpandedSubtitle>
          </ExpandedBottom>
        ),
      },
    }),
    [message],
  );

  return null;
};

/** 成功完成的轻提示：不 alert，几秒后自己走。 */
export const AgentRunDoneIsland: React.FC = () => {
  const runStatus = useChatStore((s) => s.runStatus);
  const [armed, setArmed] = React.useState(false);

  React.useEffect(() => {
    if (runStatus.phase !== 'done') {
      setArmed(false);
      return;
    }
    setArmed(true);
    const timer = window.setTimeout(() => setArmed(false), 2500);
    return () => window.clearTimeout(timer);
  }, [runStatus.phase]);

  if (!armed) return null;
  return <AgentDoneActivity />;
};

const AgentDoneActivity: React.FC = () => {
  // 结束那一刻的会话用量：本轮 token 数、耗时、模型调用次数。
  // lastUsage 由后端随会话状态回传（每轮结束更新），是真实值不是估算的 UI 数字。
  const session = useChatStore((s) => s.sessions.find((x) => x.id === s.currentSessionId));
  const usage = session?.lastUsage ?? null;
  const totalTokens = usage
    ? Number(
        usage.total_tokens ??
          (Number(usage.input_tokens ?? usage.prompt_tokens ?? 0) +
            Number(usage.output_tokens ?? usage.completion_tokens ?? 0)),
      )
    : 0;
  const tokenText = totalTokens >= 1000 ? `${(totalTokens / 1000).toFixed(1)}k` : `${totalTokens}`;
  const latencyMs = session?.latencyMs ?? null;
  const llmCalls = session?.llmCalls ?? null;

  useActivity(
    () => ({
      id: 'agent-run-done',
      group: 'agent-run',
      label: `本轮回复已完成${totalTokens > 0 ? `，${tokenText} tokens` : ''}`,
      compact: {
        leading: <Glyph icon={CheckGlyph} color={islandAccent.green} />,
        trailing: totalTokens > 0 ? (
          <CompactText>
            <NumberText value={tokenText} />
          </CompactText>
        ) : undefined,
      },
      minimal: <Glyph icon={CheckGlyph} color={islandAccent.green} />,
      expanded: {
        leading: (
          <SensorRow glyph={<Glyph icon={CheckGlyph} color={islandAccent.green} size={18} />}>
            <ContextLabel>已完成</ContextLabel>
          </SensorRow>
        ),
        bottom: totalTokens > 0 ? (
          <ExpandedBottom gap={4}>
            <ExpandedValue>
              <NumberText value={tokenText} />
              <span style={{ fontFamily: islandMono }}>tokens</span>
            </ExpandedValue>
            <ExpandedSubtitle color={islandInk.secondary}>
              {latencyMs ? `用时 ${(latencyMs / 1000).toFixed(1)}s` : ''}
              {llmCalls ? `${latencyMs ? ' · ' : ''}${llmCalls} 次模型调用` : ''}
            </ExpandedSubtitle>
          </ExpandedBottom>
        ) : undefined,
      },
    }),
    [totalTokens, tokenText, latencyMs, llmCalls],
  );

  return null;
};
