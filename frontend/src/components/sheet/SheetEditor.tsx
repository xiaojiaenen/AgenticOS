import React from 'react';

/**
 * Univer 编辑器宿主。
 *
 * SDK 在挂载时动态 import —— 它 gzip 后约 1.7MB，静态 import 会把整个
 * Chat 页面的首屏包拖进来。所有资源自托管，无外部请求。
 *
 * 卸载必须调 univer.dispose()：它负责拆插件与 ResizeObserver，但**不会**
 * 移除自己 append 进容器的 canvas，所以还要手动清空容器。
 *
 * 快照通过 ref 暴露（命令式）而不是每次按键自动回传：自动回传需要挂
 * Univer 的内部事件流，那层 API 跨版本变动大，而且用户改一个字就把整本
 * 工作簿推给上层没有意义。改成「用户点保存时才取一次」。
 */

export type SheetEditorHandle = {
  /** 从当前编辑器实例取一份快照。实例未就绪时返回 null。 */
  getSnapshot: () => Record<string, unknown> | null;
  /** 是否已加载完成 */
  isReady: () => boolean;
};

type SheetEditorProps = {
  snapshot: Record<string, unknown>;
  /** 主题切换时同步给 Univer（它自成一套 UI 命名空间，不会自动跟随） */
  dark: boolean;
};

type UniverInstance = { dispose: () => void };
type UniverWorkbook = {
  save: () => Record<string, unknown>;
  getId: () => string;
};
type UniverAPI = {
  createWorkbook: (data: Record<string, unknown>) => UniverWorkbook;
  getActiveWorkbook: () => UniverWorkbook | null;
};
type CreateUniver = (config: Record<string, unknown>) => {
  univer: UniverInstance;
  univerAPI: UniverAPI;
};

export const SheetEditor = React.forwardRef<SheetEditorHandle, SheetEditorProps>(
  function SheetEditor({ snapshot, dark }, ref) {
    const hostRef = React.useRef<HTMLDivElement>(null);
    const apiRef = React.useRef<UniverAPI | null>(null);
    const readyRef = React.useRef(false);
    const [error, setError] = React.useState<string | null>(null);
    const [ready, setReady] = React.useState(false);

    // 快照只在挂载时读入一次。之后的编辑由编辑器自身持有。
    const initialSnapshot = React.useRef(snapshot);

    React.useImperativeHandle(
      ref,
      () => ({
        getSnapshot: () => {
          if (!readyRef.current) return null;
          try {
            return apiRef.current?.getActiveWorkbook()?.save() ?? null;
          } catch {
            return null;
          }
        },
        isReady: () => readyRef.current,
      }),
      [],
    );

    React.useEffect(() => {
      const host = hostRef.current;
      if (!host) return;

      let disposed = false;
      let instance: UniverInstance | null = null;

      const bootstrap = async () => {
        try {
          // 语言包必须逐包合并：preset 包里的 zh-CN 只覆盖表格模型层，工具栏、
          // 右键菜单这些 UI 文案分散在 @univerjs/ui 与各 *-ui 包各自的
          // /locale 子路径下。漏合并的话界面上会出现 ui.ribbon.start 这种原始 key。
          const [presetsCore, core, ...localeModules] = await Promise.all([
            import('@univerjs/presets'),
            import('@univerjs/preset-sheets-core'),
            import('@univerjs/preset-sheets-core/locales/zh-CN'),
            import('@univerjs/design/locale/zh-CN'),
            import('@univerjs/ui/locale/zh-CN'),
            import('@univerjs/sheets-ui/locale/zh-CN'),
            import('@univerjs/sheets-numfmt-ui/locale/zh-CN'),
            import('@univerjs/sheets-formula-ui/locale/zh-CN'),
            import('@univerjs/docs-ui/locale/zh-CN'),
            import('@univerjs/preset-sheets-core/lib/index.css'),
          ]);
          if (disposed) return;

          const { createUniver, LocaleType, mergeLocales } = presetsCore;
          const { UniverSheetsCorePreset } = core;
          // 各 locale 模块的默认导出才是语言包本身
          const localePacks = localeModules
            .slice(0, 7)
            .map((module) => (module as { default?: unknown }).default ?? module);

          const created = (createUniver as unknown as CreateUniver)({
            locale: LocaleType.ZH_CN,
            locales: { [LocaleType.ZH_CN]: mergeLocales(...localePacks) },
            presets: [UniverSheetsCorePreset({ container: host })],
          });
          instance = created.univer;
          apiRef.current = created.univerAPI;
          created.univerAPI.createWorkbook(initialSnapshot.current);
          readyRef.current = true;
          setReady(true);
        } catch (err) {
          if (!disposed) {
            setError(
              err instanceof Error
                ? `表格编辑器加载失败：${err.message}`
                : '表格编辑器加载失败',
            );
          }
        }
      };

      void bootstrap();

      return () => {
        disposed = true;
        readyRef.current = false;
        setReady(false);
        apiRef.current = null;
        try {
          instance?.dispose();
        } catch {
          // 卸载期异常不影响后续渲染
        }
        host.replaceChildren();
      };
      // 刻意只挂载一次：重建会丢失用户已做的编辑。
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // 暗色不是调 API，而是切宿主元素上的 .univer-dark 类 —— Univer 的样式表
    // 就是靠这个类选择器（.dark\:xxx:where(.univer-dark, .univer-dark *)）切换的，
    // 比找一个跨版本可能不存在的 facade 方法稳。
    React.useEffect(() => {
      hostRef.current?.classList.toggle('univer-dark', dark);
    }, [dark]);

    if (error) {
      return (
        <div className="p-6 text-sm text-[var(--muted-foreground)]">
          <p>{error}</p>
          <p className="mt-2">刷新页面可重试；如持续失败请把上面的报错发给管理员。</p>
        </div>
      );
    }

    return (
      <div className="relative h-full w-full">
        <div ref={hostRef} className="h-full w-full" />
        {!ready && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-[var(--surface-1)] text-sm text-[var(--muted-foreground)]">
            正在加载表格编辑器…
          </div>
        )}
      </div>
    );
  },
);
