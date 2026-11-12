"""文件型作品发布服务（PPT / 文档 / 表格）。

与网站发布（``website_deploy_service``）分开：

- 网站是**静态站点**：源码 → build → dist/ → nginx alias，访问地址是目录。
- 文件型作品是**单个二进制文件**：预览用类型化渲染，访问地址是下载端点。

两者共享"作品库条目"的语义（公开/私密、审批、访问统计、短链），
但底层的存储与访问方式不同，硬塞进一张表会让两套都别扭。

导出策略：

- PPT   —— 复用既有 SVG→PPTX 管线（``AgentService.export_pptx``），产出原生 .pptx；
- 表格 —— Univer 快照 → openpyxl 写 .xlsx（公式与多工作表保留）；
- 文档 —— Univer 快照 → 结构化 HTML（.docx 需要额外依赖，先不做二进制）。
"""

from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.db.models import PublishedItemModel
from app.db.session import create_db_session

_logger = logging.getLogger("published_items")

from app.core.data_path import DATA_DIR

# 发布的文件落在这里：data/published/<short_code>/
PUBLISHED_ITEMS_DIR: Path = DATA_DIR / "published"

_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"

KIND_PPT = "ppt"
KIND_DOCUMENT = "document"
KIND_SHEET = "sheet"

KIND_LABELS = {
    KIND_PPT: "演示文稿",
    KIND_DOCUMENT: "文档",
    KIND_SHEET: "表格",
}

# 文件扩展名（下载端点据此给 Content-Type）
KIND_EXTENSIONS = {
    KIND_PPT: ".pptx",
    KIND_DOCUMENT: ".html",
    KIND_SHEET: ".xlsx",
}

