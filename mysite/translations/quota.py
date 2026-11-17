"""Reserve translation provider quota atomically across all API workers."""

from ML.errors import AIError
from mysite.api.rate_limit import consume_rate_limit
from mysite.settings import number


def reserve_translation_call():
    maximum = number('GEMINI_REQUESTS_PER_MINUTE')
    count, _ = consume_rate_limit(
        'gemini-translations', 'provider', max_requests=maximum, window_seconds=60
    )
    if count > maximum:
        raise AIError('ai_rate_limit')
