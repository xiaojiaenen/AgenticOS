# html-video 深度集成方案

## 一、项目概述

**html-video** 是一个本地视频生成引擎，用户描述想法 → AI 生成动画 HTML → Chromium 录制 → ffmpeg 编码 MP4。

**目标**：将 html-video 的核心功能用 Python 重写，作为 AgenticOS 的 `video` 智能体模式，完整保留原版所有功能。

---

## 二、html-video 原版功能清单

### 2.1 核心模块

| 模块 | 原版位置 | 功能 |
|------|----------|------|
| ContentGraph | `packages/content-graph/src/index.ts` | 多帧 storyboard 数据结构（节点+边），validate/topoSort |
| TemplateRegistry | `packages/core/src/registry.ts` | 扫描 templates/ 目录，解析 YAML manifest，语义搜索 |
| ProjectStore | `packages/core/src/registry.ts` | 项目 CRUD，JSON 文件持久化 |
| AssetStore | `packages/core/src/asset-store.ts` | 资源文件管理，content-addressed 存储 |
| ProjectOrchestrator | `packages/core/src/project.ts` | 项目生命周期编排（create→setTemplate→writeHtml→exportMp4） |
| HyperframesEngine | `packages/adapter-hyperframes/src/render.ts` | Chromium 录制 + ffmpeg 编码 |
| ErrorSystem | `packages/core/src/errors.ts` | 统一错误码 |

### 2.2 模板系统（23 个模板）

原版路径：`templates/`

| 模板 ID | 引擎 | 类别 | 说明 |
|---------|------|------|------|
| frame-swiss-grid | hyperframes | presentation | 瑞士风格网格布局 |
| frame-kinetic-type | hyperframes | social-shorts | 动感字体动画（多帧合成） |
| frame-data-chart-nyt | hyperframes | data-viz | 纽约时报风格数据图表 |
| frame-data-rollup | remotion | data-viz | 原生 Remotion 柱状图+数字滚动 |
| frame-glitch-title | hyperframes | social-shorts | 赛博朋克故障标题 |
| frame-product-promo | hyperframes | product-demo | 产品展示（多场景） |
| frame-product-promo-30s | hyperframes | product-demo | 30 秒产品宣传片 |
| frame-bold-poster | hyperframes | marketing | 70 年代欧洲海报风格 |
| frame-bold-signal | hyperframes | marketing | 大胆色块卡片 |
| frame-build-minimal | hyperframes | presentation | 奢华极简白空间 |
| frame-creative-voltage | hyperframes | social-shorts | 电蓝/暗色分割 |
| frame-decision-tree | hyperframes | explainer | 动画流程图 |
| frame-electric-studio | hyperframes | presentation | 双面板引用卡片 |
| frame-light-leak-cinema | hyperframes | documentary | 电影光晕+胶片颗粒 |
| frame-liquid-bg-hero | hyperframes | marketing | 流体渐变背景英雄卡 |
| frame-logo-outro | hyperframes | intro-outro | Logo 组装+光晕绽放 |
| frame-nyt-graph | hyperframes | data-viz | 印刷社论风格数据图 |
| frame-pentagram-stat | hyperframes | data-viz | 瑞士网格统计锚点 |
| frame-play-mode | hyperframes | social-shorts | 弹性动画 |
| frame-takram-organic | hyperframes | ambient | 软科技辐射节点图 |
| frame-vignelli | hyperframes | presentation | 红色强调粗字体 |
| frame-warm-grain | hyperframes | ambient | 奶油美学+颗粒纹理 |
| vfx-text-cursor | hyperframes | social-shorts | 打字机光标效果 |

每个模板包含：
- `template.html-video.yaml` — 元数据 manifest（id, name, tags, best_for, inputs schema, output capabilities, license）
- `source/index.html` — 自包含动画 HTML（CSS keyframes + GSAP CDN）
- 可选 `compositions/` — 多帧合成子场景

### 2.3 渲染管线（原版 `render.ts` 完整流程）

```
1. Playwright 启动 Chromium headless（recordVideo 录制）
2. 注入 CSS 冻结样式（animation-play-state: paused）
3. 加载 HTML（file:// URL，domcontentloaded）
4. 等待 Web Fonts（stylesheet 加载 → fonts.load() → fonts.ready + 2 rAF）
5. 探测动画时长（CSS animations + GSAP globalTimeline，忽略 infinite）
6. 多帧合成：注入 composition player，__hvPlayAll() 驱动所有 timeline
7. 解冻动画（移除冻结样式）
8. 录制指定时长（250ms 间隔进度回调）
9. 关闭 context，得到 .webm
10. ffmpeg 编码 webm → MP4（libx264, crf20, yuv420p, +faststart）
11. 修剪 dead lead-in（-ss seek）
12. explicit 模式：tpad 填充尾部到精确时长
```

### 2.4 ContentGraph 数据结构

```typescript
ContentGraph {
  schemaVersion: 1
  intent: 'single-frame' | 'explainer' | 'data-viz' | 'promo' | 'comparison' | 'other'
  synopsis?: string
  nodes: Node[]        // entity | data | text 三种类型
  edges: Edge[]        // sequence | contrast | dependency 三种关系
}
```

算法：
- `validate(graph)` — 检测重复 ID、未知边端点、自环、依赖边环路（DFS 着色法）
- `topoSort(graph)` — Kahn 拓扑排序，dependency 边硬约束，sequence 边软偏好
- `totalDurationSec(graph)` — 沿 topo 顺序累加 durationSec（默认 3s/帧）

### 2.5 项目生命周期

```
create(name, intent)           → status: draft
addAsset(content/type)         → 添加资源
setTemplate(templateId)        → 选择模板
writeContentGraph(graph)       → 写入多帧 storyboard
writeFrameHtml(nodeId, html)   → 为每帧写入 HTML
exportMp4(resolution, fps)     → 渲染导出 MP4 → status: rendered
```

单帧快速路径：`writePreviewHtmlRaw(html)` → `exportMp4()`

### 2.6 配乐系统

- MiniMax API 生成背景音乐 + 旁白
- ffmpeg 混音：music -18dB（背景），narration 0dB（前景）
- 支持 fade in/out
- `-shortest` 对齐视频时长

### 2.7 Agent 对话流程（原版 studio-server.ts）

```
用户消息 → detectPhase() 判断对话阶段
  → opener/content/style/format/confirm/generate/iterate/restyle
  → buildHtmlGenerationPrompt() 构建 prompt
  → 单帧：一次 agent 调用，extractHtmlDocument() 提取 HTML
  → 多帧：runSplitMultiFrameGenerate()
      Step 1: agent 生成 content-graph JSON
      Step 2: 每个节点一次 agent 调用，生成帧 HTML
  → 写入磁盘，SSE 推送进度
```

---

## 三、Python 重写架构

### 3.1 目录结构

```
backend/app/services/video/
├── __init__.py                  # 对外暴露 get_video_orchestrator()
├── types.py                     # Pydantic 数据模型（完整对标原版 TS 类型）
├── errors.py                    # HtmlVideoError 异常类
├── content_graph.py             # ContentGraph + validate + topoSort
├── template_registry.py         # 模板扫描、搜索、解析
├── project_store.py             # 项目 CRUD（JSON 文件持久化）
├── asset_store.py               # 资源文件管理（content-addressed）
├── engine.py                    # Chromium 录制 + ffmpeg 编码
├── orchestrator.py              # 项目生命周期编排
├── render_config.py             # 渲染配置
└── bridge.py                    # 对外统一接口（单例管理）

backend/app/tools/
└── video_tools.py               # wuwei 工具注册

backend/app/prompts.py           # VIDEO_SYSTEM_PROMPT

backend/templates/video/         # 23 个模板目录（原样复制）
```

### 3.2 模块详细设计

#### 3.2.1 `types.py` — 数据模型

完整对标 `packages/core/src/types/index.ts`：

