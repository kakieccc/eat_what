from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.choices import router as choices_router
from app.api.routes.decision_runs import router as decision_runs_router
from app.api.routes.discovery_sessions import router as discovery_sessions_router
from app.api.routes.health import router as health_router
from app.api.routes.locations import router as locations_router
from app.api.routes.places import router as places_router
from app.api.routes.preferences import router as preferences_router

router = APIRouter(prefix="/api/v2")
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(locations_router)
router.include_router(places_router)
router.include_router(decision_runs_router)
router.include_router(discovery_sessions_router)
router.include_router(choices_router)
router.include_router(preferences_router)
