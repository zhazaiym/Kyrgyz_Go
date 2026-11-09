"""Bounded disk uploads, inspected by ffprobe independently of image decoding."""

import json
import os
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from mysite.api.admin import require_admin_roles
from mysite.api.errors import error_detail
from mysite.api.media import MEDIA_ROOT, MEDIA_URL
from mysite.api.resource_limits import setting

video_media_router = APIRouter(prefix='/admin/media', tags=['Media'])


def inspect_video(path: Path) -> tuple[str, str]:
    # Restricted demuxers/protocols prevent playlists and external resource fetching.
    try:
        result = subprocess.run(
            [
                os.getenv('FFPROBE_BINARY', 'ffprobe'),
                '-v',
                'error',
                '-protocol_whitelist',
                'file',
                '-format_whitelist',
                'mov,matroska,webm',
                '-probesize',
                '5242880',
                '-analyzeduration',
                '5000000',
                '-show_entries',
                'format=format_name:stream=codec_type,codec_name',
                '-of',
                'json',
                str(path),
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, PermissionError) as exc:
        raise HTTPException(503, detail=error_detail('service_unavailable')) from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(400, detail=error_detail('invalid_request')) from exc
    try:
        info = json.loads(result.stdout)
        streams = info.get('streams', [])
        if result.returncode or not any(
            stream.get('codec_type') == 'video' and stream.get('codec_name') for stream in streams
        ):
            raise ValueError('No video stream')
        with path.open('rb') as source:
            signature = source.read(4096)
        formats = info.get('format', {}).get('format_name', '').split(',')
        # ffprobe groups MOV/MP4 and Matroska/WebM; check container identity as well.
        if 'mp4' in formats and signature[4:8] == b'ftyp':
            brands = (
                signature[8:12] + signature[16 : min(int.from_bytes(signature[:4], 'big'), 4096)]
            )
            if any(
                brand in brands
                for brand in (
                    b'isom',
                    b'iso2',
                    b'iso5',
                    b'iso6',
                    b'mp41',
                    b'mp42',
                    b'avc1',
                    b'dash',
                )
            ):
                return 'mp4', 'video/mp4'
        if 'webm' in formats and signature.startswith(b'\x1a\x45\xdf\xa3'):
            # EBML DocType element 0x4282 with the exact WebM doctype.
            if b'\x42\x82\x84webm' in signature:
                if all(
                    stream.get('codec_name') in {'vp8', 'vp9', 'av1', 'opus', 'vorbis'}
                    for stream in streams
                ):
                    return 'webm', 'video/webm'
        raise ValueError('Unsupported container')
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, detail=error_detail('invalid_request')) from exc


def store_video(source) -> dict:
    directory = MEDIA_ROOT / 'videos' / f'{datetime.now(UTC):%Y/%m}'
    directory.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, suffix='.upload', delete=False) as output:
            temporary = Path(output.name)
            size = 0
            while chunk := source.read(1_048_576):
                size += len(chunk)
                if size > setting('MAX_VIDEO_UPLOAD_BYTES'):
                    raise HTTPException(413, detail=error_detail('invalid_request'))
                output.write(chunk)
        extension, content_type = inspect_video(temporary)
        final = directory / f'{uuid.uuid4().hex}.{extension}'
        temporary.replace(final)
        return {
            'url': f'{MEDIA_URL}/{final.relative_to(MEDIA_ROOT).as_posix()}',
            'content_type': content_type,
            'size': size,
        }
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


async def save_video_upload(request: Request) -> dict:
    async with request.form(max_files=1, max_fields=1) as form:
        upload = form.get('file')
        if not hasattr(upload, 'file'):
            raise HTTPException(400, detail=error_detail('invalid_request'))
        return await run_in_threadpool(store_video, upload.file)


@video_media_router.post(
    '/videos/', status_code=201, dependencies=[Depends(require_admin_roles('catalog_editor'))]
)
async def upload_video(request: Request):
    return await save_video_upload(request)