```python
from enum import Enum
from typing import Optional, Any, Literal
from pydantic import BaseModel

# --- 枚举 ---
class NodeKind(str, Enum):
    ENTITY = "entity"
    DATA = "data"
    TEXT = "text"

class EdgeKind(str, Enum):
    SEQUENCE = "sequence"
    CONTRAST = "contrast"
    DEPENDENCY = "dependency"

class ProjectStatus(str, Enum):
    DRAFT = "draft"
    PREVIEWED = "previewed"
    RENDERED = "rendered"

class AssetType(str, Enum):
    IMAGE = "image"
    TEXT = "text"
    DATA = "data"
    AUDIO = "audio"
    VIDEO = "video"
    REFERENCE_LINK = "reference-link"

# --- ContentGraph 节点 ---
class BaseNode(BaseModel):
    id: str
    kind: NodeKind
    label: Optional[str] = None
    frame_intent: Optional[str] = None
    duration_sec: float = 3.0

class EntityNode(BaseNode):
    kind: Literal[NodeKind.ENTITY] = NodeKind.ENTITY
    props: dict[str, Any] = {}

class DataNode(BaseNode):
    kind: Literal[NodeKind.DATA] = NodeKind.DATA
    data: Any = None

class TextNode(BaseNode):
    kind: Literal[NodeKind.TEXT] = NodeKind.TEXT
    text: str = ""

Node = EntityNode | DataNode | TextNode

# --- ContentGraph 边 ---
class GraphEdge(BaseModel):
    from_node: str  # 原版字段名 "from"
    to_node: str    # 原版字段名 "to"
    kind: EdgeKind
    reason: Optional[str] = None

# --- ContentGraph ---
class ContentGraph(BaseModel):
    schema_version: Literal[1] = 1
    intent: Literal["single-frame", "explainer", "data-viz", "promo", "comparison", "other"]
    synopsis: Optional[str] = None
    nodes: list[Node]
    edges: list[GraphEdge]

# --- 验证结果 ---
class GraphValidationError(BaseModel):
    code: str  # "duplicate-node-id" | "edge-from-unknown-node" | "self-edge" | "cycle" | ...
    message: str
    ref: Optional[str] = None

class GraphValidationResult(BaseModel):
    ok: bool
    errors: list[GraphValidationError]
    warnings: list[GraphValidationError]

# --- 资源 ---
class AssetMetadata(BaseModel):
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_sec: Optional[float] = None
    user_caption: Optional[str] = None

class Asset(BaseModel):
    id: str
    type: AssetType
    path: Optional[str] = None
    content: Optional[str] = None
    metadata: AssetMetadata = AssetMetadata()
    user_tags: list[str] = []

# --- 用户偏好 ---
class UserPreferences(BaseModel):
    aspect: Optional[str] = None
    duration_target_sec: Optional[float] = None
    format: Optional[str] = "mp4"
    resolution: Optional[dict] = None  # {"width": 1920, "height": 1080}
    fps: Optional[int] = None
    mood: Optional[str] = None
    brand_colors: Optional[list[str]] = None
    font_families: Optional[list[str]] = None
    language: Optional[str] = None
    commercial: Optional[bool] = None

# --- 帧记录 ---
class FrameRecord(BaseModel):
    graph_node_id: str
    html_path: str
    duration_sec: float
    poster_path: Optional[str] = None
    order: int
    engine: Optional[str] = None
    native_template_id: Optional[str] = None
    data: Any = None
    preview_mp4_path: Optional[str] = None

# --- 配乐 ---
class ProjectSoundtrack(BaseModel):
    music_asset_id: Optional[str] = None
    narration_asset_id: Optional[str] = None
    music_volume_db: float = -18
    narration_volume_db: float = 0
    music_prompt: Optional[str] = None
    narration_text: Optional[str] = None
    narration_by_frame: Optional[dict[str, str]] = None
    fade_in_sec: Optional[float] = None
    fade_out_sec: Optional[float] = None

# --- 项目 ---
class Project(BaseModel):
    id: str
    name: str
    intent: Optional[str] = None
    assets: list[Asset] = []
    template_id: Optional[str] = None
    variables: dict[str, Any] = {}
    preferences: UserPreferences = UserPreferences()
    status: ProjectStatus = ProjectStatus.DRAFT
    last_preview_html_path: Optional[str] = None
    last_preview_poster_path: Optional[str] = None
    last_output_mp4_path: Optional[str] = None
    exports: list[dict] = []
    content_graph_path: Optional[str] = None
    frames: list[FrameRecord] = []
    soundtrack: Optional[ProjectSoundtrack] = None
    created_at: str = ""
    updated_at: str = ""

# --- 渲染配置 ---
class RenderConfig(BaseModel):
    format: str = "mp4"
    resolution: dict = {"width": 1920, "height": 1080}
    fps: int = 30
    duration: float | Literal["auto"] = "auto"
    duration_mode: Literal["explicit", "auto"] = "auto"
    output_path: str = ""
    alpha: bool = False
    quality: str = "medium"

class RenderOutput(BaseModel):
    output_path: str
    duration_sec: float
    file_size_bytes: int
    resolution: dict
    fps: int
    rendered_frames: int
    render_wall_clock_sec: float
    engine_version: str

# --- 模板元数据 ---
class LicenseInfo(BaseModel):
    spdx: str
    attribution_required: bool
    redistribution_allowed: bool
    commercial_use: bool
    notes: Optional[str] = None

class OutputCapabilities(BaseModel):
    formats: list[str]
    default_format: str
    resolution: dict
    fps: dict
    duration: dict
    alpha: bool
    audio: dict

class TemplateMetadata(BaseModel):
    spec_version: int = 1
    id: str
    name: str
    description: str
    engine: str
    engine_version: str
    source_entry: str
    native: Optional[dict] = None
    category: str
    subcategory: Optional[str] = None
    tags: list[str] = []
    best_for: list[str] = []
    not_for: list[str] = []
    output: OutputCapabilities
    inputs: dict
    license: LicenseInfo
    author: dict
    version: str
    preview: dict
    # 内部字段
    _dir: Optional[str] = None  # 模板目录绝对路径
```

#### 3.2.2 `errors.py` — 错误系统

完整对标 `packages/core/src/errors.ts`：

```python
class ErrorCode(str, Enum):
    ENGINE_NOT_INSTALLED = "engine-not-installed"
    ENGINE_NOT_REGISTERED = "engine-not-registered"
    TEMPLATE_INVALID = "template-invalid"
    TEMPLATE_NOT_FOUND = "template-not-found"
    RENDER_FAILED = "render-failed"
    RENDER_TIMEOUT = "render-timeout"
    OUTPUT_CORRUPT = "output-corrupt"
    DISK_FULL = "disk-full"
    CANCELLED = "cancelled"
    ASSET_NOT_FOUND = "asset-not-found"
    PROJECT_NOT_FOUND = "project-not-found"
    INVALID_INPUT = "invalid-input"

class HtmlVideoError(Exception):
    def __init__(self, code: ErrorCode, message: str, retryable: bool = False, context: dict = None):
        self.code = code
        self.message = message
        self.retryable = retryable
        self.context = context or {}
        super().__init__(message)
```

