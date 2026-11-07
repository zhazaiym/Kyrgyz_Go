from datetime import date, datetime
from zoneinfo import ZoneInfo

BISHKEK_TIMEZONE = ZoneInfo('Asia/Bishkek')


def local_today() -> date:
    return datetime.now(BISHKEK_TIMEZONE).date()
