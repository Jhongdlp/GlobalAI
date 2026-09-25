from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.schemas.progress import ProgressOut
from app.services import progress_service

router = APIRouter(tags=["progress"])


@router.get("/me/progress")
async def my_progress(user: CurrentUser, session: SessionDep) -> ProgressOut:
    return await progress_service.get_progress(session, user)
