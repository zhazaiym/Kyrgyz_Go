"""Calendar dates for the company's fixed UTC+6 Bishkek timezone."""

from datetime import datetime, timedelta, timezone

BISHKEK = timezone(timedelta(hours=6), name='Asia/Bishkek')


def bishkek_today(now=None):
    return (now or datetime.now(timezone.utc)).astimezone(BISHKEK).date()
