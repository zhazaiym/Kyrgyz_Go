"""Admin image uploads stored on the server and served by URL from /media."""

import os
import uuid
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from mysite.api.admin import get_current_admin
from mysite.api.resource_limits import setting

MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT') or Path(__file__).resolve().parents[2] / 'media')
MEDIA_URL = '/media'
IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP'}
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_SIDE = 2560

media_router = APIRouter(prefix='/admin/media', tags=['Media'])


def store_image(content: bytes) -> str:
    try:
        with Image.open(BytesIO(content)) as source:
            if source.format not in IMAGE_FORMATS:
                raise HTTPException(status_code=400, detail='Сүрөт JPEG, PNG же WEBP болушу керек')
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise HTTPException(status_code=400, detail='Сүрөттүн өлчөмү өтө чоң')
            image = ImageOps.exif_transpose(source)
            image = image.convert('RGBA' if image.has_transparency_data else 'RGB')
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise HTTPException(status_code=400, detail='Файл сүрөт эмес') from exc
    image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    name = f'{datetime.now(UTC):%Y/%m}/{uuid.uuid4().hex}.webp'
    path = MEDIA_ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, 'WEBP', quality=85)
    return name


async def save_upload(request: Request, upload: UploadFile) -> str:
    limit = setting('MAX_IMAGE_UPLOAD_BYTES')
    content = await upload.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(
            status_code=413, detail=f'Сүрөт {limit // 1_048_576} МБдан ашпашы керек'
        )
    name = await run_in_threadpool(store_image, content)
    return f'{request.url.scheme}://{request.url.netloc}{MEDIA_URL}/{name}'


@media_router.post('/', status_code=201, dependencies=[Depends(get_current_admin)])
async def upload_media(request: Request, file: UploadFile):
    return {'url': await save_upload(request, file)}
