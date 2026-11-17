from datetime import datetime

from sqlalchemy import (CheckConstraint, DateTime, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mysite.database.db import Base
from mysite.database.token_utils import utcnow


class TourReview(Base):
    __tablename__ = 'tour_reviews'
    __table_args__ = (
        UniqueConstraint('tour_id', 'client_id', name='uq_tour_reviews_tour_client'),
        CheckConstraint('rating BETWEEN 1 AND 5', name='ck_tour_reviews_rating_range'),
        CheckConstraint(
            "status IN ('pending', 'published', 'rejected')", name='ck_tour_reviews_status'
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tour_id: Mapped[int] = mapped_column(
        ForeignKey('tours.id', ondelete='CASCADE'), nullable=False, index=True
    )
    client_id: Mapped[int] = mapped_column(
        ForeignKey('chat_clients.id', ondelete='CASCADE'), nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # A review is shown on the site and counted in the rating only once a manager publishes it.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default='pending', server_default='pending', index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    tour = relationship('Tour')
