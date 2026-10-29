"""Lazy Gemini construction. SDK owns bounded network retries; no retry stacking."""

import os
from functools import lru_cache

from ML.config import integer_setting, output_budget


@lru_cache(maxsize=5)
def client(kind):
    from dotenv import load_dotenv
    from langchain_google_genai import ChatGoogleGenerativeAI

    load_dotenv()
    model_name = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
    retries = integer_setting('GEMINI_MAX_RETRIES', 1, 0, 2)
    options = {'max_retries': retries, 'timeout': 30}
    if kind == 'translation':
        return ChatGoogleGenerativeAI(
            model=model_name, temperature=0.3, timeout=15, max_retries=retries
        )
    if kind == 'agent_llm':
        from ML.tools import READ_TOOLS

        return client('llm').bind_tools(READ_TOOLS)
    if kind == 'extractor':
        from ML.schemas import Changes

        return client('extract_llm').with_structured_output(Changes, method='json_schema')
    if kind == 'extract_llm':
        model_name = os.getenv('GEMINI_EXTRACT_MODEL', model_name)
        budget = output_budget('CHAT_EXTRACT_MAX_OUTPUT_TOKENS', 512, 1024)
    elif kind == 'llm':
        budget = output_budget('CHAT_MAX_OUTPUT_TOKENS', 1536, 4096)
    else:
        raise ValueError('Unknown Gemini client kind')
    return ChatGoogleGenerativeAI(
        model=model_name,
        max_output_tokens=budget,
        thinking_config={'thinking_level': os.getenv('GEMINI_THINKING_LEVEL', 'LOW').upper()},
        **options,
    )


class LazyClient:
    def __init__(self, kind):
        self.kind = kind

    def __getattr__(self, name):
        return getattr(client(self.kind), name)
