import React from 'react';

/**
 * Univer 文档编辑器宿主。
 *
 * 与表格编辑器同构：SDK 挂载时动态 import（整包 gzip 约 1.7MB，静态引入会把
 * Chat 首屏拖垮），卸载必须 dispose 并手动清空容器（dispose 不移除 canvas）。
 *
 * 暗色靠宿主元素上的 .univer-dark 类切换 —— Univer 样式表就是这么写的
 * （.dark\:xxx:where(.univer-dark, .univer-dark *)），比赌一个可能跨版本
 * 不存在的 facade 方法稳。
 */

export type DocEditorHandle = {
  getSnapshot: () => Record<string, unknown> | null;
  isReady: () => boolean;
};

type DocEditorProps = {
  snapshot: Record<string, unknown>;
  dark: boolean;
};

type UniverInstance = { dispose: () => void };
type UniverDocument = {
  save: () => Record<string, unknown>;
  getId: () => string;
};
type UniverAPI = {
  /**
   * 浏览器端 Docs preset 注册了这个方法（Node 端没有，那边只能走 createUnit）。
   * 必须用它而不是底层 createUnit —— 否则 UI 不会把视口挂到该单元上，表现为
   * 工具栏正常、状态栏能显示字数，但正文画布一片空白。
   */
  createDocument: (data: Record<string, unknown>) => UniverDocument;
  getActiveDocument?: () => UniverDocument | null;
};
type CreateUniver = (config: Record<string, unknown>) => {
  univer: {
    dispose: () => void;
    createUnit: (type: unknown, data: Record<string, unknown>) => UniverDocument;
  };
  univerAPI: UniverAPI;
};

/**
 * 把后端产出的「逻辑文档」物化成浏览器可渲染的完整 IDocumentData。
 *
 * 为什么必须在前端做：Univer 的文档模型里，`body.textRuns` / `blockRanges` /
 * `tables` / `columnGroups` 等派生结构是由浏览器侧的插件在装载时算出来的。
 * 后端（Node，无 UI 插件）只能产出 `dataStream` + `paragraphs`，那些派生字段
 * 在快照里是 undefined，JSON 序列化时被丢掉。
 *
 * 直接渲染这种残缺快照的后果非常隐蔽：文档模型加载成功（状态栏字数正确）、
 * 工具栏完整，但正文画布只画一层背景、一个字都不显示。
 *
 * 做法：先让 Univer 自己建一份空文档拿到规范化模板（含全部派生字段），再把
 * 后端的内容覆盖上去 —— 等价于浏览器自己生成文档，再由后端提供内容。
 */

/**
 * 补齐 dataStream 的收尾 `\n`。
 *
 * Univer 的文档流里 `\r` 结束一个段落，末尾还必须有一个 `\n` 收尾。后端早期
 * 落盘的快照只写到 `\r` —— 那种快照照样能装载、状态栏字数也对，但渲染器把
 * 整份文档判成空的，正文页只剩「请输入文字」占位提示。历史产物要靠这里救回来，
 * 否则用户一打开旧文档就是一块白板。
 *
 * 只补不删：末尾本来就有空段落（连续 `\r`）时要原样保留。
 */
function withDocumentTerminator(stream: string): string {
  if (stream.endsWith('\r\n')) return stream;
  if (stream.endsWith('\r')) return `${stream}\n`;
  return `${stream}\r\n`;
}

/**
 * 标题的排版规格。
 *
 * 与后端 office-runtime/server.mjs 里的 HEADING_TEXT_STYLE 保持一致。
 * `namedStyleType` 只负责段上下间距，字号粗细必须落到 body.textRuns 上——
 * 段落级 paragraphStyle.textStyle 实测渲染器不读，只有字素级样式才生效。
 */
const HEADING_TEXT_STYLE: Record<string, { fs: number; bl: number }> = {
  h1: { fs: 32, bl: 1 },
  h2: { fs: 24, bl: 1 },
  h3: { fs: 18, bl: 1 },
  h4: { fs: 16, bl: 1 },
};

/** 旧快照里的 headingLevel → Univer 1.0.3 的 NamedStyleType（HEADING_1 起步是 4）。 */
const LEGACY_HEADING_TO_NAMED_STYLE: Record<number, number> = { 1: 4, 2: 5, 3: 6, 4: 7 };

type SourceParagraph = {
  startIndex?: number;
  paragraphStyle?: { headingLevel?: number; namedStyleType?: number } | null;
};
type SourceTextRun = { st: number; ed: number; ts?: Record<string, unknown> };

