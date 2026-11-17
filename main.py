# ruff: noqa: E402 -- load environment variables before importing application modules.
import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / '.env')
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ML.config import validate_chat_settings
from mysite.admin.host import AdminHostMiddleware
from mysite.admin.setup import setup_admin
from mysite.api.about import about_router
from mysite.api.about_section import about_section_router
from mysite.api.admin_access import AdminAccessMiddleware
from mysite.api.booking import booking_router
from mysite.api.chat import chat_router
from mysite.api.chat_images import chat_images_router
from mysite.api.chat_ws import chat_ws_router
from mysite.api.contact import contact_router
from mysite.api.country import country_router
from mysite.api.district import district_router
from mysite.api.faq import faq_router
from mysite.api.guest_ai import guest_ai_router
from mysite.api.helicopter_tour import helicopter_tour_router
from mysite.api.home_content import home_content_router
from mysite.api.hotel import hotel_router
from mysite.api.image_routes import (helicopter_image_router, hotel_image_router, tour_image_router,
                                     transport_image_router, trekking_image_router)
from mysite.api.media import MEDIA_ROOT, MEDIA_URL, media_router
from mysite.api.observability import observability_router, validate_metrics_config
from mysite.api.origin_config import configured_origins, validate_origin_settings
from mysite.api.paths import TrailingSlashMiddleware
from mysite.api.region import region_router
from mysite.api.registration import legacy_auth_router, registration_router
from mysite.api.resource_limits import ResourceLimitsMiddleware, validate_resource_settings
from mysite.api.social_auth import social_auth_router
from mysite.api.social_oauth import social_oauth_router
from mysite.api.token_maintenance import token_cleanup_loop
from mysite.api.tour import tour_router
from mysite.api.tour_category import category_router
from mysite.api.tour_program import tour_program_router
from mysite.api.tour_reviews import tour_reviews_router
from mysite.api.tour_video import tour_video_router
from mysite.api.transport import transport_router
from mysite.api.travel_request import travel_request_router
from mysite.api.travel_selection import selection_router
from mysite.api.trekking import trekking_router
from mysite.api.trekking_program import trekking_program_router
from mysite.api.trip_options import trip_options_router
from mysite.api.video_media import video_media_router
from mysite.settings import flag, validate_settings

logger = logging.getLogger(__name__)


# FASTAPI
@asynccontextmanager
async def lifespan(_app):
    cleanup = asyncio.create_task(token_cleanup_loop())
    from mysite.translations.jobs import recover_missing_translations

    async def recover_translations():
        while True:
            try:
                queued = await asyncio.to_thread(recover_missing_translations)
                logger.info('Recovered %d incomplete translation jobs', queued)
            except Exception:
                logger.exception('Could not queue missing catalogue translations')
            await asyncio.sleep(900)

    translation_recovery = asyncio.create_task(recover_translations())

    async def warm_chat_clients():
        from ML.provider import warm_up

        try:
            await asyncio.to_thread(warm_up)
        except Exception:
            logger.warning('Chat clients were not prepared in advance')

    chat_warm_up = asyncio.create_task(warm_chat_clients())
    try:
        yield
    finally:
        cleanup.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup
        chat_warm_up.cancel()
        translation_recovery.cancel()
        with suppress(asyncio.CancelledError):
            await translation_recovery


validate_resource_settings()
validate_chat_settings()
validate_origin_settings()
validate_metrics_config()
validate_settings()
api_docs = flag('API_DOCS')
app = FastAPI(
    title='KYRGYZGO',
    description='KYRGYZGO Tourism API + AI Travel Assistant',
    version='1.0.0',
    lifespan=lifespan,
    docs_url='/docs' if api_docs else None,
    redoc_url='/redoc' if api_docs else None,
    openapi_url='/openapi.json' if api_docs else None,
)

from sqlalchemy.exc import TimeoutError as DatabasePoolTimeout
from starlette.exceptions import HTTPException as StarletteHTTPException

from mysite.api.errors import database_busy_response, http_error_response

app.add_exception_handler(StarletteHTTPException, http_error_response)
app.add_exception_handler(DatabasePoolTimeout, database_busy_response)


# CORS
app.add_middleware(ResourceLimitsMiddleware)
app.add_middleware(AdminAccessMiddleware)
from mysite.api.observability import HTTPMetricsMiddleware

app.add_middleware(HTTPMetricsMiddleware)
cors_allowed_origins = list(configured_origins('CORS_ALLOWED_ORIGINS'))

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.add_middleware(AdminHostMiddleware)
app.add_middleware(TrailingSlashMiddleware)


# ADMIN ROUTER
app.include_router(media_router)
app.include_router(video_media_router)


# TOUR ROUTERS
app.include_router(category_router)
app.include_router(tour_router)
app.include_router(trip_options_router)
app.include_router(tour_reviews_router)
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
app.include_router(home_content_router)
app.include_router(contact_router)
app.include_router(faq_router)
app.include_router(travel_request_router)
app.include_router(booking_router)

app.include_router(about_router)
app.include_router(about_section_router)

app.include_router(tour_video_router)
app.include_router(tour_image_router)
app.include_router(tour_program_router)


# NEW AI CHAT ROUTERS
app.include_router(social_auth_router, prefix='/auth')
app.include_router(social_oauth_router, prefix='/auth')
app.include_router(chat_router)
app.include_router(guest_ai_router)
app.include_router(chat_images_router)
app.include_router(chat_ws_router)
app.include_router(selection_router)
app.include_router(registration_router)
app.include_router(legacy_auth_router)
app.include_router(observability_router)


# MEDIA FILES
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
if flag('SERVE_MEDIA_LOCALLY'):
    app.mount(MEDIA_URL, StaticFiles(directory=MEDIA_ROOT), name='media')


# ADMIN PANEL
setup_admin(app)


@app.get('/')
def home():
    return {'message': 'Welcome to KYRGYZGO API'}


if __name__ == '__main__':
    uvicorn.run(
        'main:app',
        host='127.0.0.1',
        port=8000,
        reload=False,
        limit_concurrency=128,
        backlog=256,
        timeout_keep_alive=5,
        ws_max_size=16_384,
        ws_max_queue=8,
        ws_per_message_deflate=False,
    )