#### 3.2.3 `content_graph.py` — 多帧 Storyboard

完整对标 `packages/content-graph/src/index.ts`，三个核心函数：

```python
DEFAULT_FRAME_DURATION_SEC = 3.0

def validate(graph: ContentGraph) -> GraphValidationResult:
    """
    校验 ContentGraph：
    1. 空图检测
    2. 重复节点 ID
    3. 无效 kind
    4. 自环边
    5. 边端点引用未知节点
    6. 依赖边环路检测（DFS 着色法：WHITE→GRAY→BLACK）
    """
    ...

def topo_sort(graph: ContentGraph) -> list[str]:
    """
    Kahn 拓扑排序：
    - 只有 dependency 边约束顺序
    - sequence 边作为软偏好（tiebreaker）
    - 同级节点按原始数组顺序稳定排序
    - 返回节点 ID 列表（播放顺序）
    - 如果存在环，抛出异常
    """
    ...

def total_duration_sec(graph: ContentGraph) -> float:
    """沿 topo 顺序累加每帧 duration_sec（默认 3s）"""
    ...

def get_node(graph: ContentGraph, node_id: str) -> Optional[Node]:
    """按 ID 查找节点"""
    ...
```

#### 3.2.4 `template_registry.py` — 模板管理

完整对标 `packages/core/src/registry.ts` TemplateRegistry：

```python
class TemplateRegistry:
    def __init__(self):
        self._templates: dict[str, TemplateMetadata] = {}

    async def scan(self, root_dir: str) -> list[TemplateMetadata]:
        """
        扫描 templates/ 下每个子目录：
        1. 检查 template.html-video.yaml 是否存在
        2. 解析 YAML 为 TemplateMetadata
        3. 设置 _dir 为目录绝对路径
        4. 存入 _templates 字典（key = meta.id）
        """
        ...

    def get(self, template_id: str) -> TemplateMetadata:
        """获取模板，不存在抛出 HtmlVideoError('template-not-found')"""
        ...

    def has(self, template_id: str) -> bool: ...

    def list_all(self) -> list[TemplateMetadata]: ...

    def search(
        self,
        intent: str = "",
        aspect: str = None,
        license_allow: list[str] = None,
        engines_available: list[str] = None,
        top: int = 5,
    ) -> list[dict]:
        """
        语义搜索（完全对标原版算法）：
        1. 分词 intent（按非字母数字分割，过滤长度<=2）
        2. 构建 haystack = tags + best_for + name + description + category + subcategory
        3. 匹配 token → score += matched_count * 0.2
        4. aspect 匹配 → +0.15，不匹配 → -0.1
        5. license/engine 硬过滤
        6. 按 score 降序返回 top N
        """
        ...
```

#### 3.2.5 `project_store.py` — 项目持久化

完整对标 `packages/core/src/registry.ts` ProjectStore：

```python
class ProjectStore:
    """JSON 文件持久化: {project_root}/.html-video/projects/{id}/project.json"""

    def __init__(self, project_root: str):
        self._project_root = project_root

    async def ensure_dir(self, project_id: str) -> str:
        """确保项目目录和 assets/ 子目录存在，返回绝对路径"""
        ...

    async def save(self, project: Project) -> None:
        """写入 project.json，自动更新 updated_at"""
        ...

    async def load(self, project_id: str) -> Project:
        """加载项目，不存在抛出 HtmlVideoError('project-not-found')"""
        ...

    async def list_all(self) -> list[Project]:
        """列出所有项目，按 updated_at 降序"""
        ...

    async def remove(self, project_id: str) -> None:
        """删除项目目录（rm -rf）"""
        ...
```

#### 3.2.6 `asset_store.py` — 资源管理

完整对标 `packages/core/src/asset-store.ts`：

```python
class AssetStore:
    """Content-addressed 资源存储，按项目隔离"""

    def __init__(self, project_root: str): ...

    async def add_file_asset(
        self, project_id: str, source_path: str,
        user_tags: list[str] = None, user_caption: str = None,
    ) -> Asset:
        """
        1. 计算文件 SHA1 作为 ID
        2. 猜测 MIME 类型（按扩展名映射）
        3. 复制到 assets/{id}{ext}（已存在则跳过）
        4. 返回 Asset
        """
        ...

    async def add_inline_asset(
        self, project_id: str, content: str, type: str,
        user_tags: list[str] = None, user_caption: str = None,
    ) -> Asset:
        """内联文本/数据资源，SHA1(content) 作为 ID"""
        ...

    async def add_buffer_asset(
        self, project_id: str, data: bytes, ext: str,
        user_tags: list[str] = None, user_caption: str = None,
    ) -> Asset:
        """原始字节资源（如 MiniMax 生成的 MP3）"""
        ...

    @staticmethod
    def guess_mime(file_path: str) -> dict:
        """按扩展名猜测 MIME 类型和 AssetType"""
        ...
```