/**
 * 补齐标题的视觉样式。
 *
 * 两个坑叠在一起，缺一个都会让标题「看起来完全没生效」：
 *
 * 1. 字段名换了。旧快照写的是 `paragraphStyle.headingLevel`，但 Univer 1.0.3
 *    的渲染层已经不消费它（真正生效的是 `namedStyleType`，且枚举值不是 1/2/3/4，
 *    HEADING_1 起步就是 4）。照抄旧值等于什么都没设。
 * 2. 字号不来自段落样式。`namedStyleType` 在 core 里只映射到段间距
 *    （NAMED_STYLE_SPACE_MAP），字号一个字都不给。所以还得按段落区间补
 *    `body.textRuns`（字素级样式），渲染器只认这个。
 *
 * 结果就是标题上方空了一段、字号却和正文一样——比什么都不写更像坏了。
 */
function withHeadingStyles(
  paragraphs: SourceParagraph[],
  dataStream: string,
  existingTextRuns: SourceTextRun[],
): { paragraphs: SourceParagraph[]; textRuns: SourceTextRun[] } {
  const styled = paragraphs.map((para) => {
    const style = para.paragraphStyle;
    if (!style) return para;
    // 已经是新版字段就原样保留
    if (style.namedStyleType != null) return para;
    const namedStyleType = style.headingLevel == null
      ? undefined
      : LEGACY_HEADING_TO_NAMED_STYLE[style.headingLevel];
    if (namedStyleType == null) return para;
    const { headingLevel: _dropped, ...rest } = style;
    return { ...para, paragraphStyle: { ...rest, namedStyleType } };
  });

  // 已经带字素样式就不用再补（用户可能自己调过）
  if (existingTextRuns.length > 0) return { paragraphs: styled, textRuns: existingTextRuns };

  const textRuns: SourceTextRun[] = [];
  styled.forEach((para, index) => {
    const namedStyleType = para.paragraphStyle?.namedStyleType;
    if (namedStyleType == null) return;
    // NamedStyleType: 4=HEADING_1 … 7=HEADING_4；其它值（TITLE/SUBTITLE）没配字号
    const spec = HEADING_TEXT_STYLE[`h${namedStyleType - 3}`];
    if (!spec) return;
    const start = para.startIndex ?? 0;
    // 段落区间：从 startIndex 到下一个段落的 startIndex（或流尾）
    const end = styled[index + 1]?.startIndex ?? dataStream.length;
    const textEnd = Math.min(end, dataStream.length);
    if (textEnd <= start) return;
    textRuns.push({ st: start, ed: textEnd, ts: { ...spec } });
  });

  return { paragraphs: styled, textRuns };
}

function materializeDocument(
  api: UniverAPI,
  snapshot: Record<string, unknown>,
  idSuffix: string,
): Record<string, unknown> {
  const template = api.createDocument({}).save()
  const sourceBody = (snapshot.body ?? {}) as {
    dataStream?: string
    paragraphs?: SourceParagraph[]
    textRuns?: SourceTextRun[]
  }
  const templateBody = (template.body ?? {}) as Record<string, unknown>

  const dataStream = withDocumentTerminator(sourceBody.dataStream ?? '')
  const sourceParagraphs = sourceBody.paragraphs ?? []
  const { paragraphs: styledParagraphs, textRuns } = withHeadingStyles(
    sourceParagraphs,
    dataStream,
    sourceBody.textRuns ?? [],
  )
  const paragraphs = styledParagraphs.map((para, index) => ({
    ...para,
    paragraphId: `${idSuffix}_para_${index}`,
  }))
  // 必须保证「至少一个分节」：分节是渲染器的页面单位，空数组等于没有页面，
  // 表现同样是工具栏正常、正文全白。不要用模板的数组去 map —— 模板可能是空的。
  const templateSections = (templateBody.sectionBreaks ?? []) as Record<string, unknown>[]
  const sections = [
    {
      ...(templateSections[0] ?? {}),
      sectionId: `${idSuffix}_section_0`,
      // 收尾 `\n` 的下标，与空文档模板的取值语义一致
      startIndex: Math.max(dataStream.length - 1, 0),
    },
  ]

  return {
    ...template,
    id: idSuffix,
    title: snapshot.title,
    body: {
      ...templateBody,
      dataStream,
      paragraphs,
      textRuns,
      sectionBreaks: sections,
    },
  }
}

