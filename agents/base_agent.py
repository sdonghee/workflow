"""
에이전트 기반 클래스
OpenRouter API 클라이언트 + 자동 폴백 로직 공통 제공
"""
import json
import logging
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
from config import OPENROUTER_API_KEY

logger = logging.getLogger(__name__)

# ─── OpenRouter 무료 모델 ID ────────────────────────────────────
HERMES_405B = "nousresearch/hermes-3-llama-3.1-405b:free"
LLAMA_70B   = "meta-llama/llama-3.3-70b-instruct:free"
GEMMA_27B   = "google/gemma-3-27b-it:free"


class BaseAgent:
    """OpenRouter 기반 에이전트 공통 기반 클래스"""

    PRIMARY_MODEL   = HERMES_405B
    FALLBACK_MODELS = [LLAMA_70B, GEMMA_27B]

    def __init__(self, model: str = None, fallback_models: list = None):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )
        self.primary_model   = model or self.PRIMARY_MODEL
        self.fallback_models = fallback_models or self.FALLBACK_MODELS

    # ── 핵심 메서드: 모델 폴백 포함 텍스트 응답 ──────────────────
    def chat(
        self,
        messages: list,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str | None:
        """
        요청 전송. 실패 시 fallback_models 순서대로 재시도.
        Returns: 응답 텍스트 또는 None
        """
        models = [self.primary_model] + self.fallback_models

        for model in models:
            try:
                resp = self.client.chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=messages,
                )
                text = resp.choices[0].message.content
                if text and text.strip():
                    logger.debug(f"[{self.__class__.__name__}] 응답 성공 ({model})")
                    return text.strip()
            except Exception as e:
                logger.warning(f"[{self.__class__.__name__}] {model} 실패: {e}")

        logger.error(f"[{self.__class__.__name__}] 모든 모델({models}) 실패")
        return None

    # ── JSON 응답 편의 메서드 ─────────────────────────────────────
    def chat_json(self, messages: list, max_tokens: int = 4096) -> dict | list | None:
        """
        JSON 응답 요청. ```json 펜스 및 순수 { } / [ ] 모두 처리.
        """
        text = self.chat(messages, max_tokens)
        if not text:
            return None

        # ```json ... ``` 블록 우선 추출
        fence = re.search(r"```json\s*([\[{].*?[\]}])\s*```", text, re.DOTALL)
        if fence:
            text = fence.group(1)
        else:
            # 첫 번째 JSON 객체/배열 추출
            raw = re.search(r"([\[{].*[\]}])", text, re.DOTALL)
            if raw:
                text = raw.group(1)

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"[{self.__class__.__name__}] JSON 파싱 실패: {e}\n원문 앞부분: {text[:200]}")
            return None
