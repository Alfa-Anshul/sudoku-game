from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..schemas import ToolExecuteRequest, ToolExecuteResponse
from ..services.tool_service import TOOLS, execute_tool

router = APIRouter(tags=["tools"])


@router.get("/tools")
async def list_tools(_: object = Depends(get_current_user)):
    return {"tools": TOOLS}


@router.post("/tool/execute", response_model=ToolExecuteResponse)
async def execute_tool_route(
    payload: ToolExecuteRequest,
    user: object = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ToolExecuteResponse:
    try:
        result = await execute_tool(payload.tool_name, payload.input, db, getattr(user, "id", None))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Tool execution failed: {exc}") from exc

    return ToolExecuteResponse(ok=True, result=result)
