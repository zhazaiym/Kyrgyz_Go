"""Admin image uploads stored on the server and served by URL from /media."""

import mimetypes
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from mysite.api.admin import require_admin_roles
from mysite.api.errors import error_detail
from mysite.api.resource_limits import setting

MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT') or Path(__file__).resolve().parents[2] / 'media')
MEDIA_URL = '/media'
IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP'}
MAX_IMAGE_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
MAX_IMAGE_SIDE = 2560
mimetypes.add_type('image/webp', '.webp')

media_router = APIRouter(prefix='/admin/media', tags=['Media'])


def store_image(content) -> str:
    try:
        with Image.open(content) as source:
            if source.format not in IMAGE_FORMATS:
                raise HTTPException(status_code=400, detail=error_detail('invalid_request'))
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise HTTPException(status_code=400, detail=error_detail('invalid_request'))
            if source.format == 'JPEG':
                source.draft('RGB', (MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            source.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            image = ImageOps.exif_transpose(source)
            mode = 'RGBA' if image.has_transparency_data else 'RGB'
            if image.mode != mode:
                converted = image.convert(mode)
                image.close()
                image = converted
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise HTTPException(status_code=400, detail=error_detail('invalid_request')) from exc
    image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    name = f'{datetime.now(UTC):%Y/%m}/{uuid.uuid4().hex}.webp'
    path = MEDIA_ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, 'WEBP', quality=85)
    image.close()
    return name


async def save_upload(request: Request, upload: UploadFile) -> str:
    limit = setting('MAX_IMAGE_UPLOAD_BYTES')

    def file_size():
        upload.file.seek(0, 2)
        size = upload.file.tell()
        upload.file.seek(0)
        return size

    if await run_in_threadpool(file_size) > limit:
        raise HTTPException(
            status_code=413, detail=f'Сүрөт {limit // 1_048_576} МБдан ашпашы керек'
        )
    name = await run_in_threadpool(store_image, upload.file)
    return f'{MEDIA_URL}/{name}'


@media_router.post(
    '/', status_code=201, dependencies=[Depends(require_admin_roles('catalog_editor'))]
)
async def upload_media(request: Request):
    async with request.form(max_files=1, max_fields=1) as form:
        upload = form.get('file')
        if not isinstance(upload, UploadFile) and not hasattr(upload, 'file'):
            raise HTTPException(400, detail=error_detail('invalid_request'))
        return {'url': await save_upload(request, upload)}
