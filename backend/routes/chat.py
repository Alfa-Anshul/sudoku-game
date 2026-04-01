from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import get_settings
from ..database import get_db
from ..models import ChatHistory
from ..schemas import ChatRequest, ChatResponse
from ..services.anthropic_service import anthropic_service
from ..services.local_mcp_service import store_message_record
from ..services.redis_cache import redis_cache
from ..services.tool_service import TOOLS, execute_tool

router = APIRouter(tags=["chat"])
settings = get_settings()


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, user=Depends(get_current_user), db: Session = Depends(get_db)) -> ChatResponse:
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")

    cache_key = f"conversation:{user.id}"
    conversation = redis_cache.get_json(cache_key) or []

    tools = TOOLS

    async def run_tool(name: str, tool_input: dict):
        return await execute_tool(name, tool_input, db, user.id)

    response_text = await anthropic_service.chat_with_tools(
        user_message=payload.message,
        conversation=conversation,
        tools=tools,
        tool_executor=run_tool,
    )

    store_message_record(payload.message, source=f"chat_user:{user.username}")
    store_message_record(response_text, source=f"chat_assistant:{user.username}")

    db.add(ChatHistory(user_id=user.id, role="user", message=payload.message))
    db.add(ChatHistory(user_id=user.id, role="assistant", message=response_text))
    db.commit()

    updated_conversation = conversation + [
        {"role": "user", "content": payload.message},
        {"role": "assistant", "content": response_text},
    ]
    redis_cache.set_json(cache_key, updated_conversation, ttl_seconds=3600)

    return ChatResponse(response=response_text)
