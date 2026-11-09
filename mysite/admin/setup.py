from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from sqladmin import Admin as SQLAdmin
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from mysite.admin.authentication import AdminAuthBackend, forget_browser
from mysite.admin.realtime import admin_requests_websocket
from mysite.api.media import save_upload
from mysite.api.video_media import save_video_upload
from mysite.database.db import engine

from .views import (AboutAdmin, AboutSectionAdmin, AdminAdmin, ContactAdmin, DistrictAdmin,
                    FAQAdmin, HelicopterImageAdmin, HelicopterTourAdmin, HotelAdmin,
                    HotelImageAdmin, RegionAdmin, TourAdmin, TourCategoryAdmin, TourImageAdmin,
                    TourProgramAdmin, TourVideoAdmin, TransportAdmin, TransportImageAdmin,
                    TravelRequestAdmin, TrekkingAdmin, TrekkingImageAdmin, TrekkingProgramAdmin)


async def upload_image(request: Request):
    if not await AdminAuthBackend().authenticate(request):
        return JSONResponse({'detail': 'invalid_credentials'}, status_code=401)
    admin_id = request.session.get('admin_id')
    role = (
        await run_in_threadpool(AdminAuthBackend.active_admin_role, admin_id)
        if admin_id is not None
        else None
    )
    if admin_id is None or role not in {'owner', 'catalog_editor'}:
        return JSONResponse({'detail': 'Админ катары кириңиз'}, status_code=401)
    form = await request.form(max_files=1, max_fields=1)
    upload = form.get('file')
    if not hasattr(upload, 'read'):
        return JSONResponse({'detail': 'Сүрөт тандалган жок'}, status_code=400)
    try:
        url = await save_upload(request, upload)
    except HTTPException as exc:
        return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
    return JSONResponse({'url': url}, status_code=201)


async def upload_video(request: Request):
    if not await AdminAuthBackend().authenticate(request):
        return JSONResponse({'detail': 'authentication_required'}, status_code=401)
    role = await run_in_threadpool(
        AdminAuthBackend.active_admin_role, request.session.get('admin_id')
    )
    if role not in {'owner', 'catalog_editor'}:
        return JSONResponse({'detail': 'forbidden'}, status_code=403)
    try:
        return JSONResponse(await save_video_upload(request), status_code=201)
    except HTTPException as exc:
        return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)


def setup_admin(auth_app: FastAPI):
    from mysite.admin.security_views import AdminSessionAdmin, AdminTrustedDeviceAdmin

    admin = SQLAdmin(
        auth_app,
        engine,
        authentication_backend=AdminAuthBackend(),
        templates_dir=str(Path(__file__).resolve().parent / 'templates'),
    )
    admin.admin.router.add_websocket_route(
        '/ws/requests', admin_requests_websocket, name='request_notifications'
    )
    admin.admin.router.add_route('/media/upload', upload_image, methods=['POST'])
    admin.admin.router.add_route('/media/video-upload', upload_video, methods=['POST'])
    admin.admin.router.add_route('/forget-device', forget_browser, methods=['POST'])
    admin.add_view(AdminAdmin)
    admin.add_view(AdminSessionAdmin)
    admin.add_view(AdminTrustedDeviceAdmin)
    admin.add_view(AboutAdmin)
    admin.add_view(AboutSectionAdmin)
    admin.add_view(TourCategoryAdmin)
    admin.add_view(TourVideoAdmin)
    admin.add_view(TourImageAdmin)
    admin.add_view(TourAdmin)
    admin.add_view(TourProgramAdmin)
    admin.add_view(RegionAdmin)
    admin.add_view(DistrictAdmin)
    admin.add_view(HotelAdmin)
    admin.add_view(HotelImageAdmin)
    admin.add_view(TransportAdmin)
    admin.add_view(TransportImageAdmin)
    admin.add_view(HelicopterTourAdmin)
    admin.add_view(HelicopterImageAdmin)
    admin.add_view(TrekkingAdmin)
    admin.add_view(TrekkingImageAdmin)
    admin.add_view(TrekkingProgramAdmin)
    admin.add_view(ContactAdmin)
    admin.add_view(FAQAdmin)
    admin.add_view(TravelRequestAdmin)
    return admin
