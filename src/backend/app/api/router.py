from __future__ import annotations

from fastapi import APIRouter

from app.api.errors.responses import error_responses
from app.api.routes.health import router as health_router
from app.modules.auth.router import router as auth_router
from app.modules.choice.router import router as choices_router
from app.modules.decision.router import router as decision_runs_router
from app.modules.history.router import router as discovery_sessions_router
from app.modules.location.router import router as locations_router
from app.modules.places.router import router as places_router
from app.modules.preferences.router import router as preferences_router

router = APIRouter(prefix="/api/v2", responses=error_responses(500))
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(locations_router)
router.include_router(places_router)
router.include_router(decision_runs_router)
router.include_router(discovery_sessions_router)
router.include_router(choices_router)
router.include_router(preferences_router)
