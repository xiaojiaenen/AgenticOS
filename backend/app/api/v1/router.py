from fastapi import APIRouter

from app.api.v1.endpoints.agent import router as agent_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.dashboard import router as dashboard_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.users import router as users_router

router = APIRouter()
router.include_router(agent_router)
router.include_router(auth_router)
router.include_router(dashboard_router)
router.include_router(health_router)
router.include_router(users_router)
