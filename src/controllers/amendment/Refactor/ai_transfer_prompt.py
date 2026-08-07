from __future__ import annotations

import json
import re

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.state.app_state import RedactionBox


def build_amendment_match_prompt(
    text_boxes: list[RedactionBox],
    dest_text: str,
    dest_start: int,
    dest_end: int,
) -> str:
    """Build prompt for AI amendment matching."""

    source_items = []
    for idx, box in enumerate(text_boxes, 1):
        text = box.match
        context = box.context

        if context and len(context) > len(text):
            text_pos = context.find(text)
            if text_pos != -1:
                before = context[:text_pos]
                after = context[text_pos + len(text) :]
                source_items.append(f'{idx}. "...{before}[{text}]{after}..."')
            else:
                source_items.append(f'{idx}. "{text}" (Context: {context})')
        else:
            source_items.append(f'{idx}. "{text}"')

    source_section = "\n".join(source_items)

    print(
        f"      Prompt: {len(text_boxes)} source items, {len(dest_text)} chars of dest text"
    )

    prompt = f"""TASK: Match redacted content between two document versions.

SOURCE REDACTIONS (from redline PDF):
{source_section}

Note: Text in [brackets] is the redacted content. Text before and after [brackets] is context.

DESTINATION DOCUMENT (pages {dest_start + 1}-{dest_end + 1}):
{dest_text}

INSTRUCTIONS:
1. Find each source redaction in the destination document.
2. The text can be the same or can have small changes.
3. The text must have the same meaning.
4. The text must be in the page range shown above.
5. If a matched region is part of a larger phrase that represents the same logical entity after amendment, expand the redline boundaries to include the entire transformed entity.
6. Prefer complete semantic coverage over exact character-level alignment.

OUTPUT RULES:
Put only the redacted text in "target_text", not the context.
Example: Source shows "...administered [EXAMPLE REDACTION HERE] once daily...".
You must return "EXAMPLE REDACTION HERE" only in "target_text".

OUTPUT FORMAT:
{{
  "matches": [
    {{
      "source_text": "text from source (no context)",
      "target_text": "text from destination (no context)",
      "page": page_number
    }}
  ]
}}

Return {{"matches": []}} if you find no matches."""

    return prompt


def parse_ai_response(response: object) -> list[dict[str, object]]:
    """Parse AI response into list of matches."""
    response_text = response.get("data", {}).get("response", "")  # type: ignore[attr-defined]
    json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
    if not json_match:
        return []

    parsed = json.loads(json_match.group(0))
    return parsed.get("matches", [])  # type: ignore[no-any-return]
