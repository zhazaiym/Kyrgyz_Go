from sqlalchemy import Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from mysite.database.db import Base


class RateLimitCounter(Base):
    __tablename__ = 'rate_limit_counters'
    __table_args__ = (
        Index('ix_rate_limit_counters_window_start', 'window_start'),
        Index('ix_rate_limit_counters_scope_account', 'scope', 'account_id'),
    )

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''"))
    account_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    window_start: Mapped[int] = mapped_column(Integer, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False)
