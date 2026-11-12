from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from sqladmin import Admin as SQLAdmin
from sqladmin.authentication import login_required
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from mysite.admin.authentication import AdminAuthBackend
from mysite.admin.overview import DEFAULT_PERIOD, build_overview
from mysite.admin.realtime import admin_requests_websocket
from mysite.api.media import save_upload
from mysite.api.video_media import save_video_upload
from mysite.database.db import engine

from .views import (AboutAdmin, AboutSectionAdmin, AdminAdmin, AuthProviderAdmin, ContactAdmin,
                    DistrictAdmin, FAQAdmin, HelicopterImageAdmin, HelicopterTourAdmin, HotelAdmin,
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


class KerbenAdmin(SQLAdmin):
    @login_required
    async def index(self, request: Request):
        role = await run_in_threadpool(
            AdminAuthBackend.active_admin_role, request.session.get('admin_id')
        )
        overview = await run_in_threadpool(
            build_overview,
            request.query_params.get('period', DEFAULT_PERIOD),
            role in {'owner', 'manager'},
        )
        return await self.templates.TemplateResponse(
            request,
            'sqladmin/index.html',
            {'overview': overview, 'catalog_links': role in {'owner', 'catalog_editor'}},
        )


def setup_admin(auth_app: FastAPI):
    from mysite.admin.security_views import AdminSessionAdmin

    admin = KerbenAdmin(
        auth_app,
        engine,
        title='Kerben Travel',
        authentication_backend=AdminAuthBackend(),
        templates_dir=str(Path(__file__).resolve().parent / 'templates'),
    )
    admin.admin.router.add_websocket_route(
        '/ws/requests', admin_requests_websocket, name='request_notifications'
    )
    admin.admin.router.add_route('/media/upload', upload_image, methods=['POST'])
    admin.admin.router.add_route('/media/video-upload', upload_video, methods=['POST'])
    for view in (
        TravelRequestAdmin,
        TourAdmin,
        TourCategoryAdmin,
        TourProgramAdmin,
        TourImageAdmin,
        TourVideoAdmin,
        HotelAdmin,
        HotelImageAdmin,
        TransportAdmin,
        TransportImageAdmin,
        HelicopterTourAdmin,
        HelicopterImageAdmin,
        TrekkingAdmin,
        TrekkingProgramAdmin,
        TrekkingImageAdmin,
        RegionAdmin,
        DistrictAdmin,
        AboutAdmin,
        AboutSectionAdmin,
        ContactAdmin,
        FAQAdmin,
        AuthProviderAdmin,
        AdminAdmin,
        AdminSessionAdmin,
    ):
        admin.add_view(view)
    return admin
