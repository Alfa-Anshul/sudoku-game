import json
from typing import Any, Awaitable, Callable

from anthropic import AsyncAnthropic

from ..config import get_settings

settings = get_settings()


class AnthropicService:
    def __init__(self) -> None:
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def chat_with_tools(
        self,
        user_message: str,
        conversation: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
    ) -> str:
        messages = conversation + [{"role": "user", "content": user_message}]

        for _ in range(5):
            response = await self.client.messages.create(
                model=settings.anthropic_model,
                max_tokens=1000,
                messages=messages,
                tools=tools,
            )

            assistant_text_parts: list[str] = []
            tool_uses: list[Any] = []

            for block in response.content:
                if block.type == "text":
                    assistant_text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_uses.append(block)

            if not tool_uses:
                return "\n".join(part for part in assistant_text_parts if part).strip()

            assistant_content = [
                {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
                for block in tool_uses
            ]
            messages.append({"role": "assistant", "content": assistant_content})

            tool_results = []
            for tool_use in tool_uses:
                result = await tool_executor(tool_use.name, dict(tool_use.input or {}))
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": json.dumps(result),
                    }
                )

            messages.append({"role": "user", "content": tool_results})

        return "Tool loop limit reached before final response."


anthropic_service = AnthropicService()