#### 3.2.7 `engine.py` — 渲染引擎（核心）

完整对标 `packages/adapter-hyperframes/src/render.ts`，这是最关键的部分：

```python
class HyperframesEngine:
    """Chromium 录制 + ffmpeg 编码引擎"""

    async def render(
        self,
        html_path: str,
        config: RenderConfig,
        work_dir: str,
        on_progress: Callable = None,
        signal: asyncio.Event = None,
    ) -> RenderOutput:
        """
        完整渲染管线（10 步，与原版完全一致）：

        Step 1: 准备输出目录
        Step 2: Playwright 启动 Chromium headless
            - args: ['--no-sandbox', '--disable-blink-features=AutomationControlled']
            - recordVideo: {dir: tmpDir, size: {width, height}}
        Step 3: 注入动画冻结 CSS
            - addInitScript: '* { animation-play-state: paused !important; }'
            - 注册 __hvUnfreeze() 全局函数
        Step 4: 多帧合成处理（prepare_source_html）
            - 检测 data-composition-src 属性
            - 读取 composition 文件
            - 注入 window.__COMPOSITIONS__ map
            - 注入 composition player（reexec scripts + mountOne + __hvPlayAll）
        Step 5: 加载 HTML
            - goto(file://, wait_until='domcontentloaded')
        Step 6: 等待 Web Fonts
            - 等待所有 <link rel="stylesheet"> 加载
            - fonts.load() 强制下载所有 @font-face
            - fonts.ready + 2 rAF
            - 硬上限 8s
        Step 7: 探测动画时长
            - CSS animations: 遍历所有元素，解析 animationDuration/animationDelay/animationIterationCount
            - GSAP: globalTimeline.getChildren()，跳过 repeat=-1
            - 取 max + 0.4s settle，cap 30s
            - duration_mode != 'explicit' 时才 extend
        Step 8: 驱动多帧合成
            - 调用 window.__hvPlayAll() 从 frame 0 开始播放
        Step 9: 解冻动画 + 录制
            - 调用 __hvUnfreeze()
            - 循环等待 totalDuration，250ms 间隔回调进度
        Step 10: 关闭 + ffmpeg 编码
            - 关闭 context，得到 .webm
            - ffmpeg: -ss 修剪 lead-in, -vf tpad (explicit), -t 精确时长
            - 参数: libx264, yuv420p, preset medium, crf 20, +faststart
        """
        ...

    async def _prepare_source_html(self, source_path: str) -> dict:
        """
        多帧合成 HTML 预处理（对标原版 prepareSourceHtml）：
        1. 读取源 HTML
        2. 检测 data-composition-src 属性
        3. 读取每个 composition 文件
        4. JSON 序列义为 window.__COMPOSITIONS__（转义 </）
        5. 注入 <head> script: __timelines + __COMPOSITIONS__
        6. 注入 composition player script（boot + mountOne + reexec + __hvPlayAll）
        7. 替换 __VIDEO_DURATION__ 和 __VIDEO_SRC__ 占位符
        8. 写入临时 .html 文件
        9. 返回 {load_path, cleanup_fn}
        """
        ...

    async def _wait_for_fonts(self, page) -> None:
        """
        等待 Web Fonts（对标原版 font wait 逻辑）：
        1. 等待所有 <link rel="stylesheet"> load/error
        2. fonts.forEach(face => face.load()) 强制下载
        3. await fonts.ready
        4. 2 rAF 确保布局稳定
        5. 8s 硬上限
        """
        ...

    async def _probe_animation_duration(self, page) -> float:
        """
        探测动画时长（对标原版 animMs 探测）：
        CSS: 遍历所有元素 getComputedStyle，解析 animationDuration/animationDelay/animationIterationCount
        GSAP: globalTimeline.getChildren(true, true, true)，跳过 repeat()===-1
        返回 max(cssMs, gsapMs) / 1000 + 0.4，cap 30
        """
        ...

    async def _run_ffmpeg(self, args: list[str]) -> None:
        """
        执行 ffmpeg（对标原版 runFfmpeg）：
        - asyncio.create_subprocess_exec('ffmpeg', *args)
        - 收集 stderr
        - ENOENT → 友好提示 "brew install ffmpeg"
        - exit code != 0 → 抛出 HtmlVideoError('render-failed')
        """
        ...

    async def _concat_frames_ffmpeg(
        self, frame_mp4s: list[str], output_path: str, work_dir: str,
        reencode: bool = False, fps: int = 60,
    ) -> None:
        """
        多帧 MP4 合成（对标原版 concatFramesWithFfmpeg）：
        - 单引擎: concat demuxer + -c copy（快速，不重编码）
        - 混合引擎: concat filter + 重编码（避免 PTS 累积问题）
        """
        ...

    async def _mux_audio_ffmpeg(
        self, video_path: str, output_path: str,
        music_path: str = None, narration_path: str = None,
        music_volume_db: float = -18, narration_volume_db: float = 0,
        fade_in_sec: float = 0, fade_out_sec: float = 0,
        video_duration_sec: float = None,
    ) -> None:
        """
        音频混音（对标原版 muxAudioWithFfmpeg）：
        - 视频 stream copy（不重编码）
        - 音频编码 AAC 192k
        - music: volume + fade in/out
        - narration: volume
        - amix 混合
        - -shortest 对齐视频时长
        """
        ...
```

