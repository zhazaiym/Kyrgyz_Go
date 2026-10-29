"""Safe provider errors, independent of HTTP and WebSocket transports."""

import asyncio

import httpx
from google.genai.errors import APIError
from langchain_core.exceptions import ModelError
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError

PROVIDER_ERRORS = (APIError, ModelError, ChatGoogleGenerativeAIError, httpx.HTTPError, OSError)

MESSAGES = {
    'ai_rate_limit': 'Лимит AI временно исчерпан. Попробуйте позже.',
    'ai_unavailable': 'AI-консультант временно недоступен. Попробуйте позже.',
    'ai_timeout': 'Ответ занимает слишком много времени. Попробуйте ещё раз.',
    'ai_blocked': 'AI не смог ответить на это сообщение. Попробуйте переформулировать запрос.',
    'ai_invalid_response': 'AI вернул некорректный ответ. Попробуйте ещё раз.',
    'internal_error': 'Не удалось обработать запрос. Попробуйте ещё раз.',
}


class AIError(RuntimeError):
    def __init__(self, code, diagnostic=None):
        self.code = code
        self.message = MESSAGES[code]
        # Diagnostic must be static application text, never provider/customer content.
        super().__init__(diagnostic or code)


def classify_error(error):
    """Inspect bounded cause chains using SDK status fields, never message matching."""
    seen = set()
    current = error
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        if isinstance(current, AIError):
            return current
        if isinstance(current, (asyncio.TimeoutError, httpx.TimeoutException)):
            return AIError('ai_timeout')
        status = getattr(current, 'code', None)
        if callable(status):
            status = status()
        response = getattr(current, 'response', None)
        status = status if isinstance(status, int) else getattr(response, 'status_code', None)
        if status == 429:
            return AIError('ai_rate_limit')
        if status in (408, 504):
            return AIError('ai_timeout')
        if isinstance(status, int) and (status in (400, 401, 403, 404) or status >= 500):
            return AIError('ai_unavailable')
        current = current.__cause__ or current.__context__
    if isinstance(error, PROVIDER_ERRORS):
        return AIError('ai_unavailable')
    return AIError('internal_error')
