from fastapi import APIRouter

from app import __version__
from app.api.deps import SettingsDep
from app.schemas.health import HealthRead

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthRead, summary="Liveness probe")
async def health(settings: SettingsDep) -> HealthRead:
    return HealthRead(
        status="ok",
        app_name=settings.app_name,
        version=__version__,
        environment=settings.environment,
    )