#### 3.2.8 `orchestrator.py` — 项目编排

完整对标 `packages/core/src/project.ts` ProjectOrchestrator：

```python
class ProjectOrchestrator:
    def __init__(
        self,
        project_root: str,
        engines: dict[str, HyperframesEngine],
        templates: TemplateRegistry,
        projects: ProjectStore,
        assets: AssetStore,
    ): ...

    # --- CRUD ---
    async def create(self, name: str, intent: str = "") -> Project:
        """创建项目，ID = proj_{uuid[:12]}，status=draft"""
        ...

    async def list_all(self) -> list[Project]: ...
    async def load(self, project_id: str) -> Project: ...
    async def remove(self, project_id: str) -> None: ...

    # --- 资源操作 ---
    async def add_inline_asset(self, project_id: str, content: str, type: str) -> Project: ...
    async def add_buffer_asset(self, project_id: str, data: bytes, ext: str) -> dict: ...
    async def remove_asset(self, project_id: str, asset_id: str) -> Project: ...

    # --- 模板/变量 ---
    async def set_template(self, project_id: str, template_id: str) -> Project:
        """设置模板，重置 variables，降级 status 为 draft"""
        ...

    async def set_variables(self, project_id: str, variables: dict) -> Project: ...
    async def set_variable(self, project_id: str, key: str, value: Any) -> Project: ...

    # --- 内容写入 ---
    async def write_preview_html(self, project_id: str, html: str) -> dict:
        """
        单帧快速路径：
        1. 写入 preview.html
        2. 如果没有 frames[]，清除 contentGraphPath
        3. status → previewed
        """
        ...

    async def write_content_graph(self, project_id: str, graph: ContentGraph, preserve_frames: bool = False) -> dict:
        """
        写入多帧 storyboard：
        1. validate(graph) 校验
        2. 写入 content-graph.json
        3. 创建 frames/ 目录
        4. preserve_frames=True: 保留已有帧，只更新 durationSec
        5. preserve_frames=False: 清空 frames[]
        """
        ...

    async def write_frame_html(self, project_id: str, graph_node_id: str, html: str) -> dict:
        """
        写入单帧 HTML：
        1. 读取 content-graph，topo_sort
        2. 文件名: {order:02d}-{safe_id}.html
        3. 更新 frames[]（按 order 排序）
        4. 第一帧成为 project preview
        5. status → previewed
        """
        ...

    # --- 渲染导出 ---
    async def export_mp4(
        self,
        project_id: str,
        output_path: str = None,
        resolution: dict = None,
        fps: int = 60,
        on_progress: Callable = None,
        signal: asyncio.Event = None,
    ) -> dict:
        """
        核心渲染流程（与原版完全一致）：

        多帧路径（frames[] 非空）：
        1. 按 order 排序帧
        2. 检测是否混合引擎（reencode 标志）
        3. 遍历每帧:
           - resolve_frame_template_ref() 解析引擎+模板
           - engine.render(frame_html, config) → 帧 MP4
        4. concat_frames_ffmpeg() 合并所有帧
        5. apply_soundtrack() 混音（如有）
        6. status → rendered

        单帧快速路径：
        1. 读取 template
        2. engine.render(template_html, config) → MP4
        3. apply_soundtrack()
        4. status → rendered
        """
        ...

    async def apply_soundtrack(self, project: Project, output_path: str, video_duration_sec: float = None) -> None:
        """
        配乐混音：
        1. 查找 music_asset_id 和 narration_asset_id 对应的文件路径
        2. 默认 fade_out = min(1.5, video_duration/3)
        3. 调用 engine._mux_audio_ffmpeg()
        """
        ...
```

---

## 四、AgenticOS 集成

### 4.1 后端集成（6 个触点）

#### 触点 1：模式注册 — `tool_config_service.py`

```python
AGENT_MODES["video"] = {
    "label": "视频",
    "description": "智能视频生成，将想法转化为动画MP4视频",
}
```

正则新增 `video`。

#### 触点 2：系统提示 — `prompts.py`

