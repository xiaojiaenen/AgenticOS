from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["健康检查"])


@router.get("/", summary="健康检查")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
