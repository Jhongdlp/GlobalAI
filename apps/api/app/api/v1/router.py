from fastapi import APIRouter

from app.api.v1 import assessments, auth, health, practice, progress, stimuli, teacher

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(assessments.router)
api_router.include_router(progress.router)
api_router.include_router(stimuli.router)
api_router.include_router(practice.router)
api_router.include_router(teacher.router)