```python
VIDEO_SYSTEM_PROMPT = """你是视频创作助手，帮助用户将想法转化为高质量动画视频。

## 你的能力
- 搜索并选择 23 种专业视频模板（数据可视化、标题动画、产品展示、解说视频等）
- 规划多帧 storyboard（content-graph），决定帧数、顺序、时长
- 为每帧生成自包含的动画 HTML（CSS keyframes + GSAP）
- 渲染导出为 MP4，可选添加 AI 配乐和旁白

## 工作流程
1. 理解用户意图 → video_search_templates 搜索合适模板
2. 创建项目 → video_create_project
3. 设置模板 → video_set_template
4. 规划内容 → video_write_content_graph（多帧）或 video_write_preview_html（单帧）
5. 为每帧生成 HTML → video_write_frame_html（循环）
6. 渲染导出 → video_export_mp4

## HTML 生成规则
- 使用 CSS keyframes 或 GSAP 做动画
- 自包含：所有样式和脚本内联，不依赖外部资源（除 Google Fonts 和 GSAP CDN）
- 匹配模板风格：遵循模板的 CSS 变量和布局约定

## content-graph 格式
{
  "schemaVersion": 1,
  "intent": "explainer",
  "synopsis": "简要描述",
  "nodes": [
    {"id": "intro", "kind": "text", "text": "欢迎", "durationSec": 3},
    {"id": "data", "kind": "data", "data": {"items": [...]}, "durationSec": 5}
  ],
  "edges": [
    {"from": "intro", "to": "data", "kind": "sequence"}
  ]
}
"""
```

#### 触点 3：Agent 配置 — `agent_profile_service.py`

```python
BUILTIN_AGENT_PROFILES["video"] = {
    "name": "视频创作",
    "avatar": "🎬",
    "description": "智能视频生成",
    "response_mode": "video",
    "max_steps": 25,
    "system_prompt": VIDEO_SYSTEM_PROMPT,
}
```

#### 触点 4：工具模块 — `video_tools.py`

```python
def register_video_tools(registry: ToolRegistry):
    orchestrator = get_video_orchestrator()

    @registry.register(name="video_search_templates", ...)
    async def video_search_templates(intent: str, top_n: int = 5):
        return orchestrator.templates.search(intent, top=top_n)

    @registry.register(name="video_list_templates", ...)
    async def video_list_templates():
        return [t.model_dump() for t in orchestrator.templates.list_all()]

    @registry.register(name="video_get_template", ...)
    async def video_get_template(template_id: str):
        return orchestrator.templates.get(template_id).model_dump()

    @registry.register(name="video_create_project", ...)
    async def video_create_project(name: str, intent: str = ""):
        project = await orchestrator.create(name, intent)
        return {"project_id": project.id}

    @registry.register(name="video_set_template", ...)
    async def video_set_template(project_id: str, template_id: str):
        await orchestrator.set_template(project_id, template_id)
        return {"ok": True}

    @registry.register(name="video_set_variables", ...)
    async def video_set_variables(project_id: str, variables: dict):
        await orchestrator.set_variables(project_id, variables)
        return {"ok": True}

    @registry.register(name="video_write_content_graph", ...)
    async def video_write_content_graph(project_id: str, graph: dict):
        cg = ContentGraph(**graph)
        result = validate(cg)
        if not result.ok:
            return {"ok": False, "errors": [e.model_dump() for e in result.errors]}
        await orchestrator.write_content_graph(project_id, cg)
        return {"ok": True}

    @registry.register(name="video_write_frame_html", ...)
    async def video_write_frame_html(project_id: str, node_id: str, html: str):
        await orchestrator.write_frame_html(project_id, node_id, html)
        return {"ok": True}

    @registry.register(name="video_write_preview_html", ...)
    async def video_write_preview_html(project_id: str, html: str):
        await orchestrator.write_preview_html(project_id, html)
        return {"ok": True}

    @registry.register(name="video_export_mp4", ...)
    async def video_export_mp4(project_id: str, resolution: str = "1920x1080", fps: int = 30):
        w, h = resolution.split("x")
        result = await orchestrator.export_mp4(
            project_id,
            resolution={"width": int(w), "height": int(h)},
            fps=fps,
            on_progress=lambda pct, stage: emit_progress(pct, stage),
        )
        return {"output_path": result["output_path"], "duration_sec": result["duration_sec"]}
```

#### 触点 5：Agent 编排 — `agent_service.py`

```python
# _build_tool_registry()
if profile.response_mode == "video":
    register_video_tools(registry)

# stream_chat() 中 video 模式特殊处理
if profile.response_mode == "video":
    # 注入模板目录信息
    template_catalog = get_video_orchestrator().templates.list_all()
    enriched_msg = _inject_video_template_catalog(message, template_catalog)

    # text_delta 收集不转发（同 PPT 模式）
    # done 事件时渲染
    yield _format_sse("run_status", {"phase": "rendering_video"})
    result = await orchestrator.export_mp4(project_id, ...)
    yield _format_sse("artifact_ready", {
        "type": "video",
        "artifactId": artifact_id,
        "videoUrl": f"/api/v1/videos/{artifact_id}/file",
        "title": title,
        "duration": result["duration_sec"],
    })
```

