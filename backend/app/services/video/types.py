"""
Video 智能体数据模型
完整对标 html-video 原版 TypeScript 类型定义
"""

from enum import Enum
from typing import Optional, Any, Literal, Union
from pydantic import BaseModel, Field


# --- 枚举 ---

class NodeKind(str, Enum):
    """ContentGraph 节点类型"""
    ENTITY = "entity"
    DATA = "data"
    TEXT = "text"


class EdgeKind(str, Enum):
    """ContentGraph 边类型"""
    SEQUENCE = "sequence"
    CONTRAST = "contrast"
    DEPENDENCY = "dependency"


class ProjectStatus(str, Enum):
    """项目状态"""
    DRAFT = "draft"
    PREVIEWED = "previewed"
    RENDERED = "rendered"


class AssetType(str, Enum):
    """资源类型"""
    IMAGE = "image"
    TEXT = "text"
    DATA = "data"
    AUDIO = "audio"
    VIDEO = "video"
    REFERENCE_LINK = "reference-link"


class OutputFormat(str, Enum):
    """输出格式"""
    MP4 = "mp4"
    WEBM = "webm"
    WEBM_ALPHA = "webm-alpha"
    GIF = "gif"
    PNG_SEQUENCE = "png-sequence"
    APNG = "apng"


# --- ContentGraph 节点 ---

class BaseNode(BaseModel):
    """节点基类"""
    id: str
    kind: NodeKind
    label: Optional[str] = None
    frame_intent: Optional[str] = Field(None, alias="frameIntent")
    duration_sec: float = Field(3.0, alias="durationSec")

    class Config:
        populate_by_name = True


class EntityNode(BaseNode):
    """实体节点 - 品牌实体，自由属性"""
    kind: Literal[NodeKind.ENTITY] = NodeKind.ENTITY
    props: dict[str, Any] = {}


class DataNode(BaseNode):
    """数据节点 - 可视化数据点"""
    kind: Literal[NodeKind.DATA] = NodeKind.DATA
    data: Any = None


class TextNode(BaseNode):
    """文本节点 - 标题/引言/说明"""
    kind: Literal[NodeKind.TEXT] = NodeKind.TEXT
    text: str = ""


Node = Union[EntityNode, DataNode, TextNode]


# --- ContentGraph 边 ---

class GraphEdge(BaseModel):
    """图边"""
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    kind: EdgeKind
    reason: Optional[str] = None

    class Config:
        populate_by_name = True


# --- ContentGraph ---

class ContentGraph(BaseModel):
    """内容图 - 多帧 storyboard 数据结构"""
    schema_version: Literal[1] = Field(1, alias="schemaVersion")
    intent: Literal["single-frame", "explainer", "data-viz", "promo", "comparison", "other"]
    synopsis: Optional[str] = None
    nodes: list[Node]
    edges: list[GraphEdge]

    class Config:
        populate_by_name = True


# --- 验证结果 ---

class GraphValidationError(BaseModel):
    """图验证错误"""
    code: str  # "duplicate-node-id" | "edge-from-unknown-node" | "self-edge" | "cycle" | ...
    message: str
    ref: Optional[str] = None


class GraphValidationResult(BaseModel):
    """图验证结果"""
    ok: bool
    errors: list[GraphValidationError] = []
    warnings: list[GraphValidationError] = []


# --- 资源 ---

class AssetMetadata(BaseModel):
    """资源元数据"""
    filename: Optional[str] = None
    mime_type: Optional[str] = Field(None, alias="mimeType")
    size_bytes: Optional[int] = Field(None, alias="sizeBytes")
    width: Optional[int] = None
    height: Optional[int] = None
    duration_sec: Optional[float] = Field(None, alias="durationSec")
    user_caption: Optional[str] = Field(None, alias="userCaption")

    class Config:
        populate_by_name = True


class Asset(BaseModel):
    """资源"""
    id: str
    type: AssetType
    path: Optional[str] = None
    content: Optional[str] = None
    metadata: AssetMetadata = AssetMetadata()
    user_tags: list[str] = Field([], alias="userTags")

    class Config:
        populate_by_name = True


# --- 用户偏好 ---

class UserPreferences(BaseModel):
    """用户偏好设置"""
    aspect: Optional[str] = None
    duration_target_sec: Optional[float] = Field(None, alias="durationTargetSec")
    format: Optional[str] = "mp4"
    resolution: Optional[dict] = None  # {"width": 1920, "height": 1080}
    fps: Optional[int] = None
    mood: Optional[str] = None
    brand_colors: Optional[list[str]] = Field(None, alias="brandColors")
    font_families: Optional[list[str]] = Field(None, alias="fontFamilies")
    language: Optional[str] = None
    commercial: Optional[bool] = None

    class Config:
        populate_by_name = True


