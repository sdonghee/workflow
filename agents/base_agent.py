"""
에이전트 기반 클래스
Claude API (Anthropic) 클라이언트 + 자동 폴백 로직 공통 제공
"""
import json
import logging
import re
import sys
import os
from typing import Optional, Union, List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anthropic
from config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

# ─── Claude 모델 ID ────────────────────────────────────────────
HERMES_405B = "claude-sonnet-4-6"   # 기존 Hermes 역할 → Claude Sonnet
LLAMA_70B   = "claude-haiku-4-5"    # 기존 Llama 역할  → Claude Haiku (폴백)
GEMMA_27B   = "claude-haiku-4-5"    # 기존 Gemma 역할  → Claude Haiku (폴백)


class BaseAgent:
    """Claude API 기반 에이전트 공통 기반 클래스"""

    PRIMARY_MODEL   = HERMES_405B
    FALLBACK_MODELS = [LLAMA_70B]

    def __init__(self, model: str = None, fallback_models: list = None):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.primary_model   = model or self.PRIMARY_MODEL
        self.fallback_models = fallback_models if fallback_models is not None else self.FALLBACK_MODELS

    # ── 핵심 메서드: 모델 폴백 포함 텍스트 응답 ──────────────────
    def chat(
        self,
        messages: list,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> Optional[str]:
        """
        요청 전송. 실패 시 fallback_models 순서대로 재시도.
        Returns: 응답 텍스트 또는 None
        """
        # system 메시지 분리 (Anthropic API 형식)
        system_prompt = None
        user_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_prompt = msg["content"]
            else:
                user_messages.append(msg)

        models = [self.primary_model] + self.fallback_models

        for model in models:
            try:
                kwargs = dict(
                    model=model,
                    max_tokens=max_tokens,
                    messages=user_messages,
                )
                if system_prompt:
                    kwargs["system"] = system_prompt

                resp = self.client.messages.create(**kwargs)
                text = resp.content[0].text if resp.content else None
                if text and text.strip():
                    logger.debug(f"[{self.__class__.__name__}] 응답 성공 ({model})")
                    return text.strip()
            except Exception as e:
                logger.warning(f"[{self.__class__.__name__}] {model} 실패: {e}")

        logger.error(f"[{self.__class__.__name__}] 모든 모델({models}) 실패")
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
            # 첫 번째 JSON 객체/배열 추출
            raw = re.search(r"([\[{].*[\]}])", text, re.DOTALL)
            if raw:
                text = raw.group(1)

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"[{self.__class__.__name__}] JSON 파싱 실패: {e}\n원문 앞부분: {text[:200]}")
            return None
