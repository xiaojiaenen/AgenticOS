import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Brain, Code2, FolderGit2, Sparkles, Target, Trash2 } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../shadcn/dialog';
import { Button } from '../shadcn/button';
import { cn } from '../../lib/utils';
import { toastError } from '../../lib/errors';
import { deleteMemory, getPortrait } from '../../services/memoryService';

const TYPE_LABEL: Record<string, string> = {
  fact: '事实', preference: '偏好', habit: '习惯', goal: '目标', skill: '技能', event: '经历',
};

function Chip({ children, tone = 'default' }: { children: React.ReactNode; tone?: 'default' | 'like' | 'dislike' }) {
  return (
    <span className={cn(
      'rounded-full px-2.5 py-1 text-xs font-medium',
      tone === 'like' && 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
      tone === 'dislike' && 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300',
      tone === 'default' && 'bg-[var(--surface-2)] text-[var(--foreground)]',
    )}>{children}</span>
  );
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
      <div className="mb-2.5 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
        {icon} {title}
      </div>
      {children}
    </div>
  );
}

export function PortraitCard({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['portrait'], queryFn: getPortrait, enabled: open });
  const del = useMutation({
    mutationFn: (id: number) => deleteMemory(id),
    onSuccess: () => { toast.success('已删除这条记忆'); void qc.invalidateQueries({ queryKey: ['portrait'] }); },
    onError: (e) => toast.error(toastError(e, '删除失败')),
  });
  const d = q.data;
  const likes = d?.preferences?.likes ?? [];
  const dislikes = d?.preferences?.dislikes ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[88vh] max-w-2xl flex-col overflow-hidden p-0">
        <DialogHeader className="border-b border-[var(--border-subtle)] px-5 py-4">
          <DialogTitle className="flex items-center gap-2 text-base">
            <Sparkles size={18} className="text-zinc-500" /> AI 眼中的你
          </DialogTitle>
          <DialogDescription className="text-xs">基于你们的对话自动提炼 · 你可以随时纠正或删除</DialogDescription>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {q.isLoading ? (
            <div className="py-10 text-center text-sm text-[var(--muted-foreground)]">加载中…</div>
          ) : !d ? (
            <div className="py-10 text-center text-sm text-[var(--muted-foreground)]">加载失败</div>
          ) : (
            <div className="flex flex-col gap-4">
              <div className="rounded-xl bg-gradient-to-br from-zinc-500/10 to-violet-500/10 p-4 text-sm leading-relaxed text-[var(--foreground)]">
                {d.summary}
              </div>

              {d.atom_count === 0 ? (
                <div className="flex flex-col items-center gap-2 py-8 text-center">
                  <Brain size={28} className="text-[var(--muted-foreground)]" />
                  <p className="text-sm text-[var(--muted-foreground)]">多聊几句，AI 会慢慢记住你的偏好与正在做的事。</p>
                </div>
              ) : (
                <>
                  {(d.identity?.name || d.identity?.role || d.identity?.location) && (
                    <Section icon={<Brain size={14} />} title="身份">
                      <div className="flex flex-wrap gap-2">
                        {d.identity.name && <Chip>{d.identity.name}</Chip>}
                        {d.identity.role && <Chip>{d.identity.role}</Chip>}
                        {d.identity.location && <Chip>{d.identity.location}</Chip>}
                      </div>
                    </Section>
                  )}

                  {(likes.length > 0 || dislikes.length > 0) && (
                    <Section icon={<Sparkles size={14} />} title="喜好">
                      <div className="flex flex-wrap gap-2">
                        {likes.map((x) => <Chip key={`l-${x}`} tone="like">♥ {x}</Chip>)}
                        {dislikes.map((x) => <Chip key={`d-${x}`} tone="dislike">✕ {x}</Chip>)}
                      </div>
                    </Section>
                  )}

                  {d.tech_stack.length > 0 && (
                    <Section icon={<Code2 size={14} />} title="技术栈">
                      <div className="flex flex-wrap gap-2">{d.tech_stack.map((x) => <Chip key={x}>{x}</Chip>)}</div>
                    </Section>
                  )}

                  {d.goals.length > 0 && (
                    <Section icon={<Target size={14} />} title="目标">
                      <ul className="flex flex-col gap-1.5 text-sm text-[var(--foreground)]">
                        {d.goals.map((g, i) => <li key={i} className="flex gap-2"><span className="text-zinc-500">▸</span>{g}</li>)}
                      </ul>
                    </Section>
                  )}

                  {d.projects.length > 0 && (
                    <Section icon={<FolderGit2 size={14} />} title="正在做的项目">
                      <div className="flex flex-col gap-2">
                        {d.projects.map((p, i) => (
                          <div key={i} className="rounded-lg bg-[var(--surface-2)] p-2.5">
                            <div className="flex items-center gap-2 text-sm font-medium text-[var(--foreground)]">
                              {p.name}
                              <span className="rounded bg-zinc-500/10 px-1.5 py-0.5 text-[10px] text-zinc-600 dark:text-zinc-400">{p.status}</span>
                            </div>
                            {p.summary && <p className="mt-1 text-xs text-[var(--muted-foreground)]">{p.summary}</p>}
                          </div>
                        ))}
                      </div>
                    </Section>
                  )}

                  <Section icon={<Brain size={14} />} title={`记忆碎片 · ${d.atom_count} 条`}>
                    <div className="mb-2 flex flex-wrap gap-1.5">
                      {Object.entries(d.atoms_by_type).map(([t, c]) => (
                        <span key={t} className="rounded bg-[var(--surface-2)] px-2 py-0.5 text-[11px] text-[var(--muted-foreground)]">{TYPE_LABEL[t] ?? t} {c}</span>
                      ))}
                    </div>
                    <div className="flex flex-col gap-1.5">
                      {d.recent_atoms.map((a) => (
                        <div key={a.id} className="group flex items-start gap-2 rounded-lg border border-[var(--border-subtle)] p-2.5">
                          <p className="min-w-0 flex-1 text-xs leading-relaxed text-[var(--foreground)]">{a.content}</p>
                          <button type="button" onClick={() => del.mutate(a.id)} disabled={del.isPending}
                            aria-label="删除记忆"
                            className="shrink-0 rounded p-1 text-[var(--muted-foreground)] opacity-0 transition hover:bg-rose-50 hover:text-rose-600 group-hover:opacity-100 dark:hover:bg-rose-500/10">
                            <Trash2 size={13} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </Section>
                </>
              )}

              <Button variant="outline" size="sm" className="gap-1.5 self-start" onClick={() => { onOpenChange(false); navigate('/wrapped'); }}>
                <Sparkles size={14} /> 查看我的年度报告
              </Button>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
