/**
 * 权限管理：角色 / Casbin 策略 / 审计日志。
 *
 * 部门（departments）已整体下线，授权模型收敛为「用户 → 角色 → 策略」：
 * 角色负责分组，策略描述「谁能对哪个资源做什么」，审计记录每一次变更。
 */
import { useState } from 'react';
import { ScrollText, ShieldCheck, Users2 } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/shadcn/tabs';
import { AdminPageHeader } from './shared';
import { RoleManagementTab } from './RoleManagementTab';
import { PolicyManagementTab } from './PolicyManagementTab';
import { AuditLogTab } from './AuditLogTab';

type PermissionTab = 'roles' | 'policies' | 'audit';

const TAB_ITEMS: { id: PermissionTab; label: string; icon: typeof Users2 }[] = [
  { id: 'roles', label: '角色', icon: Users2 },
  { id: 'policies', label: '策略', icon: ShieldCheck },
  { id: 'audit', label: '审计日志', icon: ScrollText },
];

export function PermissionManagement() {
  const [tab, setTab] = useState<PermissionTab>('roles');

  return (
    <div className="space-y-4">
      <AdminPageHeader
        kicker="Permissions"
        title="权限管理"
        description="用角色分配授权、用策略描述资源边界、用审计日志追溯每一次变更"
      />

      <Tabs value={tab} onValueChange={(value) => setTab(value as PermissionTab)} className="w-full">
        <TabsList>
          {TAB_ITEMS.map((item) => (
            <TabsTrigger key={item.id} value={item.id} className="gap-1.5">
              <item.icon className="h-3.5 w-3.5" />
              {item.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="roles" className="pt-4">
          <RoleManagementTab />
        </TabsContent>
        <TabsContent value="policies" className="pt-4">
          <PolicyManagementTab />
        </TabsContent>
        <TabsContent value="audit" className="pt-4">
          <AuditLogTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
