"""
에이전트 기반 클래스
OpenRouter 실제 가용 무료 모델 풀 + 순서 지정 폴백 + 429 재시도 로직
"""
import json
import logging
import re
import sys
import os
import time
from typing import Optional, Union, List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anthropic
from openai import OpenAI
from config import OPENROUTER_API_KEY, ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

# ─── OpenRouter 실제 가용 무료 모델 (2026-03 기준 검증 완료) ────

# 대형 고품질 모델
HERMES_405B     = "nousresearch/hermes-3-llama-3.1-405b:free"
NEMOTRON_120B   = "nvidia/nemotron-3-super-120b-a12b:free"
GPT_OSS_120B    = "openai/gpt-oss-120b:free"
QWEN3_80B       = "qwen/qwen3-next-80b-a3b-instruct:free"
LLAMA_70B       = "meta-llama/llama-3.3-70b-instruct:free"
MINIMAX         = "minimax/minimax-m2.5:free"

# 중형 모델
MISTRAL_24B     = "mistralai/mistral-small-3.1-24b-instruct:free"
GEMMA_27B       = "google/gemma-3-27b-it:free"
DOLPHIN_24B     = "cognitivecomputations/dolphin-mistral-24b-venice-edition:free"
NEMOTRON_30B    = "nvidia/nemotron-3-nano-30b-a3b:free"
QWEN3_CODER     = "qwen/qwen3-coder:free"
ARCEE_LARGE     = "arcee-ai/trinity-large-preview:free"
GLM_45          = "z-ai/glm-4.5-air:free"

# 소형·경량 모델 (폴백 최후순)
GPT_OSS_20B     = "openai/gpt-oss-20b:free"
GEMMA_12B       = "google/gemma-3-12b-it:free"
NEMOTRON_12B    = "nvidia/nemotron-nano-12b-v2-vl:free"
NEMOTRON_9B     = "nvidia/nemotron-nano-9b-v2:free"
STEPFUN         = "stepfun/step-3.5-flash:free"
GEMMA_4B        = "google/gemma-3-4b-it:free"
QWEN3_4B        = "qwen/qwen3-4b:free"

# 전체 풀 (기본 폴백 순서 — 크기·품질 내림차순)
FREE_POOL = [
    HERMES_405B, NEMOTRON_120B, GPT_OSS_120B,
    QWEN3_80B, LLAMA_70B, MINIMAX,
    MISTRAL_24B, GEMMA_27B, DOLPHIN_24B, NEMOTRON_30B,
    QWEN3_CODER, ARCEE_LARGE, GLM_45,
    GPT_OSS_20B, GEMMA_12B, NEMOTRON_12B, NEMOTRON_9B,
    STEPFUN, GEMMA_4B, QWEN3_4B,
]


class BaseAgent:
    """OpenRouter 무료 모델 풀 기반 에이전트 공통 기반 클래스"""

    PRIMARY_MODEL   = HERMES_405B
    FALLBACK_MODELS = [NEMOTRON_120B, GPT_OSS_120B, QWEN3_80B, LLAMA_70B]

    def __init__(self, model: str = None, fallback_models: list = None):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )
        self.primary_model   = model or self.PRIMARY_MODEL
        self.fallback_models = fallback_models if fallback_models is not None else self.FALLBACK_MODELS

    def _build_model_queue(self) -> List[str]:
        """메인 → 지정 폴백 → FREE_POOL 나머지 (순서 고정, 중복 제거)"""
        queue = [self.primary_model] + self.fallback_models
        seen  = set(queue)
        for m in FREE_POOL:
            if m not in seen:
                queue.append(m)
                seen.add(m)
        return queue

    # ── 핵심 메서드: 모델 폴백 + 429 재시도 ──────────────────────
    def chat(
        self,
        messages: list,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> Optional[str]:
        """
        요청 전송.
        - 429 (rate limit): 해당 모델 건너뛰고 다음 모델로
        - 기타 오류: 즉시 다음 모델로
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
                    logger.info(f"[{self.__class__.__name__}] 성공 ({model})")
                    return text.strip()
            except Exception as e:
                err = str(e)
                if "429" in err:
                    logger.warning(f"[{self.__class__.__name__}] rate limit — 다음 모델로: {model}")
                elif "404" in err or "400" in err:
                    logger.warning(f"[{self.__class__.__name__}] 모델 없음 — 건너뜀: {model}")
                else:
                    logger.warning(f"[{self.__class__.__name__}] {model} 실패: {err[:80]}")

        # ── 최종 폴백: Claude API (OpenRouter 전체 실패 시) ──────────
        if ANTHROPIC_API_KEY:
            logger.warning(f"[{self.__class__.__name__}] OpenRouter 전체 실패 → Claude API 폴백 사용")
            try:
                claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
                # system 메시지와 user 메시지 분리
                system_msg = next(
                    (m["content"] for m in messages if m["role"] == "system"), ""
                )
                user_messages = [m for m in messages if m["role"] != "system"]
                resp = claude_client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=min(max_tokens, 8000),
                    system=system_msg if system_msg else anthropic.NOT_GIVEN,
                    messages=user_messages,
                )
                text = resp.content[0].text
                if text and text.strip():
                    logger.info(f"[{self.__class__.__name__}] Claude 폴백 성공")
                    return text.strip()
            except Exception as e:
                logger.error(f"[{self.__class__.__name__}] Claude 폴백도 실패: {e}")

        logger.error(f"[{self.__class__.__name__}] 모든 모델 실패")
        return None

    # ── JSON 응답 편의 메서드 ─────────────────────────────────────
    def chat_json(self, messages: list, max_tokens: int = 4096) -> Optional[Union[Dict, List]]:
        text = self.chat(messages, max_tokens)
        if not text:
            return None

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
            logger.error(f"[{self.__class__.__name__}] JSON 파싱 실패: {e}\n원문: {text[:200]}")
            return None
