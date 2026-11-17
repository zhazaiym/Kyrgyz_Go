"""SDK owns bounded network retries; no retry stacking."""

import os
from functools import lru_cache

import langchain_google_genai

from ML.config import chat_setting, integer_setting
from ML.schemas import Changes, Translations
from ML.tools import READ_TOOLS


@lru_cache(maxsize=6)
def client(kind):
    # The class is looked up at call time: importing this module builds no client.
    chat_model = langchain_google_genai.ChatGoogleGenerativeAI
    model_name = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
    retries = integer_setting('GEMINI_MAX_RETRIES', 1, 0, 2)
    options = {'max_retries': retries, 'timeout': 30}
    if kind == 'translation':
        return chat_model(model=model_name, timeout=15, max_retries=retries)
    if kind == 'translator':
        # include_raw keeps the provider message: its finish reason tells a block from a bad reply.
        return client('translation').with_structured_output(
            Translations, method='json_schema', include_raw=True
        )
    if kind == 'agent_llm':
        return client('llm').bind_tools(READ_TOOLS)
    if kind == 'extractor':
        # include_raw keeps the provider message, which carries the token usage.
        return client('extract_llm').with_structured_output(
            Changes, method='json_schema', include_raw=True
        )
    if kind == 'extract_llm':
        model_name = os.getenv('GEMINI_EXTRACT_MODEL', model_name)
        budget = chat_setting('CHAT_EXTRACT_MAX_OUTPUT_TOKENS')
    elif kind == 'llm':
        budget = chat_setting('CHAT_MAX_OUTPUT_TOKENS')
    else:
        raise ValueError('Unknown Gemini client kind')
    return chat_model(
        model=model_name,
        max_output_tokens=budget,
        thinking_config={'thinking_level': os.getenv('GEMINI_THINKING_LEVEL', 'MINIMAL').upper()},
        **options,
    )


def warm_up():
    """Build the chat clients ahead of the first message, which would otherwise wait for it."""
    client('agent_llm')
    client('extractor')


class LazyClient:
    def __init__(self, kind):
        self.kind = kind

    def __getattr__(self, name):
        return getattr(client(self.kind), name)
