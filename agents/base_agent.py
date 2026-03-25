"""
에이전트 기반 클래스
OpenRouter 무료 모델 풀 + 순서 지정 폴백 로직 공통 제공

폴백 순서:
  메인 모델 → 지정 폴백 목록 → FREE_POOL 나머지 (순서 고정)
"""
import json
import logging
import re
import sys
import os
from typing import Optional, Union, List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
from config import OPENROUTER_API_KEY

logger = logging.getLogger(__name__)

# ─── OpenRouter 무료 모델 (품질·속도 순 정렬) ───────────────────
HERMES_405B  = "nousresearch/hermes-3-llama-3.1-405b:free"
DEEPSEEK_R1  = "deepseek/deepseek-r1:free"
DEEPSEEK_V3  = "deepseek/deepseek-chat-v3-0324:free"
QWEN_235B    = "qwen/qwen3-235b-a22b:free"
QWEN_72B     = "qwen/qwen3-72b:free"
LLAMA_70B    = "meta-llama/llama-3.3-70b-instruct:free"
GEMMA_27B    = "google/gemma-3-27b-it:free"
MISTRAL_24B  = "mistralai/mistral-small-3.1-24b-instruct:free"
GEMMA_12B    = "google/gemma-3-12b-it:free"
PHI4         = "microsoft/phi-4:free"

# 전체 풀 (우선순위 고정 순서)
FREE_POOL = [
    HERMES_405B,
    DEEPSEEK_R1,
    DEEPSEEK_V3,
    QWEN_235B,
    QWEN_72B,
    LLAMA_70B,
    GEMMA_27B,
    MISTRAL_24B,
    GEMMA_12B,
    PHI4,
]


class BaseAgent:
    """OpenRouter 무료 모델 풀 기반 에이전트 공통 기반 클래스"""

    PRIMARY_MODEL   = HERMES_405B
    FALLBACK_MODELS = [DEEPSEEK_R1, DEEPSEEK_V3, QWEN_235B, QWEN_72B,
                       LLAMA_70B, GEMMA_27B, MISTRAL_24B, GEMMA_12B, PHI4]

    def __init__(self, model: str = None, fallback_models: list = None):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )
        self.primary_model   = model or self.PRIMARY_MODEL
        self.fallback_models = fallback_models if fallback_models is not None else self.FALLBACK_MODELS

    def _build_model_queue(self) -> List[str]:
        """
        시도 순서: 메인 → 지정 폴백 → FREE_POOL 나머지 (순서 고정, 중복 제거).
        """
        queue = [self.primary_model] + self.fallback_models
        seen  = set(queue)
        for m in FREE_POOL:
            if m not in seen:
                queue.append(m)
                seen.add(m)
        return queue

    # ── 핵심 메서드: 모델 폴백 포함 텍스트 응답 ──────────────────
    def chat(
        self,
        messages: list,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> Optional[str]:
        """
        요청 전송. 실패 시 폴백 목록 → FREE_POOL 순으로 재시도.
        Returns: 응답 텍스트 또는 None
        """
        for model in self._build_model_queue():
            try:
                resp = self.client.chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=messages,
                )
                text = resp.choices[0].message.content
                if text and text.strip():
                    logger.info(f"[{self.__class__.__name__}] 응답 성공 ({model})")
                    return text.strip()
            except Exception as e:
                logger.warning(f"[{self.__class__.__name__}] {model} 실패: {e}")

        logger.error(f"[{self.__class__.__name__}] FREE_POOL 전체 실패")
        return None

    # ── JSON 응답 편의 메서드 ─────────────────────────────────────
    def chat_json(self, messages: list, max_tokens: int = 4096) -> Optional[Union[Dict, List]]:
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
            raw = re.search(r"([\[{].*[\]}])", text, re.DOTALL)
            if raw:
                text = raw.group(1)

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"[{self.__class__.__name__}] JSON 파싱 실패: {e}\n원문 앞부분: {text[:200]}")
            return None
