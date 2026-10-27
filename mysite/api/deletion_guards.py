"""Turn references that must be retained into actionable conflict responses."""

from fastapi import HTTPException

from mysite.database.models import Hotel, Tour, Transport
from mysite.database.selection_models import TravelSelection


def protect_selected_item(db, model, identity):
    column = {
        Tour: TravelSelection.tour_id,
        Hotel: TravelSelection.hotel_id,
        Transport: TravelSelection.transport_id,
    }[model]
    if db.query(TravelSelection.id).filter(column == identity).first():
        raise HTTPException(409, 'This item is referenced by a trip; deactivate it instead')
