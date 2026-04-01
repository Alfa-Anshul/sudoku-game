from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..services.local_mcp_service import run_local_mcp_tool

router = APIRouter(tags=["mcp"])


class JsonRpcRequest(BaseModel):
    jsonrpc: str = Field(default="2.0")
    id: Any = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/mcp")
def mcp(payload: JsonRpcRequest) -> dict[str, Any]:
    method = payload.method
    params = payload.params or {}

    if method in {"tools/call", "tool.call", "call_tool"}:
        tool_name = params.get("name") or params.get("tool") or params.get("tool_name")
        arguments = params.get("arguments") or params.get("input") or {}
    else:
        tool_name = method
        arguments = params

    if not isinstance(tool_name, str) or not tool_name:
        return {
            "jsonrpc": "2.0",
            "id": payload.id,
            "error": {
                "code": -32602,
                "message": "Invalid params: missing tool name",
            },
        }

    try:
        result = run_local_mcp_tool(tool_name, arguments if isinstance(arguments, dict) else {})
    except ValueError as exc:
        return {
            "jsonrpc": "2.0",
            "id": payload.id,
            "error": {
                "code": 400,
                "message": str(exc),
            },
        }

    return {
        "jsonrpc": "2.0",
        "id": payload.id,
        "result": result,
    }
