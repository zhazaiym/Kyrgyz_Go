import uvicorn
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dotenv import load_dotenv

load_dotenv()

# ADMIN
from mysite.api.admin import admin_router
from mysite.admin.setup import setup_admin

# OLD KYRGYZGO API
from mysite.api.tour_category import category_router
from mysite.api.tour import tour_router
from mysite.api.country import country_router
from mysite.api.region import region_router
from mysite.api.district import district_router

from mysite.api.hotel import hotel_router
from mysite.api.hotel_image import hotel_image_router

from mysite.api.transport import transport_router
from mysite.api.transport_image import transport_image_router

from mysite.api.helicopter_tour import helicopter_tour_router
from mysite.api.helicopter_image import helicopter_image_router

from mysite.api.trekking import trekking_router
from mysite.api.trekking_image import trekking_image_router
from mysite.api.trekking_program import trekking_program_router

from mysite.api.contact import contact_router
from mysite.api.faq import faq_router
from mysite.api.travel_request import travel_request_router
from mysite.api.booking import booking_router

from mysite.api.about import about_router
from mysite.api.about_section import about_section_router

from mysite.api.tour_image import tour_image_router
from mysite.api.tour_program import tour_program_router
from mysite.api.manager_selection import manager_selection_router
from mysite.api.travel_selection import selection_router
from mysite.api.registration import router as registration_router
from mysite.api.password_reset import router as password_reset_router
# NEW AI CHAT
from mysite.api.client_auth import router as client_auth_router
from mysite.api.chat import chat_router
from mysite.api.chat_ws import router as chat_ws_router


# FASTAPI
app = FastAPI(
    title="KYRGYZGO",
    description="KYRGYZGO Tourism API + AI Travel Assistant",
    version="1.0.0",
)


# CORS
cors_allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000;http://127.0.0.1:3000",
    ).split(";")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ADMIN ROUTER
app.include_router(admin_router)


# TOUR ROUTERS
app.include_router(category_router)
app.include_router(tour_router)
app.include_router(country_router)
app.include_router(region_router)
app.include_router(district_router)

# HOTEL ROUTERS
app.include_router(hotel_router)
app.include_router(hotel_image_router)

# TRANSPORT ROUTERS
app.include_router(transport_router)
app.include_router(transport_image_router)

# HELICOPTER ROUTERS
app.include_router(helicopter_tour_router)
app.include_router(helicopter_image_router)

# TREKKING ROUTERS
app.include_router(trekking_router)
app.include_router(trekking_image_router)
app.include_router(trekking_program_router)

# OTHER ROUTERS
app.include_router(contact_router)
app.include_router(faq_router)
app.include_router(travel_request_router)
app.include_router(booking_router)

app.include_router(about_router)
app.include_router(about_section_router)

app.include_router(tour_image_router)
app.include_router(tour_program_router)


# NEW AI CHAT ROUTERS
app.include_router(client_auth_router, prefix='/auth')
app.include_router(client_auth_router, prefix='/chat/auth', include_in_schema=False)
app.include_router(chat_router)
app.include_router(chat_ws_router)
app.include_router(selection_router)
app.include_router(manager_selection_router)
app.include_router(registration_router)
app.include_router(password_reset_router)


# ADMIN PANEL
setup_admin(app)


@app.get("/")
def home():
    return {
        "message": "Welcome to KYRGYZGO API"
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=False
    )