#### 触点 6：数据库 + API

```python
# models.py
class VideoArtifactModel(Base):
    __tablename__ = "video_artifacts"
    id: str
    session_id: str
    user_id: int
    project_id: str
    title: str
    video_path: str
    thumbnail_path: str
    duration_sec: float
    resolution: str
    fps: int
    template_id: str
    has_soundtrack: bool
    file_size_bytes: int
    created_at: datetime

# endpoints/video.py
@router.get("/videos/{artifact_id}/file")
async def get_video_file(artifact_id: str):
    """返回 MP4，支持 Range 请求"""

@router.get("/videos/{artifact_id}/thumbnail")
async def get_video_thumbnail(artifact_id: str):
    """返回首帧缩略图"""
```

### 4.2 前端集成

#### 类型 — `types.ts`

```typescript
// Artifact 联合类型新增：
| {
    language: 'video'
    artifactId: string
    videoUrl: string
    title: string
    duration?: number
    resolution?: string
  }
```

#### 新面板 — `VideoArtifactPanel.tsx`

- `<video>` 播放 MP4
- 工具栏：下载、全屏、重新生成
- 元信息：时长、分辨率、模板
- 动画入场（沿用 PptArtifactPanel）

#### 路由 — `ChatArtifactArea.tsx`

```tsx
case 'video':
  return <VideoArtifactPanel artifact={artifact} />
```

---

## 五、模板复用

23 个模板目录**原样复制**：

```bash
cp -r /Users/xiaojia/code/html-video/templates/ \
      /Users/xiaojia/code/AgenticOS/backend/templates/video/
```

模板是浏览器端 HTML/CSS/GSAP 代码，Python 只负责：
1. 解析 YAML manifest（`template_registry.py`）
2. 读取 HTML 文件路径（`engine.py`）
3. 注入变量和 composition player（`engine.py`）

---

## 六、依赖

### Python 依赖（新增）

```
playwright>=1.49.0    # Chromium 录制
pyyaml                # 模板 YAML 解析
```

### 系统依赖

| 依赖 | 版本 | 安装 |
|------|------|------|
| ffmpeg | >=5 | `brew install ffmpeg` |
| Chromium | Playwright 内置 | `playwright install chromium` |

### 不需要的依赖

- 不需要 Node.js
- 不需要 pnpm
- 不需要 Remotion（frame-data-rollup 模板暂时跳过，它是唯一的 native Remotion 模板）

---

## 七、工作量评估

| 模块 | 代码量 | 天数 |
|------|--------|------|
| types.py | ~250 行 | 0.5 |
| errors.py | ~40 行 | 0.5 |
| content_graph.py | ~150 行 | 0.5 |
| template_registry.py | ~120 行 | 0.5 |
| project_store.py | ~100 行 | 0.5 |
| asset_store.py | ~120 行 | 0.5 |
| engine.py | ~400 行 | 2 |
| orchestrator.py | ~350 行 | 1.5 |
| video_tools.py | ~200 行 | 0.5 |
| 系统提示 + 模式注册 | ~60 行 | 0.5 |
| 数据库 + API | ~150 行 | 0.5 |
| 前端 VideoArtifactPanel | ~200 行 | 1 |
| 模板复制 + 测试 | — | 2 |
| **合计** | **~2100 行** | **~10 天** |

---

## 八、实现顺序

**Phase 1（3 天）：核心引擎**
1. types.py + errors.py — 数据模型
2. content_graph.py — validate + topoSort
3. template_registry.py — 模板扫描 + 搜索
4. project_store.py + asset_store.py — 持久化
5. engine.py — Chromium 录制 + ffmpeg 编码

**Phase 2（2 天）：编排 + 工具**
1. orchestrator.py — 项目生命周期
2. video_tools.py — wuwei 工具注册
3. prompts.py — 系统提示
4. tool_config_service.py + agent_profile_service.py — 模式注册

**Phase 3（2 天）：Agent 集成**
1. agent_service.py — video 模式编排
2. schemas/agent.py — response_mode 正则
3. 模板复制到 backend/templates/video/
4. 联调测试

**Phase 4（2 天）：前端 + 收尾**
1. types.ts — Artifact 类型
2. VideoArtifactPanel.tsx
3. ChatArtifactArea.tsx + agentService.ts
4. 数据库模型 + API 端点
5. 缩略图生成 + 错误处理

---

## 九、风险

| 风险 | 应对 |
|------|------|
| frame-data-rollup 是 Remotion 原生模板 | Phase 1 跳过，只支持 hyperframes 模板（22 个） |
| Chromium 内存占用 | 限制并发渲染数（2-3），队列排队 |
| ffmpeg 不可用 | 启动时检测，不可用则报错提示安装 |
| 字体加载超时 | 8s 硬上限，降级到系统字体 |
| 动画时长探测失败 | 降级到请求的 duration 或默认 5s |
