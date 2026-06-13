from fastapi import APIRouter

from app.api.v1.endpoints.announcements import router as announcements_router
from app.api.v1.endpoints.agent import router as agent_router
from app.api.v1.endpoints.agent_profiles import router as agent_profiles_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.credential_proxy import router as credential_proxy_router
from app.api.v1.endpoints.dashboard import router as dashboard_router
from app.api.v1.endpoints.email import router as email_router
from app.api.v1.endpoints.external_systems import admin_router as external_systems_admin_router
from app.api.v1.endpoints.external_systems import router as integrations_router
from app.api.v1.endpoints.files import router as files_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.memory import router as memory_router
from app.api.v1.endpoints.skills import router as skills_router
from app.api.v1.endpoints.suggest import router as suggest_router
from app.api.v1.endpoints.tool_config import router as tool_config_router
from app.api.v1.endpoints.users import router as users_router
from app.api.v1.endpoints.video import router as video_router
from app.api.v1.endpoints.website import router as website_router
from app.api.v1.endpoints.website import admin_router as website_admin_router

router = APIRouter()
router.include_router(announcements_router)
router.include_router(agent_router)
router.include_router(agent_profiles_router)
router.include_router(auth_router)
router.include_router(credential_proxy_router)
router.include_router(dashboard_router)
router.include_router(email_router)
router.include_router(external_systems_admin_router)
router.include_router(integrations_router)
router.include_router(files_router)
router.include_router(health_router)
router.include_router(memory_router)
router.include_router(skills_router)
router.include_router(suggest_router)
router.include_router(tool_config_router)
router.include_router(users_router)
router.include_router(video_router)
router.include_router(website_router)
router.include_router(website_admin_router)
