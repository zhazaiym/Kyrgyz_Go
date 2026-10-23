from fastapi import APIRouter, HTTPException


booking_router = APIRouter(prefix="/bookings", tags=["Bookings"])


def require_chat_booking():
    raise HTTPException(410, detail={
        'code': 'booking_requires_chat',
        'message': 'Для бронирования откройте чат, заполните данные и подтвердите заявку.',
        'chat_session_url': '/chat/session',
    })


@booking_router.post("/", include_in_schema=False)
def create_booking():
    require_chat_booking()
