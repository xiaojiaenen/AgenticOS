"""ArtifactFactory：PPT / website / spreadsheet 工件创建与 PPTX 导出。

从原 ``app/services/agent_service.py`` 整段搬移（TECH-DEBT-2026-09 拆分）：
- _create_ppt_artifact / _create_website_artifact / _create_sheet_artifact
- _inline_dist_assets / _get_edit_hint / _infer_project_slug_from_tools
- _export_pptx_sync

本类为 Mixin：由 ``service.AgentService`` 组合继承，依赖宿主提供的属性
（self.ppt_artifacts: PptArtifactService）。
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from app.core.data_path import (
    DATA_DIR,
    PPT_SESSIONS_DIR,
    SHEETS_DIR,
    WEBSITES_DIR,
    _parse_dir_name,
)

_logger = logging.getLogger("agent")


class ArtifactFactory:
    """PPT / website 工件工厂（Mixin，由 AgentService 组合继承）。

    依赖宿主（AgentService）提供的属性：
    - ``self.ppt_artifacts``: PptArtifactService
    """

    async def _create_ppt_artifact(self, session_id: str) -> dict[str, Any] | None:
        """Create a PPT artifact from saved slides in the session work directory."""
        from app.core.data_path import next_version_dir

        # Find the latest versioned directory for this session.
        # Directory naming: u{user_id}_s{session_id}_v{version}
        def _find_slides_dir():
            _slides_dir = None
            max_ver = 0
            if PPT_SESSIONS_DIR.exists():
                for child in PPT_SESSIONS_DIR.iterdir():
                    if not child.is_dir():
                        continue
                    parsed = _parse_dir_name(child.name)
                    if parsed and str(parsed[1]) == session_id:
                        if parsed[2] > max_ver:
                            max_ver = parsed[2]
                            _slides_dir = child
            return _slides_dir

        _slides_dir = await asyncio.to_thread(_find_slides_dir)
        if _slides_dir is None:
            # 使用正确的命名格式，而不是直接使用 session_id
            from app.core.data_path import get_current_user_id
            user_id = get_current_user_id() or 0
            _slides_dir = next_version_dir(PPT_SESSIONS_DIR, user_id, session_id)
        try:
            artifact = await self.ppt_artifacts.create_from_slides_dir(session_id, _slides_dir)
            if artifact is not None:
                _logger.info("ppt artifact created: session=%s slides=%d", session_id, artifact.get("slide_count", 0))
            else:
                _logger.info("ppt artifact skipped: session=%s (no slides found)", session_id)
            return artifact
        except Exception as exc:
            _logger.exception("ppt artifact creation failed: session=%s", session_id)
            # 按 session 隔离记录质量门结果（原先写入跨会话共享的 _last_quality_* 属性）
            self.ppt_artifacts.set_quality_feedback(
                session_id, [f"artifact 创建异常: {type(exc).__name__}: {exc}"], []
            )
            return None

    @staticmethod
    def _infer_project_slug_from_tools(tool_names: list[str], messages: list | None = None) -> str | None:
        """Try to find the project slug from recent tool calls.

        We can't directly access tool call arguments here, so we scan
        data/websites/ for directories with recent dist/ folders.
        """
        _websites_dir = WEBSITES_DIR
        if not _websites_dir.exists():
            return None

        # Find directories with dist/ that have been modified recently
        candidates: list[tuple[str, float]] = []
        for proj in _websites_dir.iterdir():
            if not proj.is_dir() or proj.name.startswith("."):
                continue
            dist = proj / "dist"
            if dist.exists() and dist.is_dir():
                index_html = dist / "index.html"
                if index_html.exists():
                    candidates.append((proj.name, index_html.stat().st_mtime))

        if not candidates:
            return None

        # Return the most recently modified one
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    @staticmethod
    def _inline_dist_assets(dist_dir: "Path", html: str) -> str:
        """Inline CSS and JS assets from dist/ into a self-contained HTML document.

        Vite-built index.html references /assets/... paths which can't resolve
        inside an iframe srcdoc. This reads each local asset and inlines it.
        """
        import re as _re

        def _read_asset(href: str) -> str | None:
            path = href.lstrip("/")
            file_path = dist_dir / path
            if not file_path.exists():
                return None
            try:
                return file_path.read_text(encoding="utf-8")
            except Exception as e:
                _logger.debug("File read failed: %s — %s", file_path, e)
                return None

        # Inline CSS: <link rel="stylesheet" href="/assets/xxx.css" /> → <style>
        link_re = _re.compile(
            r'<link\b[^>]*\brel\s*=\s*["\']stylesheet["\'][^>]*\bhref\s*=\s*["\']([^"\']+\.css)["\'][^>]*/?>',
            _re.IGNORECASE,
        )
        def _replace_link(match: _re.Match) -> str:
            href = match.group(1)
            content = _read_asset(href)
            if content is None:
                return match.group(0)
            return f"<style>{content}</style>"

        html = link_re.sub(_replace_link, html)

        # Inline JS: <script src="/assets/xxx.js"></script> → <script>...</script>
        script_re = _re.compile(
            r'<script\b([^>]*)\bsrc\s*=\s*["\']([^"\']+)["\']([^>]*)>\s*</script>',
            _re.IGNORECASE,
        )
        def _replace_script(match: _re.Match) -> str:
            src = match.group(2)
            if src.startswith(("http://", "https://", "data:")):
                return match.group(0)
            content = _read_asset(src)
            if content is None:
                return match.group(0)
            before = match.group(1)
            after = match.group(3)
            return f"<script{before}{after}>{content}</script>"

        html = script_re.sub(_replace_script, html)

        return html

    async def _create_website_artifact(
        self, session_id: str, tool_names: list[str]
    ) -> dict[str, Any] | None:
        """Create a website artifact from the built dist/ directory."""
        _websites_dir = WEBSITES_DIR

        try:
            slug = await asyncio.to_thread(self._infer_project_slug_from_tools, tool_names)
            if not slug:
                _logger.info("website artifact skipped: could not infer project slug")
                return None
            return await self.build_website_artifact(session_id, slug)
        except Exception:
            _logger.exception("website artifact creation failed: session=%s", session_id)
            return None

    # ── spreadsheet 工件 ───────────────────────────────────────────────

    async def _create_sheet_artifact(self, session_id: str) -> dict[str, Any] | None:
        """Create a spreadsheet artifact from the newest workbook snapshot on disk.

        与 website 同构：产物不是从模型输出里解析的，而是从 data/sheets 下
        build_sheet 写出的快照读回来的，所以刷新页面能重建、也不会出现
        "模型编了一个不存在的表格"。
        """
        try:

            def _find_latest() -> Path | None:
                if not SHEETS_DIR.exists():
                    return None
                best_ver = -1
                best: Path | None = None
                for child in SHEETS_DIR.iterdir():
                    if not child.is_dir() or not (child / "workbook.json").is_file():
                        continue
                    parsed = _parse_dir_name(child.name)
                    if parsed and str(parsed[1]) == session_id and parsed[2] > best_ver:
                        best_ver = parsed[2]
                        best = child
                return best

            directory = await asyncio.to_thread(_find_latest)
            if directory is None:
                return None
            return await self.build_sheet_artifact(session_id, directory)
        except Exception:
            _logger.exception("sheet artifact creation failed: session=%s", session_id)
            return None

    async def build_sheet_artifact(
        self, session_id: str, directory: Path
    ) -> dict[str, Any] | None:
        """从 data/sheets/{version_dir}/workbook.json 构建 spreadsheet 制品。"""
        from app.services.sheet.service import read_snapshot

        snapshot = await asyncio.to_thread(read_snapshot, directory)
        if not snapshot:
            _logger.info("sheet artifact skipped: unreadable snapshot at %s", directory)
            return None

        sheets = snapshot.get("sheets", {}) or {}
        order = snapshot.get("sheetOrder", []) or []
        sheet_names = [
            sheets[sid].get("name", sid) for sid in order if sid in sheets
        ]
        # 字段命名与 website 产物保持一致（type + snake_case），由前端翻译成
        # 前端的 Artifact 联合类型。
        return {
            "type": "spreadsheet",
            "artifact_id": directory.name,
            "session_id": session_id,
            "title": snapshot.get("name") or "未命名表格",
            "snapshot": snapshot,
            "sheet_names": sheet_names,
            "sheet_count": len(order),
        }

    async def get_latest_sheet_artifact(self, session_id: str) -> dict[str, Any] | None:
        """回源重建会话最新的表格制品（刷新页面后恢复预览面板用）。

        data/sheets 下目录形如 ``u{user}_s{session}_v{version}``，取版本号最大的一个。
        """
        return await self._create_sheet_artifact(session_id)

    async def get_latest_website_artifact(self, session_id: str) -> dict[str, Any] | None:
        """回源重建会话最新的网站制品（刷新页面后恢复预览面板用）。

        data/websites 下目录形如 ``u{user}_s{session}_v{version}``，取版本号最大的一个。
        """
        def _find_latest_slug() -> str | None:
            if not WEBSITES_DIR.exists():
                return None
            best_ver = -1
            best_name: str | None = None
            for child in WEBSITES_DIR.iterdir():
                if not child.is_dir():
                    continue
                parsed = _parse_dir_name(child.name)
                if parsed and str(parsed[1]) == session_id and parsed[2] > best_ver:
                    best_ver = parsed[2]
                    best_name = child.name
            return best_name

        try:
            slug = await asyncio.to_thread(_find_latest_slug)
            if not slug:
                return None
            return await self.build_website_artifact(session_id, slug)
        except Exception:
            _logger.exception("latest website artifact lookup failed: session=%s", session_id)
            return None

    async def build_website_artifact(self, session_id: str, slug: str) -> dict[str, Any] | None:
        """从 data/websites/{slug}/dist 构建 website 制品（预览 HTML 内联资源）。"""
        _websites_dir = WEBSITES_DIR
        project_dir = _websites_dir / slug
        dist_dir = project_dir / "dist"
        index_html = dist_dir / "index.html"
        if not index_html.exists():
            _logger.info("website artifact skipped: dist/index.html not found in %s", dist_dir)
            return None

        raw_html = await asyncio.to_thread(index_html.read_text, encoding="utf-8")
        preview_html = self._inline_dist_assets(dist_dir, raw_html)

        # Count files in dist and detect stack（同步 rglob 扫描放线程池）
        def _scan_project():
            file_count = len([f for f in dist_dir.rglob("*") if f.is_file()])
            has_vue = any(f.suffix == ".vue" for f in project_dir.rglob("*"))
            has_jsx = any(f.suffix == ".jsx" for f in project_dir.rglob("*"))
            return file_count, has_vue, has_jsx

        file_count, has_vue, has_jsx = await asyncio.to_thread(_scan_project)
        if has_vue:
            stack = "vue"
        elif has_jsx:
            stack = "react"
        else:
            stack = "vanilla"

        return {
            "type": "website",
            "artifact_id": session_id,  # use session_id as artifact_id for now
            "session_id": session_id,
            "title": slug.replace("-", " ").title(),
            "project_slug": slug,
            "stack": stack,
            "file_count": file_count,
            "preview_html": preview_html,
        }

    async def _get_edit_hint(self, session_id: str) -> str | None:
        """If the session has existing PPT artifacts, add an edit hint for save_slide."""
        try:
            artifact = await self.ppt_artifacts.get_latest_for_session(session_id)
            if artifact is None:
                return None
            title = artifact.get("title", "未命名")
            slide_count = artifact.get("slide_count", 0)
            # 查找正确的目录（u{user_id}_s{session_id}_v{version} 格式）
            from app.core.data_path import _parse_dir_name

            def _find_slides_dir():
                slides_dir = None
                if PPT_SESSIONS_DIR.exists():
                    for child in PPT_SESSIONS_DIR.iterdir():
                        if not child.is_dir():
                            continue
                        parsed = _parse_dir_name(child.name)
                        if parsed and str(parsed[1]) == session_id:
                            slides_dir = child
                            break
                return slides_dir

            slides_dir = await asyncio.to_thread(_find_slides_dir)
            if slides_dir is None:
                slides_dir = PPT_SESSIONS_DIR / session_id  # fallback
            svg_files = sorted(slides_dir.glob("slide_*.svg"),
                                key=lambda p: int(p.stem.replace("slide_", ""))) if slides_dir.exists() else []
            file_list = "\n".join(
                f"  read_slide({f.stem.replace('slide_', '')})" for f in svg_files
            ) if svg_files else "  （无已保存文件）"
            return (
                f"\n\n---\n"
                f"## 注意：当前对话已有 PPT「{title}」（{slide_count} 页）\n"
                f"用户可能要修改它。用 read_slide(N) 读取后，save_slide 覆盖修改的页：\n"
                f"{file_list}\n"
                f"如果是新建 PPT 要求，忽略此提示。\n"
            )
        except Exception:
            _logger.warning("_get_edit_hint failed for session=%s", session_id, exc_info=True)
            return None

    @staticmethod
    def _export_pptx_sync(
        artifact_id: str,
        svgs: list[str],
        canvas_format: str | None,
        use_native_shapes: bool,
        use_compat_mode: bool,
        transition: str | None,
        animation: str | None,
        enable_notes: bool,
    ) -> bytes:
        """同步执行 PPTX 导出（在线程池中运行）"""
        import logging
        import tempfile
        from pathlib import Path
        from app.services.ppt.svg_to_pptx import create_pptx_with_native_svg
        from app.services.ppt.svg_finalize.embed_icons import process_svg_file as _embed_icons
        from app.services.ppt.svg_finalize.align_embed_images import align_and_embed_images_in_svg as _align_images
        from app.services.ppt.svg_finalize.flatten_tspan import flatten_text_with_tspans as _flatten_tspan_text
        from app.services.ppt.svg_finalize.svg_rect_to_path import process_svg as _fix_rounded
        from app.services.ppt_artifact_service import sanitize_svg_xml
        from xml.etree import ElementTree as ET

        _logger = logging.getLogger("ppt_export")

        _logger.info(f"Exporting artifact {artifact_id}: {len(svgs)} slides, "
                     f"native_shapes={use_native_shapes}, compat={use_compat_mode}")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            svg_paths: list[Path] = []
            for i, svg_content in enumerate(svgs):
                svg_path = tmpdir_path / f"slide{i + 1}.svg"
                svg_content = sanitize_svg_xml(svg_content)
                svg_path.write_text(svg_content, encoding="utf-8")
                svg_paths.append(svg_path)

            # SVG post-processing
            _icons_dir = DATA_DIR / "icons"
            _processed = 0
            for svg_path in svg_paths:
                _processed += _embed_icons(svg_path, _icons_dir, dry_run=False, verbose=False)
                _processed += _align_images(svg_path, dry_run=False, verbose=False)[0]
                try:
                    svg_content = svg_path.read_text(encoding="utf-8")
                    svg_content = svg_content.replace('&nbsp;', '&#160;')
                    svg_content = svg_content.replace('&copy;', '&#169;')
                    svg_content = svg_content.replace('&reg;', '&#174;')
                    svg_content = svg_content.replace('&trade;', '&#8482;')
                    svg_content = svg_content.replace('&mdash;', '&#8212;')
                    svg_content = svg_content.replace('&ndash;', '&#8211;')
                    svg_content = svg_content.replace('&ldquo;', '&#8220;')
                    svg_content = svg_content.replace('&rdquo;', '&#8221;')
                    svg_content = svg_content.replace('&lsquo;', '&#8216;')
                    svg_content = svg_content.replace('&rsquo;', '&#8217;')
                    svg_content = svg_content.replace('&hellip;', '&#8230;')
                    svg_content = svg_content.replace('&bull;', '&#8226;')
                    import re
                    svg_content = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)', '&amp;', svg_content)
                    svg_content = svg_content.replace('<br>', '<br/>')
                    svg_content = svg_content.replace('<hr>', '<hr/>')
                    svg_path.write_text(svg_content, encoding="utf-8")
                    import io
                    tree = ET.parse(io.StringIO(svg_content))
                    if _flatten_tspan_text(tree):
                        tree.write(str(svg_path), encoding="unicode", xml_declaration=False)
                        _processed += 1
                except Exception:
                    _logger.warning("tspan flatten failed for %s", svg_path.name, exc_info=True)
                try:
                    raw = svg_path.read_text(encoding="utf-8")
                    new_content, count = _fix_rounded(raw, verbose=False)
                    if count:
                        svg_path.write_text(new_content, encoding="utf-8")
                        _processed += count
                except Exception:
                    _logger.warning("rounded rect fix failed for %s", svg_path.name, exc_info=True)
            _logger.info(f"SVG post-processing: {_processed} changes across {len(svg_paths)} slides")

            output_path = tmpdir_path / "output.pptx"
            create_pptx_with_native_svg(
                svg_files=svg_paths,
                output_path=output_path,
                canvas_format=canvas_format or "ppt169",
                verbose=False,
                transition=transition or "fade",
                use_native_shapes=use_native_shapes,
                use_compat_mode=use_compat_mode,
                animation=animation or "mixed",
                enable_notes=enable_notes,
                notes={},
            )

            return output_path.read_bytes()
