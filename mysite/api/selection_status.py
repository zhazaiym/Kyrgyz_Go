"""After submission, the linked request is the source of processing status."""

from fastapi import HTTPException

from mysite.database.chat_models import ChatBookingLink
from mysite.database.models import TravelRequest
from mysite.database.request_status import validate_status_transition


def require_status_transition(current, proposed):
    try:
        validate_status_transition(current, proposed)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


def requests_for_selections(db, selections):
    """Load direct requests by selection and chat requests by session in bounded queries."""
    from sqlalchemy import func, select

    selection_ids = {row.id for row in selections}
    session_ids = {row.session_id for row in selections if row.session_id}
    requests = {}
    if selection_ids:
        requests.update(
            (request.selection_id, request)
            for request in db.query(TravelRequest)
            .filter(TravelRequest.selection_id.in_(selection_ids))
            .all()
        )
    if session_ids:
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
        requests.update({(sid, client_id): request for sid, client_id, request in rows})
    return requests


def linked_request(db, selection, *, for_update=False):
    direct_query = db.query(TravelRequest).filter(TravelRequest.selection_id == selection.id)
    if for_update:
        direct_query = direct_query.populate_existing().with_for_update()
    direct = direct_query.first()
    if direct is not None:
        return direct
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
