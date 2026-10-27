"""After submission, the linked request is the source of processing status."""

from mysite.database.chat_models import ChatBookingLink
from mysite.database.models import TravelRequest


def requests_for_selections(db, selections):
    """Get the latest request for every session in one bounded query."""
    from sqlalchemy import func, select

    session_ids = {row.session_id for row in selections if row.session_id}
    if not session_ids:
        return {}
    ranked = (
        select(
            ChatBookingLink.session_id,
            ChatBookingLink.client_id,
            ChatBookingLink.request_id,
            func.row_number()
            .over(
                partition_by=(ChatBookingLink.session_id, ChatBookingLink.client_id),
                order_by=ChatBookingLink.id.desc(),
            )
            .label('position'),
        )
        .where(ChatBookingLink.session_id.in_(session_ids))
        .subquery()
    )
    rows = (
        db.query(ranked.c.session_id, ranked.c.client_id, TravelRequest)
        .join(TravelRequest, TravelRequest.id == ranked.c.request_id)
        .filter(ranked.c.position == 1)
        .all()
    )
    return {(sid, client_id): request for sid, client_id, request in rows}


def linked_request(db, selection, *, for_update=False):
    if not selection.session_id:
        return None
    query = (
        db.query(TravelRequest)
        .join(ChatBookingLink, ChatBookingLink.request_id == TravelRequest.id)
        .filter(
            ChatBookingLink.session_id == selection.session_id,
            ChatBookingLink.client_id == selection.client_id,
        )
        .order_by(ChatBookingLink.id.desc())
    )
    if for_update:
        query = query.populate_existing().with_for_update(of=TravelRequest)
    return query.first()


def processing_status(selection, request):
    if request is None:
        return selection.status
    status = getattr(request.status, 'value', request.status)
    return 'in_progress' if status == 'new' else status