# 预览 MIME
KIND_MIME = {
    KIND_PPT: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    KIND_DOCUMENT: "text/html; charset=utf-8",
    KIND_SHEET: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _new_short_code() -> str:
    import secrets

    return "".join(secrets.choice(_ALPHABET) for _ in range(10))


def _safe_filename(title: str, fallback: str) -> str:
    """把标题变成安全文件名（保留中文，去掉路径分隔符与控制字符）。"""
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', "", (title or "").strip())
    cleaned = cleaned.strip(". ")
    return (cleaned or fallback)[:80]


class PublishedItemService:
    """文件型作品的发布（申请 → 审批 → 上架 / 下架）。"""

    def __init__(self, session_factory=create_db_session) -> None:
        self.session_factory = session_factory

    # ── 申请 ────────────────────────────────────────────────────────────

    def request_publish(
        self,
        *,
        kind: str,
        session_id: str,
        source_ref: str,
        user_id: int,
        title: str,
        description: str = "",
    ) -> dict[str, Any]:
        """提交发布申请。

        文件型作品**只能公开**（用户明确要求）：PPT/文档/表格没有服务端
        运行时，泄露即等于公开，所以不存在"私密发布"这种选项。

        同一份产物重复申请时复用已有的 pending 记录（幂等）。
        """
        if kind not in KIND_LABELS:
            raise ValueError(f"不支持的产物类型: {kind}")
        if not source_ref:
            raise ValueError("缺少产物标识")

        with self.session_factory() as db:
            existing = db.scalar(
                select(PublishedItemModel).where(
                    PublishedItemModel.kind == kind,
                    PublishedItemModel.source_ref == source_ref,
                    PublishedItemModel.status == "pending",
                )
            )
            if existing is not None:
                # 幂等：更新说明与标题，其余保持
                existing.title = (title or "").strip()[:200] or existing.title
                existing.description = (description or "").strip()[:2000]
                existing.updated_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(existing)
                return self._serialize(existing)

            item = PublishedItemModel(
                kind=kind,
                session_id=session_id,
                source_ref=source_ref,
                user_id=user_id,
                title=(title or "").strip()[:200] or "未命名作品",
                description=(description or "").strip()[:2000],
                visibility="public",
                status="pending",
                short_code=_new_short_code(),
                requested_by=user_id,
                file_path="",
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            _logger.info("publish requested: kind=%s ref=%s user=%s", kind, source_ref, user_id)
            return self._serialize(item)

    # ── 审批 ────────────────────────────────────────────────────────────

    def decide(self, item_id: int, status: str, approved_by: int, reason: str | None = None) -> dict[str, Any]:
        """管理员审批。通过则导出文件并上架；拒绝则落 rejected。"""
        if status not in ("approved", "rejected"):
            raise ValueError("status must be 'approved' or 'rejected'")

        with self.session_factory() as db:
            item = db.get(PublishedItemModel, item_id)
            if item is None:
                raise LookupError(f"Published item {item_id} not found")
            if item.status != "pending":
                raise ValueError(f"发布申请 {item_id} 当前状态为 {item.status}，无法重复处理")

            item.status = status
            item.approved_by = approved_by
            item.reason = reason
            item.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(item)

            if status == "approved":
                try:
                    self._materialize(item)
                    db.commit()
                    db.refresh(item)
                except Exception as exc:  # noqa: BLE001
                    _logger.exception("发布物化失败: id=%s", item_id)
                    item.status = "failed"
                    item.reason = f"导出失败：{exc}"[:500]
                    item.updated_at = datetime.now(timezone.utc)
                    db.commit()
                    db.refresh(item)
            return self._serialize(item)

    def cancel(self, item_id: int, *, by_user_id: int, is_admin: bool = False) -> dict[str, Any]:
        """取消发布：下架，**源产物保留**（用户可重新发布）。"""
        with self.session_factory() as db:
            item = db.get(PublishedItemModel, item_id)
            if item is None:
                raise LookupError(f"Published item {item_id} not found")
            if not is_admin and item.user_id != by_user_id and item.requested_by != by_user_id:
                raise PermissionError("只能取消自己的发布")
            if item.status in ("cancelled", "superseded"):
                return self._serialize(item)
            self._remove_files(item)
            item.status = "cancelled"
            item.reason = "用户取消发布（源产物保留）"
            item.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(item)
            return self._serialize(item)

    # ── 物化：把源产物导出成发布文件 ────────────────────────────────────

    def _materialize(self, item: PublishedItemModel) -> None:
        """导出发布文件并落盘到 ``data/published/<short_code>/``。"""
        target_dir = PUBLISHED_ITEMS_DIR / item.short_code
        target_dir.mkdir(parents=True, exist_ok=True)

        if item.kind == KIND_PPT:
            filename = _safe_filename(item.title, "deck") + ".pptx"
            out_path = target_dir / filename
            self._export_pptx(item, out_path)
        elif item.kind == KIND_SHEET:
            filename = _safe_filename(item.title, "sheet") + ".xlsx"
            out_path = target_dir / filename
            self._export_sheet(item, out_path)
        elif item.kind == KIND_DOCUMENT:
            filename = _safe_filename(item.title, "document") + ".html"
            out_path = target_dir / filename
            self._export_document(item, out_path)
        else:  # pragma: no cover —— request_publish 已挡
            raise ValueError(f"不支持的产物类型: {item.kind}")

        item.file_path = str(Path(item.short_code) / filename)
        item.status = "deployed"
        item.updated_at = datetime.now(timezone.utc)

    def _export_pptx(self, item: PublishedItemModel, out_path: Path) -> None:
        """PPT：复用 SVG→PPTX 管线。"""
        import json

        from app.services.agent.artifacts import ArtifactFactory

        db_artifact = self._load_ppt_artifact(item.source_ref)
        if not db_artifact:
            raise FileNotFoundError(f"PPT 产物不存在: {item.source_ref}")

        deck = json.loads(db_artifact.get("deck_json") or "{}")
        theme = deck.get("theme") or "apple"
        svgs = deck.get("svgs") or []
        if not svgs:
            raise FileNotFoundError("PPT 产物没有幻灯片")

        data = ArtifactFactory._export_pptx_sync(
            self,
            artifact_id=item.source_ref,
            svgs=svgs,
            canvas_format=None,
            use_native_shapes=True,
            use_compat_mode=False,
            transition=None,
            animation=None,
            enable_notes=False,
        )
        out_path.write_bytes(data)

    def _load_ppt_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        """读 PPT 产物（同步版）。

        ``PptArtifactService.get`` 是 async（为的是不阻塞事件循环），
        但发布审批走的是同步线程池路径 —— 直接查库更稳，也避免在同步
        上下文里"忘记 await"（那会静默拿到 coroutine 对象而不是数据）。
        """
        from app.db.models import PptArtifactModel

        with self.session_factory() as db:
            row = db.get(PptArtifactModel, artifact_id)
            if row is None:
                return None
            return {
                "artifact_id": row.artifact_id,
                "session_id": row.session_id,
                "title": row.title,
                "slide_count": row.slide_count,
                "deck_json": row.deck_json,
                "preview_html": row.preview_html,
                "metadata_json": row.metadata_json,
            }

    def _export_sheet(self, item: PublishedItemModel, out_path: Path) -> None:
        """表格：Univer 快照 → openpyxl。"""
        snapshot = self._read_office_snapshot(item.source_ref, kind="sheet")
        if not snapshot:
            raise FileNotFoundError(f"表格快照不存在: {item.source_ref}")

        from openpyxl import Workbook

        wb = Workbook()
        wb.remove(wb.active)
        sheets = snapshot.get("sheets") or {}
        order = snapshot.get("sheetOrder") or list(sheets.keys())

        for sheet_id in order:
            sheet = sheets.get(sheet_id)
            if not sheet:
                continue
            ws = wb.create_sheet(title=(sheet.get("name") or sheet_id)[:31])
            for row_idx, row in enumerate(sheet.get("cellData") or [], start=1):
                if not isinstance(row, list):
                    continue
                for col_idx, cell in enumerate(row, start=1):
                    if not isinstance(cell, dict):
                        continue
                    content = cell.get("content") or {}
                    value = content.get("v")
                    formula = (content.get("f") or "").strip()
                    if formula:
                        ws.cell(row=row_idx, column=col_idx, value=f"={formula}")
                    elif value is not None:
                        ws.cell(row=row_idx, column=col_idx, value=value)
        if not wb.sheetnames:
            wb.create_sheet(title="Sheet1")
        wb.save(out_path)

    def _export_document(self, item: PublishedItemModel, out_path: Path) -> None:
        """文档：Univer 快照 → 自包含 HTML（标题层级保留）。"""
        snapshot = self._read_office_snapshot(item.source_ref, kind="document")
        if not snapshot:
            raise FileNotFoundError(f"文档快照不存在: {item.source_ref}")

        title = snapshot.get("title") or item.title
        body = snapshot.get("body") or {}
        stream = body.get("dataStream") or ""
        paragraphs = body.get("paragraphs") or []

        # 段落级样式（标题层级）从 paragraphs 的 style 推断：
        # Univer 用 namedStyleType 标标题（4=h1 5=h2 6=h3 7=h4）。
        style_by_index = {}
        for idx, para in enumerate(paragraphs):
            style = ((para.get("style") or {}) or {}).get("namedStyleType")
            if style in (4, 5, 6, 7):
                style_by_index[idx] = f"h{style - 3}"

        lines = (stream.split("\r") if "\r" in stream else stream.split("\n"))
        html_parts: list[str] = []
        for idx, line in enumerate(lines):
            text = line.strip("\n")
            if not text.strip():
                continue
            tag = style_by_index.get(idx, "p")
            html_parts.append(f"<{tag}>{_escape(text)}</{tag}>")

        html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_escape(title)}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin:0; padding:48px 24px; background:#fff; color:#18181b;
         font:16px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",
         "Hiragino Sans GB","Microsoft YaHei",sans-serif; }}
  .doc {{ max-width:760px; margin:0 auto; }}
  h1 {{ font-size:28px; font-weight:700; margin:32px 0 12px; }}
  h2 {{ font-size:22px; font-weight:650; margin:28px 0 10px; }}
  h3 {{ font-size:18px; font-weight:600; margin:24px 0 8px; }}
  h4 {{ font-size:16px; font-weight:600; margin:20px 0 6px; }}
  p  {{ margin:0 0 14px; }}
