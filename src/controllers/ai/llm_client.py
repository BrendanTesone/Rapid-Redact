"""LLM client interface for CCI detection using LiteLLM."""

import json
import logging
import re
from typing import Any, Protocol, TypedDict

from litellm import completion

from src.config import AIAPIConfig
from src.controllers.ai import prompts
from src.core.state.ai_state import CCILibraryItem

logger = logging.getLogger(__name__)


class DocumentContext(TypedDict, total=False):
    doc_title: str
    doc_type: str
    toc_summary: str
    title_page_text: str
    toc_text: str
    summary: str
    compound_name: str
    table_inventory: str


class _ChunkInfoRequired(TypedDict):
    file_name: str
    start_page: int
    end_page: int
    section_title: str


class ChunkInfo(_ChunkInfoRequired, total=False):
    doc_context: "DocumentContext | None"


class Detection(TypedDict, total=False):
    text: str
    page: int
    confidence: str
    category: str
    justification: str
    context: str
    file_name: str
    file_path: str


class LLMClient(Protocol):
    def test_authentication(self) -> bool: ...

    def detect_cci(
        self, pdf_text: str, cci_library: list[CCILibraryItem], chunk_info: ChunkInfo
    ) -> list[Detection]: ...

    def summarize_document(
        self,
        title_page_text: str,
        toc_text: str,
        pdf_metadata_title: str,
    ) -> "dict[str, str] | None": ...


class LiteLLMClient:
    """
    LLM client using LiteLLM for multi-provider AI support.

    Supports any provider that LiteLLM supports:
    - Anthropic (Claude)
    - OpenAI (GPT)
    - Google (Gemini)
    - Azure OpenAI
    - AWS Bedrock
    - And many more...

    Configuration via AIAPIConfig:
    - api_key: Your API key for the provider
    - base_url: (Optional) Custom endpoint or LiteLLM proxy URL
    - model: Model name (e.g., "claude-opus-4.6", "gpt-4", "gemini-pro")
    """

    def __init__(self, config: AIAPIConfig) -> None:
        self.api_key = config.api_key
        self.base_url = config.base_url if config.base_url else None
        self.model = config.model

    def test_authentication(self) -> bool:
        try:
            completion(
                model=self.model,
                messages=[{"role": "user", "content": "test"}],
                api_key=self.api_key,
                base_url=self.base_url,
                max_tokens=10,
            )
            return True
        except Exception as e:
            logger.error(f"Authentication test failed: {e}")
            return False

    def chat(self, prompt: str, max_tokens: int = 8192) -> str:
        response = completion(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            api_key=self.api_key,
            base_url=self.base_url,
            max_tokens=max_tokens,
            temperature=0.0,
        )
        return str(response.choices[0].message.content)

    def _call_api(self, prompt: str, max_tokens: int = 8192) -> object:
        """Used by amendment matching for advanced response parsing."""
        return completion(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            api_key=self.api_key,
            base_url=self.base_url,
            max_tokens=max_tokens,
            temperature=0.0,
        )

    def detect_cci(
        self, pdf_text: str, cci_library: list[CCILibraryItem], chunk_info: ChunkInfo
    ) -> list[Detection]:
        prompt = prompts.build_cci_detection_prompt(pdf_text, cci_library, chunk_info)
        response_text = self.chat(prompt)
        return self._parse_detection_response(response_text)

    def summarize_document(
        self,
        title_page_text: str,
        toc_text: str,
        pdf_metadata_title: str,
    ) -> "dict[str, str] | None":
        prompt = prompts.build_document_summary_prompt(
            title_page_text, toc_text, pdf_metadata_title
        )

        if not prompt.strip():
            return None

        response_text = self.chat(prompt, max_tokens=512)
        json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(1)

        return json.loads(response_text)

    def _parse_detection_response(self, response_text: str) -> list[Detection]:
        json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(1)

        detections_raw: list[dict[str, Any]] = json.loads(response_text)

        detections: list[Detection] = []
        for det in detections_raw:
            detection: Detection = {
                "text": str(det.get("text", "")),
                "page": int(det.get("page", 0)),
                "confidence": str(det.get("confidence", "medium")),
                "category": str(det.get("category", "unknown")),
                "justification": str(det.get("justification", "")),
                "context": str(det.get("context", "")),
            }
            detections.append(detection)

        return detections
