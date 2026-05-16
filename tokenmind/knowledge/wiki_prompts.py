"""LLM prompts for compiling raw text into Wiki pages."""
from __future__ import annotations


def build_compile_system_prompt(language: str = "zh") -> str:
    return (
        "You are a knowledge base curator. Given raw source text, you produce a strict JSON object describing:\n"
        "  - source_summary: { title, summary (<=80 words), key_points (list of 3-6) }\n"
        "  - entities: list of { title, type (concept|tool|person|project|other), summary (<=40 words),\n"
        "      content (Markdown, <=300 words), aliases (list), links (list of related entity/topic titles) }\n"
        "  - topics: list of { title, summary (<=40 words), content (Markdown), links (list of entity/topic titles) }\n"
        "Use [[title]] inline to link to other pages. Reuse existing page titles when they match the same concept.\n"
        "Output language: " + ("Chinese" if language == "zh" else "English") + ".\n"
        "Output ONLY a valid JSON object. No prose, no markdown code fences."
    )


def build_compile_user_prompt(
    *,
    purpose: str,
    existing_titles: list[str],
    source_title: str,
    source_text: str,
    max_source_chars: int = 8000,
) -> str:
    text = source_text.strip()
    if len(text) > max_source_chars:
        text = text[:max_source_chars] + "\n...[truncated]"
    existing = ", ".join(f"[[{t}]]" for t in existing_titles[:60]) or "(none)"
    return (
        f"# Knowledge base purpose\n{purpose}\n\n"
        f"# Existing page titles (reuse when applicable)\n{existing}\n\n"
        f"# Source title\n{source_title}\n\n"
        f"# Source text\n{text}\n\n"
        "Return the JSON object now."
    )
