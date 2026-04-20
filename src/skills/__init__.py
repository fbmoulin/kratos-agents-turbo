"""Skill functions for the legal document processing system.

This module defines a few simple "skills" that can be composed by
agents to process legal documents. Skills are small, focused
functions that each perform a specific task. By composing skills in
an agent, we can build up more complex behaviour without coupling
our core logic to a monolithic function.

In a production environment these skills might call external AI
services, perform sophisticated natural language processing, or
integrate with third‑party systems. For this repository, we
implement lightweight heuristics so that the system remains
functional even without network access.

The key skills defined here are:

* ``extract_text_from_pdf`` – pulls a small amount of text from the
  first couple of pages of a PDF. This is used by the classifier.
* ``classify_document`` – classifies a document into broad legal
  categories based on simple keyword matching.
* ``generate_decision`` – produces a plain‑language decision or
  despacho based on the classification and the caller's message.

Agents can call these skills directly, or you can expose them via
an MCP server for consumption by other agents.
"""

from __future__ import annotations

import io

import pdfplumber

HEALTH_KEYWORDS = {
    "plano de saúde",
    "plano de saude",
    "medicamento",
    "tratamento",
}

CRIMINAL_KEYWORDS = {
    "acusado",
    "acusada",
    "audiência de custódia",
    "audiencia de custodia",
    "crime",
    "custódia",
    "custodia",
    "denuncia",
    "denúncia",
    "flagrante",
    "habeas corpus",
    "pena",
    "penal",
    "prisão",
    "prisao",
    "preventiva",
    "réu",
    "reu",
    "tráfico",
    "trafico",
}


def extract_text_from_pdf(file_bytes: bytes, max_pages: int = 2) -> str:
    """Extract text from the first pages of a PDF.

    For classification we don't need the entire document; reading just
    the first couple of pages keeps processing lightweight. If the
    document does not contain extractable text (e.g. scanned
    documents), an empty string is returned.

    :param file_bytes: raw bytes of a PDF file
    :param max_pages: maximum number of pages to read
    :returns: extracted text or empty string
    """
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages[:max_pages]:
                page_text = page.extract_text() or ""
                text += page_text + "\n"
    except Exception:
        # If parsing fails, fall back to empty string
        return ""
    return text


def classify_document(text: str) -> str:
    """Classify a document into a high‑level legal category.

    This simple heuristic looks for keywords in the document text to
    determine whether the case relates to health (planos de saúde,
    medicamentos), criminal matters, or general civil matters. If no
    keywords are found the default category is ``"Cível"``.

    :param text: plain text extracted from the document
    :returns: a string representing the category
    """
    text_lower = text.lower()
    if any(keyword in text_lower for keyword in HEALTH_KEYWORDS):
        return "Saúde"
    if any(keyword in text_lower for keyword in CRIMINAL_KEYWORDS):
        return "Penal"
    return "Cível"


def generate_decision(classification: str, message: str, task_type: str = "despacho") -> str:
    """Generate a simple decision or despacho based on classification.

    The generated text is intentionally minimalist. It echoes the
    classification and the user's instruction message, and
    encourages the reviewer to adjust the output as necessary. In
    production this function would call an LLM or more advanced
    pipeline.

    :param classification: category returned by ``classify_document``
    :param message: user message/instruction provided at task
    :returns: generated decision text
    """
    preamble = (
        f"Processo classificado como {classification}. "
        f"Tipo de saída solicitado: {task_type}. "
        "A seguir, segue uma minuta gerada automaticamente. "
        "Por favor, revise e ajuste conforme necessário:\n\n"
    )
    return preamble + message


__all__ = [
    "extract_text_from_pdf",
    "classify_document",
    "generate_decision",
]