export const DocEditor = React.forwardRef<DocEditorHandle, DocEditorProps>(
  function DocEditor({ snapshot, dark }, ref) {
    const hostRef = React.useRef<HTMLDivElement>(null);
    const apiRef = React.useRef<UniverAPI | null>(null);
    const univerRef = React.useRef<UniverInstance | null>(null);
    const docRef = React.useRef<UniverDocument | null>(null);
    const readyRef = React.useRef(false);
    const [error, setError] = React.useState<string | null>(null);
    const [ready, setReady] = React.useState(false);

    const initialSnapshot = React.useRef(snapshot);

    React.useImperativeHandle(
      ref,
      () => ({
        getSnapshot: () => {
          if (!readyRef.current) return null;
          // Docs 的 save 入口跨版本不稳定，按可靠度依次尝试
          const viaDoc = docRef.current;
          if (viaDoc) {
            try {
              return viaDoc.save();
            } catch {
              /* 继续走后备 */
            }
          }
          try {
            return apiRef.current?.getActiveDocument?.()?.save() ?? null;
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
      const disposedRefValue = `doc_${Date.now().toString(36)}`;

      /**
       * Univer 会往 container 里 append 自己的 canvas 与覆盖层。若直接挂到
       * React 渲染出来的 host 上，卸载时清空 host 就会和 React 的节点簿记
       * 打架——重建编辑器（切换产物/版本）时表现为整页报
       * 「Failed to execute 'removeChild' on 'Node'」，应用直接白屏。
       * 所以自建一个 React 不追踪的宿主挂进去，卸载时整块 remove 掉。
       */
      const mount = document.createElement('div');
      mount.className = 'h-full w-full';
      host.appendChild(mount);

      /** 等到容器有实际尺寸再建文档。
       *
       * 面板是在 AnimatePresence + Suspense 里挂载的，首帧容器宽度常常还是 0。
       * Univer 的文档视口在创建时定尺寸，且不像表格那样有 ResizeObserver 兜底
       * ——容器为 0 时会渲染成一张全透明画布，工具栏和字数统计却一切正常，
       * 极难排查。表格那边靠自身 ResizeObserver 自愈，文档这边必须自己等。
       */
      const waitForSize = () =>
        new Promise<void>((resolve) => {
          if (host.clientWidth > 0 && host.clientHeight > 0) return resolve();
          const observer = new ResizeObserver(() => {
            if (host.clientWidth > 0 && host.clientHeight > 0) {
              observer.disconnect();
              resolve();
            }
          });
          observer.observe(host);
          // 兜底：即使观察器一直不触发也不要永久挂住
          setTimeout(() => {
            observer.disconnect();
            resolve();
          }, 3000);
        });

      const bootstrap = async () => {
        try {
          await waitForSize();
          if (disposed) return;
          // 文档语言包分散在 @univerjs/docs-ui 等各包的 /locale 子路径下，
          // 漏合并会出现 docs.xxx 这种原始 key。
          // 注意不要直接 import('@univerjs/core')：presets 已 re-export 了它，
          // 两条路径并存会让渲染引擎加载两次（[redi] 警告，且第二次实例不参与渲染）。
          const [presetsCore, docsPreset, ...localeModules] = await Promise.all([
            import('@univerjs/presets'),
            import('@univerjs/preset-docs-core'),
            import('@univerjs/preset-docs-core/locales/zh-CN'),
            import('@univerjs/design/locale/zh-CN'),
            import('@univerjs/ui/locale/zh-CN'),
            import('@univerjs/docs-ui/locale/zh-CN'),
            import('@univerjs/sheets-ui/locale/zh-CN'),
            import('@univerjs/preset-docs-core/lib/index.css'),
          ]);
          if (disposed) return;

          const { createUniver, LocaleType, mergeLocales } = presetsCore;
          const { UniverDocsCorePreset } = docsPreset;
          const localePacks = localeModules
            .slice(0, 4)
            .map((module) => (module as { default?: unknown }).default ?? module);

          const created = (createUniver as unknown as CreateUniver)({
            locale: LocaleType.ZH_CN,
            locales: { [LocaleType.ZH_CN]: mergeLocales(...localePacks) },
            presets: [UniverDocsCorePreset({ container: mount })],
          });
          (window as unknown as Record<string, unknown>).__api = created.univerAPI;
          (window as unknown as Record<string, unknown>).__univer = created.univer;
          (window as unknown as Record<string, unknown>).__api = created.univerAPI;
          univerRef.current = created.univer;
          apiRef.current = created.univerAPI;

          const doc = created.univerAPI.createDocument(
            materializeDocument(created.univerAPI, initialSnapshot.current, disposedRefValue),
          );
          docRef.current = doc;
          readyRef.current = true;
          setReady(true);
        } catch (err) {
          if (!disposed) {
            setError(
              err instanceof Error ? `文档编辑器加载失败：${err.message}` : '文档编辑器加载失败',
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
        docRef.current = null;
        try {
          univerRef.current?.dispose();
        } catch {
          // 卸载期异常不影响后续渲染
        }
        univerRef.current = null;
        // 只移除自己建的宿主，不碰 React 渲染的节点
        mount.remove();
      };
      // 刻意只挂载一次：重建会丢失用户已做的编辑。
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

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
            正在加载文档编辑器…
          </div>
        )}
      </div>
    );
  },
);
