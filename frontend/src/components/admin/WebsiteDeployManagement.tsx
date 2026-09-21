import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/Card';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import { Check, X, ExternalLink, Clock, Globe, Loader2, AlertCircle } from 'lucide-react';
import { listPendingDeploys, listAllDeploys, decideDeploy, type DeployRecord } from '../../services/websiteService';

export function WebsiteDeployManagement() {
  const [pendingDeploys, setPendingDeploys] = useState<DeployRecord[]>([]);
  const [allDeploys, setAllDeploys] = useState<DeployRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [pending, all] = await Promise.all([
        listPendingDeploys(),
        listAllDeploys(),
      ]);
      setPendingDeploys(pending);
      setAllDeploys(all);
    } catch (error) {
      setError(error instanceof Error ? error.message : '加载失败');
    } finally {
      setLoading(false);
    }
  };

  const handleDecide = async (deployId: number, decision: 'approved' | 'rejected') => {
    setActionLoading(`${deployId}-${decision}`);
    try {
      await decideDeploy(deployId, {
        status: decision,
        reason: decision === 'approved' ? '管理员已批准' : '管理员已拒绝',
      });
      setMessage(decision === 'approved' ? '已批准部署' : '已拒绝部署');
      await loadData();
    } catch (error) {
      setError(error instanceof Error ? error.message : '操作失败');
    } finally {
      setActionLoading(null);
    }
  };

  const getStatusBadge = (status: string) => {
    const config: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
      pending: { label: '待审批', variant: 'outline' },
      approved: { label: '已批准', variant: 'default' },
      rejected: { label: '已拒绝', variant: 'destructive' },
      deployed: { label: '已部署', variant: 'secondary' },
    };
    const { label, variant } = config[status] || { label: status, variant: 'outline' as const };
    return <Badge variant={variant}>{label}</Badge>;
  };

  // 自动清除消息
  useEffect(() => {
    if (message || error) {
      const t = setTimeout(() => { setMessage(null); setError(null); }, 3000);
      return () => clearTimeout(t);
    }
  }, [message, error]);

  return (
    <div className="admin-page-stage space-y-4">
      {/* Header */}
      <section className="admin-page-header">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="admin-section-kicker">网站管理</p>
            <h2 className="mt-1.5 text-xl font-semibold tracking-tight text-slate-950">部署审批</h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {message && (
              <div className="rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700">
                {message}
              </div>
            )}
            {error && (
              <div className="flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-medium text-rose-700">
                <AlertCircle size={14} />
                {error}
              </div>
            )}
            <div className="admin-kpi-pill">
              待审批 <span className="font-semibold text-slate-900">{pendingDeploys.length}</span>
            </div>
            <div className="admin-kpi-pill">
              总计 <span className="font-semibold text-slate-900">{allDeploys.length}</span>
            </div>
            <Button variant="secondary" onClick={loadData} disabled={loading} size="sm" className="gap-1.5">
              {loading ? <Loader2 size={14} className="animate-spin" /> : '刷新'}
            </Button>
          </div>
        </div>
      </section>

      {/* Pending Approvals */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Clock className="h-5 w-5" />
            待审批请求
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12 text-slate-500">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              加载中…
            </div>
          ) : pendingDeploys.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">暂无待审批的部署请求</p>
          ) : (
            <div className="space-y-3">
              {pendingDeploys.map((deploy) => (
                <div
                  key={deploy.id}
                  className="flex items-center justify-between rounded-lg border border-slate-200/80 bg-slate-50/50 p-4"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <Globe className="h-4 w-4 text-slate-500" />
                      <span className="font-medium text-slate-900">{deploy.project_slug}</span>
                      <Badge variant="outline">{deploy.stack}</Badge>
                    </div>
                    <div className="mt-1 text-sm text-slate-500">
                      用户 {deploy.requested_by}
                      {deploy.target_domain && ` • ${deploy.target_domain}`}
                    </div>
                    {deploy.preview_url && (
                      <a
                        href={deploy.preview_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-1 inline-flex items-center gap-1 text-sm text-[#2b87c2] hover:underline"
                      >
                        <ExternalLink className="h-3 w-3" />
                        预览
                      </a>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => handleDecide(deploy.id, 'rejected')}
                      disabled={actionLoading !== null}
                    >
                      {actionLoading === `${deploy.id}-rejected` ? (
                        <span className="animate-pulse">...</span>
                      ) : (
                        <>
                          <X className="mr-1 h-4 w-4" />
                          拒绝
                        </>
                      )}
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => handleDecide(deploy.id, 'approved')}
                      disabled={actionLoading !== null}
                    >
                      {actionLoading === `${deploy.id}-approved` ? (
                        <span className="animate-pulse">...</span>
                      ) : (
                        <>
                          <Check className="mr-1 h-4 w-4" />
                          批准
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* All Deploy Requests */}
      <Card>
        <CardHeader>
          <CardTitle>全部部署记录</CardTitle>
        </CardHeader>
        <CardContent>
          {allDeploys.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">暂无部署记录</p>
          ) : (
            <div className="space-y-2">
              {allDeploys.map((deploy) => (
                <div
                  key={deploy.id}
                  className="flex items-center justify-between rounded-lg border border-slate-200/60 p-3"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-slate-900">{deploy.project_slug}</span>
                      <Badge variant="outline">{deploy.stack}</Badge>
                      {getStatusBadge(deploy.status)}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      用户 {deploy.requested_by} • {new Date(deploy.created_at).toLocaleString('zh-CN')}
                    </div>
                  </div>
                  {deploy.status === 'deployed' && deploy.deploy_url && (
                    <a
                      href={deploy.deploy_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-sm text-[#2b87c2] hover:underline"
                    >
                      <ExternalLink className="h-3 w-3" />
                      访问
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
