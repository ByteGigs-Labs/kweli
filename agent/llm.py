"""The model behind the agent. Swappable; tests use a scripted fake."""

from dataclasses import dataclass
from typing import Protocol

from api.config import get_settings


@dataclass(frozen=True)
class Turn:
    blocks: list[dict]

    @property
    def text(self) -> str:
        return "\n".join(b["text"] for b in self.blocks if b.get("type") == "text").strip()

    @property
    def tool_uses(self) -> list[dict]:
        return [b for b in self.blocks if b.get("type") == "tool_use"]


class LLM(Protocol):
    def respond(self, system: str, messages: list[dict], tools: list[dict]) -> Turn: ...


class AnthropicLLM:
    def __init__(self, api_key: str, model: str) -> None:
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key, timeout=45, max_retries=2)
        self.model = model

    @classmethod
    def from_settings(cls) -> "AnthropicLLM | None":
        settings = get_settings()
        if settings.anthropic_api_key is None or not settings.anthropic_api_key.get_secret_value():
            return None
        return cls(settings.anthropic_api_key.get_secret_value(), settings.llm_model)

    def respond(self, system: str, messages: list[dict], tools: list[dict]) -> Turn:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1200,
            temperature=0,
            system=system,
            tools=tools,
            messages=messages,
        )
        blocks = []
        for block in response.content:
            if block.type == "text":
                blocks.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                blocks.append(
                    {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
                )
        return Turn(blocks)