# --- 帧记录 ---

class FrameRecord(BaseModel):
    """帧记录"""
    graph_node_id: str = Field(alias="graphNodeId")
    html_path: str = Field(alias="htmlPath")
    duration_sec: float = Field(3.0, alias="durationSec")
    poster_path: Optional[str] = Field(None, alias="posterPath")
    order: int
    engine: Optional[str] = None
    native_template_id: Optional[str] = Field(None, alias="nativeTemplateId")
    data: Any = None
    preview_mp4_path: Optional[str] = Field(None, alias="previewMp4Path")

    class Config:
        populate_by_name = True


# --- 配乐 ---

class ProjectSoundtrack(BaseModel):
    """项目配乐"""
    music_asset_id: Optional[str] = Field(None, alias="musicAssetId")
    narration_asset_id: Optional[str] = Field(None, alias="narrationAssetId")
    music_volume_db: float = Field(-18, alias="musicVolumeDb")
    narration_volume_db: float = Field(0, alias="narrationVolumeDb")
    music_prompt: Optional[str] = Field(None, alias="musicPrompt")
    narration_text: Optional[str] = Field(None, alias="narrationText")
    narration_by_frame: Optional[dict[str, str]] = Field(None, alias="narrationByFrame")
    fade_in_sec: Optional[float] = Field(None, alias="fadeInSec")
    fade_out_sec: Optional[float] = Field(None, alias="fadeOutSec")

    class Config:
        populate_by_name = True


# --- 项目 ---

class Project(BaseModel):
    """项目"""
    id: str
    name: str
    intent: Optional[str] = None
    assets: list[Asset] = []
    template_id: Optional[str] = Field(None, alias="templateId")
    variables: dict[str, Any] = {}
    preferences: UserPreferences = UserPreferences()
    status: ProjectStatus = ProjectStatus.DRAFT
    last_preview_html_path: Optional[str] = Field(None, alias="lastPreviewHtmlPath")
    last_preview_poster_path: Optional[str] = Field(None, alias="lastPreviewPosterPath")
    last_output_mp4_path: Optional[str] = Field(None, alias="lastOutputMp4Path")
    exports: list[dict] = []
    content_graph_path: Optional[str] = Field(None, alias="contentGraphPath")
    frames: list[FrameRecord] = []
    soundtrack: Optional[ProjectSoundtrack] = None
    created_at: str = Field("", alias="createdAt")
    updated_at: str = Field("", alias="updatedAt")

    class Config:
        populate_by_name = True


# --- 渲染配置 ---

class RenderConfig(BaseModel):
    """渲染配置"""
    format: str = "mp4"
    resolution: dict = {"width": 1920, "height": 1080}
    fps: int = 30
    duration: Union[float, Literal["auto"]] = "auto"
    duration_mode: Literal["explicit", "auto"] = Field("auto", alias="durationMode")
    output_path: str = Field("", alias="outputPath")
    alpha: bool = False
    quality: str = "medium"

    class Config:
        populate_by_name = True


class RenderOutput(BaseModel):
    """渲染输出"""
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
    """许可证信息"""
    spdx: str
    attribution_required: bool = Field(alias="attributionRequired")
    redistribution_allowed: bool = Field(alias="redistributionAllowed")
    commercial_use: bool = Field(alias="commercialUse")
    notes: Optional[str] = None

    class Config:
        populate_by_name = True


class OutputCapabilities(BaseModel):
    """输出能力"""
    formats: list[str]
    default_format: str = Field(alias="defaultFormat")
    resolution: dict
    fps: dict
    duration: dict
    alpha: bool
    audio: dict

    class Config:
        populate_by_name = True


class TemplateMetadata(BaseModel):
    """模板元数据"""
    spec_version: int = Field(1, alias="specVersion")
    id: str
    name: str
    description: str
    engine: str
    engine_version: str = Field("", alias="engineVersion")
    source_entry: str = Field(alias="sourceEntry")
    native: Optional[dict] = None
    category: str
    subcategory: Optional[str] = None
    tags: list[str] = []
    best_for: list[str] = Field([], alias="bestFor")
    not_for: list[str] = Field([], alias="notFor")
    output: OutputCapabilities
    inputs: dict
    license: LicenseInfo
    author: dict
    version: str
    preview: dict
    # 内部字段
    template_dir: Optional[str] = Field(None, alias="dir")  # 模板目录绝对路径

    class Config:
        populate_by_name = True


# --- 模板搜索结果 ---

class TemplateSearchResult(BaseModel):
    """模板搜索结果"""
    template: TemplateMetadata
    score: float
    matched_tags: list[str] = []
