"""Reserve translation provider quota atomically across all API workers."""

import os

from ML.errors import AIError
from mysite.api.rate_limit import consume_rate_limit


def reserve_translation_call():
    maximum = int(os.getenv('GEMINI_REQUESTS_PER_MINUTE', '10'))
    if not 1 <= maximum <= 10000:
        raise RuntimeError('GEMINI_REQUESTS_PER_MINUTE must be between 1 and 10000')
    count, _ = consume_rate_limit(
        'gemini-translations', 'provider', max_requests=maximum, window_seconds=60
    )
    if count > maximum:
        raise AIError('ai_rate_limit')
