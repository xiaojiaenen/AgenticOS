"""
Video 智能体 API 端点
提供视频文件服务和缩略图
"""

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

router = APIRouter()


# 视频文件根目录（与 orchestrator 一致）
def _get_video_root() -> str:
    """获取视频项目根目录"""
    return os.getcwd()


@router.get("/videos/{project_id}/file")
async def get_video_file(project_id: str, request: Request):
    """
    返回 MP4 视频文件，支持 Range 请求（用于视频播放器拖拽进度条）
    """
    from app.services.video import get_video_orchestrator

    orchestrator = get_video_orchestrator()

    try:
        project = await orchestrator.load(project_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.last_output_mp4_path or not os.path.exists(project.last_output_mp4_path):
        raise HTTPException(status_code=404, detail="Video file not found")

    video_path = project.last_output_mp4_path
    file_size = os.path.getsize(video_path)

    # 处理 Range 请求
    range_header = request.headers.get("range")
    if range_header:
        # 解析 Range: bytes=start-end
        try:
            ranges = range_header.replace("bytes=", "").split("-")
            start = int(ranges[0]) if ranges[0] else 0
            end = int(ranges[1]) if ranges[1] else file_size - 1
        except (ValueError, IndexError):
            start = 0
            end = file_size - 1

        # 边界检查
        start = max(0, min(start, file_size - 1))
        end = max(start, min(end, file_size - 1))
        content_length = end - start + 1

        def iterfile():
            with open(video_path, "rb") as f:
                f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk_size = min(8192, remaining)
                    data = f.read(chunk_size)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(
            iterfile(),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Content-Disposition": f'inline; filename="{project.name}.mp4"',
            },
        )

    # 普通请求
    return FileResponse(
        video_path,
        media_type="video/mp4",
        filename=f"{project.name}.mp4",
    )


@router.get("/videos/{project_id}/thumbnail")
async def get_video_thumbnail(project_id: str):
    """
    返回视频首帧缩略图（JPEG）
    如果缩略图不存在，尝试从视频生成
    """
    from app.services.video import get_video_orchestrator

    orchestrator = get_video_orchestrator()

    try:
        project = await orchestrator.load(project_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.last_output_mp4_path or not os.path.exists(project.last_output_mp4_path):
        raise HTTPException(status_code=404, detail="Video file not found")

    # 检查缩略图是否已存在
    video_dir = os.path.dirname(project.last_output_mp4_path)
    thumbnail_path = os.path.join(video_dir, "thumbnail.jpg")

    if not os.path.exists(thumbnail_path):
        # 使用 ffmpeg 生成缩略图
        try:
            import asyncio

            proc = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-y",
                "-i",
                project.last_output_mp4_path,
                "-vframes",
                "1",
                "-q:v",
                "2",
                thumbnail_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            if proc.returncode != 0 or not os.path.exists(thumbnail_path):
                raise HTTPException(status_code=500, detail="Failed to generate thumbnail")
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail="ffmpeg not available")

    return FileResponse(
        thumbnail_path,
        media_type="image/jpeg",
        filename=f"{project.name}_thumbnail.jpg",
    )


@router.get("/videos/{project_id}/info")
async def get_video_info(project_id: str):
    """
    获取视频元信息
    """
    from app.services.video import get_video_orchestrator

    orchestrator = get_video_orchestrator()

    try:
        project = await orchestrator.load(project_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.last_output_mp4_path:
        raise HTTPException(status_code=404, detail="No video output found")

    file_size = 0
    if os.path.exists(project.last_output_mp4_path):
        file_size = os.path.getsize(project.last_output_mp4_path)

    # 从导出历史获取最新信息
    duration_sec = 0
    resolution = "1920x1080"
    fps = 30
    if project.exports:
        latest = project.exports[-1]
        duration_sec = latest.get("duration_sec", 0)
        res = latest.get("resolution", {})
        resolution = f"{res.get('width', 1920)}x{res.get('height', 1080)}"
        fps = latest.get("fps", 30)

    return {
        "project_id": project.id,
        "title": project.name,
        "status": project.status.value,
        "template_id": project.template_id,
        "duration_sec": duration_sec,
        "resolution": resolution,
        "fps": fps,
        "file_size_bytes": file_size,
        "video_url": f"/api/v1/videos/{project_id}/file",
        "thumbnail_url": f"/api/v1/videos/{project_id}/thumbnail",
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }
