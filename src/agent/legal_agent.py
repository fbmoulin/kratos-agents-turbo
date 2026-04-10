"""Legal agent implementation for judicial document processing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.agent.registry import AgentDefinition

from src.skills import (
    classify_document,
    extract_text_from_pdf,
    generate_decision,
)


@dataclass(frozen=True)
class AgentExecutionResult:
    result_text: str
    metadata: dict[str, object]


class LegalAgent:
    """Process a legal document using a small sequence of reusable skills."""

    def __init__(self, definition: AgentDefinition) -> None:
        self.definition = definition

    def run(
        self,
        *,
        file_bytes: bytes,
        message: str,
        task_type: str,
        emit_step: Callable[[str, str, dict[str, object]], None] | None = None,
    ) -> AgentExecutionResult:
        max_pages = int(self.definition.config.get("max_pages", 2))
        text = extract_text_from_pdf(file_bytes, max_pages=max_pages)
        if emit_step:
            emit_step(
                "extract_text",
                "extract_text_from_pdf",
                {"characters": len(text), "max_pages": max_pages},
            )

        classification = classify_document(text)
        if emit_step:
            emit_step(
                "classify_document",
                "classify_document",
                {"classification": classification},
            )

        decision = generate_decision(
            classification=classification,
            message=message,
            task_type=task_type,
        )
        if emit_step:
            emit_step(
                "generate_decision",
                "generate_decision",
                {"classification": classification, "task_type": task_type},
            )

        return AgentExecutionResult(
            result_text=decision,
            metadata={
                "classification": classification,
                "extracted_characters": len(text),
                "agent_id": self.definition.id,
            },
        )


__all__ = ["AgentExecutionResult", "LegalAgent"]
