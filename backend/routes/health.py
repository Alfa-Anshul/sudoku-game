from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..schemas import HealthResponse
from ..services.tool_service import TOOLS

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="backend")


@router.get("/health/tools")
async def tools_check() -> dict:
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=500, detail="Anthropic is not configured")

    return {
        "message": "Tools are ready",
        "tool_count": len(TOOLS),
        "anthropic": "configured",
    }
