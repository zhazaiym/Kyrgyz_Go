from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mysite.database.db import Base
from mysite.database.token_utils import utcnow


class TravelSelection(Base):
    __tablename__ = 'travel_selections'
    __table_args__ = (UniqueConstraint('session_id', name='uq_travel_selections_session_id'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    client_id: Mapped[int] = mapped_column(
        ForeignKey('chat_clients.id'), nullable=False, index=True
    )

    tour_id: Mapped[int | None] = mapped_column(ForeignKey('tours.id'), nullable=True)

    hotel_id: Mapped[int | None] = mapped_column(ForeignKey('hotels.id'), nullable=True)

    transport_id: Mapped[int | None] = mapped_column(ForeignKey('transports.id'), nullable=True)

    session_id: Mapped[str | None] = mapped_column(ForeignKey('chat_sessions.id'), nullable=True)

    status: Mapped[str] = mapped_column(String(30), default='draft', nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
