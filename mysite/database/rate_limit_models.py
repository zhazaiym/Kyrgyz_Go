from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from mysite.database.db import Base


class RateLimitCounter(Base):
    __tablename__ = "rate_limit_counters"
    __table_args__ = (
        Index("ix_rate_limit_counters_window_start", "window_start"),
    )

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[int] = mapped_column(Integer, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False)