</style></head>
<body><div class="doc">
{''.join(html_parts)}
</div></body></html>
"""
        out_path.write_text(html, encoding="utf-8")

    def _read_office_snapshot(self, source_ref: str, *, kind: str) -> dict[str, Any] | None:
        """按 source_ref（版本目录名）读取 office 快照 JSON。"""
        from app.core.data_path import DOCUMENTS_DIR, SHEETS_DIR

        base = SHEETS_DIR if kind == "sheet" else DOCUMENTS_DIR
        filename = "workbook.json" if kind == "sheet" else "document.json"
        path = base / source_ref / filename
        if not path.is_file():
            return None
        import json

        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    # ── 文件访问 ────────────────────────────────────────────────────────

    def file_path(self, item: PublishedItemModel) -> Path | None:
        if not item.file_path:
            return None
        path = PUBLISHED_ITEMS_DIR / item.file_path
        # 纵深防御：不允许逃出发布根目录
        try:
            path.relative_to(PUBLISHED_ITEMS_DIR)
        except ValueError:
            return None
        return path if path.is_file() else None

    def _remove_files(self, item: PublishedItemModel) -> None:
        try:
            target = PUBLISHED_ITEMS_DIR / item.short_code
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
        except Exception:  # noqa: BLE001
            _logger.warning("清理发布目录失败: %s", item.short_code, exc_info=True)

    # ── 查询 ────────────────────────────────────────────────────────────

    def get(self, item_id: int) -> dict[str, Any] | None:
        with self.session_factory() as db:
            row = db.get(PublishedItemModel, item_id)
            return self._serialize(row) if row else None

    def get_by_code(self, code: str) -> dict[str, Any] | None:
        with self.session_factory() as db:
            row = db.scalar(
                select(PublishedItemModel).where(PublishedItemModel.short_code == code)
            )
            return self._serialize(row) if row else None

    def list_pending(self) -> list[dict[str, Any]]:
        with self.session_factory() as db:
            rows = db.scalars(
                select(PublishedItemModel)
                .where(PublishedItemModel.status == "pending")
                .order_by(PublishedItemModel.created_at.desc())
            ).all()
            return [self._serialize(r) for r in rows]

    def list_all(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.session_factory() as db:
            rows = db.scalars(
                select(PublishedItemModel)
                .order_by(PublishedItemModel.created_at.desc())
                .limit(limit)
            ).all()
            return [self._serialize(r) for r in rows]

    def list_gallery(self, viewer_id: int, is_admin: bool = False) -> list[dict[str, Any]]:
        """作品库里的文件型作品（已上架的）。"""
        with self.session_factory() as db:
            rows = db.scalars(
                select(PublishedItemModel)
                .where(PublishedItemModel.status == "deployed")
                .order_by(PublishedItemModel.updated_at.desc())
                .limit(200)
            ).all()
            items = [self._serialize(r) for r in rows]
        for item in items:
            item["author_name"] = self._author_name(item.get("user_id"))
        return items

    def _author_name(self, user_id: int | None) -> str | None:
        if not user_id:
            return None
        try:
            from app.db.models import UserModel

            with self.session_factory() as db:
                row = db.get(UserModel, user_id)
                if row is None:
                    return None
                return (row.name or "").strip() or (row.email or "").split("@")[0] or None
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _serialize(item: PublishedItemModel) -> dict[str, Any]:
        return {
            "id": item.id,
            "kind": item.kind,
            "kind_label": KIND_LABELS.get(item.kind, item.kind),
            "session_id": item.session_id,
            "source_ref": item.source_ref,
            "user_id": item.user_id,
            "title": item.title,
            "description": item.description or "",
            "visibility": item.visibility or "public",
            "status": item.status,
            "short_code": item.short_code,
            "short_url": f"/s/{item.short_code}/",
            "cover_url": None,
            "file_name": Path(item.file_path).name if item.file_path else None,
            "file_size": (
                (PUBLISHED_ITEMS_DIR / item.file_path).stat().st_size
                if item.file_path and (PUBLISHED_ITEMS_DIR / item.file_path).is_file()
                else None
            ),
            "view_count": item.view_count or 0,
            "last_viewed_at": item.last_viewed_at.isoformat() if item.last_viewed_at else None,
            "requested_by": item.requested_by,
            "approved_by": item.approved_by,
            "reason": item.reason,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
