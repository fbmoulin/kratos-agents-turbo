"""Legal agent implementation for judicial document processing.

This module defines a minimal agent class that orchestrates the
execution of various skills. The ``LegalAgent`` is responsible for
combining simple skill functions into a coherent workflow: it
extracts text from an uploaded PDF, classifies the document
according to heuristic rules, and then generates a basic decision
based on a user‑provided instruction.

While the current implementation is intentionally lightweight, the
agent pattern here mirrors how one might structure interactions with
managed agents or other complex orchestration frameworks. By
encapsulating the logic in an agent class, you can later swap out
skill implementations, add more steps, or integrate with an MCP
server without changing the surrounding infrastructure.
"""

from __future__ import annotations

from typing import Optional

from src.skills import (
    extract_text_from_pdf,
    classify_document,
    generate_decision,
)


class LegalAgent:
    """An agent that processes a legal document using a sequence of skills."""

    def __init__(self, file_bytes: bytes, message: str) -> None:
        self.file_bytes = file_bytes
        self.message = message

    def run(self) -> str:
        """Execute the agent workflow and return a decision text.

        The workflow is simple: extract text from the PDF, classify the
        document, and generate a decision. In a real deployment the
        workflow could involve calling external services, retrieving
        precedent information, or invoking other agents via MCP.

        :returns: generated decision text
        """
        # Extract text for classification
        text = extract_text_from_pdf(self.file_bytes)
        # Classify the document
        classification = classify_document(text)
        # Generate decision
        decision = generate_decision(classification, self.message)
        return decision


__all__ = ["LegalAgent"]