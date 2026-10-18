from dotenv import load_dotenv

load_dotenv()
import uvicorn

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mysite.database.db import Base, engine
import mysite.database.models

from mysite.api.admin import admin_router
from mysite.api.tour_category import category_router
from mysite.api.tour import tour_router
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
from mysite.api.chat import chat_router
from mysite.api.about import about_router
from mysite.api.about_section import about_section_router
from mysite.api.tour_image import tour_image_router
from mysite.api.tour_program import tour_program_router

app = FastAPI(
    title="KYRGYZGO",
    description="KYRGYZGO Tourism API",
    version="1.0.0"
)

Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(admin_router)
app.include_router(category_router)
app.include_router(tour_router)
app.include_router(region_router)
app.include_router(district_router)
app.include_router(hotel_router)
app.include_router(hotel_image_router)
app.include_router(transport_router)
app.include_router(transport_image_router)
app.include_router(helicopter_tour_router)
app.include_router(helicopter_image_router)
app.include_router(trekking_router)
app.include_router(trekking_image_router)
app.include_router(trekking_program_router)
app.include_router(contact_router)
app.include_router(faq_router)
app.include_router(travel_request_router)
app.include_router(booking_router)
app.include_router(chat_router)
app.include_router(about_router)
app.include_router(about_section_router)
app.include_router(tour_image_router)
app.include_router(tour_program_router)


@app.get("/")
def home():
    return {"message": "Welcome to KYRGYZGO API"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )
