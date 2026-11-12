import re
import secrets
import ssl
from dataclasses import dataclass

import certifi
import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mysite.api.client_auth import issue_token, passwords
from mysite.api.errors import error_detail
from mysite.api.network_identity import request_network
from mysite.api.rate_limit import enforce_rate_limit
from mysite.database.booking_validation import optional_email
from mysite.database.chat_models import ChatClient
from mysite.database.db import get_db
from mysite.database.social_models import AuthProvider, ClientIdentity

router = APIRouter(tags=['Client authentication'])

GOOGLE_CERTS = 'https://www.googleapis.com/oauth2/v3/certs'
GOOGLE_ISSUERS = ('accounts.google.com', 'https://accounts.google.com')
GRAPH_URL = 'https://graph.facebook.com'
APP_ID_FORMATS = {
    'google': re.compile(r'[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com'),
    'facebook': re.compile(r'[0-9]{5,25}'),
}
TIMEOUT_SECONDS = 5
tls = ssl.create_default_context(cafile=certifi.where())
google_keys = jwt.PyJWKClient(
    GOOGLE_CERTS, cache_keys=True, lifespan=3600, timeout=TIMEOUT_SECONDS, ssl_context=tls
)


class SocialLoginError(Exception):
    def __init__(self, status_code, code):
        super().__init__(code)
        self.status_code = status_code
        self.code = code


@dataclass
class Identity:
    subject: str
    email: str | None
    email_trusted: bool


class GoogleLogin(BaseModel):
    credential: str = Field(min_length=20, max_length=4096)


class FacebookLogin(BaseModel):
    access_token: str = Field(min_length=20, max_length=4096)


def valid_app_id(provider, value):
    return bool(value) and APP_ID_FORMATS[provider].fullmatch(value) is not None


def active_app_id(db, provider):
    row = db.get(AuthProvider, provider)
    if row is None or not row.is_active or not valid_app_id(provider, row.app_id):
        raise HTTPException(404, error_detail('not_found'))
    return row.app_id


def clean_email(value):
    try:
        return optional_email(value)
    except ValueError:
        return None


def google_identity(credential, client_id):
    try:
        key = google_keys.get_signing_key_from_jwt(credential)
    except jwt.PyJWKClientConnectionError as exc:
        raise SocialLoginError(503, 'service_unavailable') from exc
    except jwt.PyJWTError as exc:
        raise SocialLoginError(401, 'invalid_credentials') from exc
    try:
        claims = jwt.decode(
            credential,
            key.key,
            algorithms=['RS256'],
            audience=client_id,
            issuer=GOOGLE_ISSUERS,
            options={'require': ['exp', 'iat', 'iss', 'aud', 'sub']},
        )
    except jwt.PyJWTError as exc:
        raise SocialLoginError(401, 'invalid_credentials') from exc
    trusted = claims.get('email_verified') is True
    return Identity(
        subject=str(claims['sub']),
        email=clean_email(claims.get('email')) if trusted else None,
        email_trusted=trusted,
    )


def graph(path, access_token, fields=None):
    params = {'access_token': access_token}
    if fields:
        params['fields'] = fields
    try:
        response = httpx.get(
            f'{GRAPH_URL}/{path}', params=params, timeout=TIMEOUT_SECONDS, verify=tls
        )
    except httpx.HTTPError as exc:
        raise SocialLoginError(503, 'service_unavailable') from exc
    if 400 <= response.status_code < 500:
        raise SocialLoginError(401, 'invalid_credentials')
    if response.status_code != 200:
        raise SocialLoginError(503, 'service_unavailable')
    try:
        return response.json()
    except ValueError as exc:
        raise SocialLoginError(503, 'service_unavailable') from exc


def facebook_identity(access_token, app_id):
    if str(graph('app', access_token).get('id')) != app_id:
        raise SocialLoginError(401, 'invalid_credentials')
    profile = graph('me', access_token, 'id,email')
    subject = str(profile.get('id') or '')
    if not subject.isdigit():
        raise SocialLoginError(401, 'invalid_credentials')
    return Identity(subject=subject, email=clean_email(profile.get('email')), email_trusted=False)


def free_username(db, provider, identity):
    seed = (identity.email or '').split('@')[0]
    base = re.sub(r'[^a-z0-9_]', '', seed.lower())[:40]
    if len(base) < 3:
        base = f'{provider}_{base}'.rstrip('_')
    candidate = base
    while db.scalar(select(ChatClient.id).where(ChatClient.username == candidate)) is not None:
        candidate = f'{base}_{secrets.token_hex(3)}'
    return candidate


def linked_client(db, provider, identity):
    found = db.scalar(
        select(ClientIdentity).where(
            ClientIdentity.provider == provider, ClientIdentity.subject == identity.subject
        )
    )
    if found is not None:
        return db.get(ChatClient, found.client_id)
    owner = None
    if identity.email:
        owner = db.scalar(select(ChatClient).where(ChatClient.email == identity.email))
    if owner is not None and identity.email_trusted:
        client = owner
    else:
        client = ChatClient(
            username=free_username(db, provider, identity),
            email=identity.email if owner is None else None,
            password_hash=passwords.hash(secrets.token_urlsafe(32)),
        )
        db.add(client)
        db.flush()
    db.add(
        ClientIdentity(
            client_id=client.id, provider=provider, subject=identity.subject, email=identity.email
        )
    )
    db.commit()
    return client


def sign_in(request, db, provider, verify):
    enforce_rate_limit(
        f'client-{provider}', request_network(request), max_requests=20, window_seconds=600
    )
    app_id = active_app_id(db, provider)
    db.rollback()
    try:
        identity = verify(app_id)
    except SocialLoginError as exc:
        raise HTTPException(exc.status_code, error_detail(exc.code)) from exc
    try:
        client = linked_client(db, provider, identity)
    except IntegrityError:
        db.rollback()
        client = linked_client(db, provider, identity)
    return issue_token(db, client)


@router.get('/providers')
def providers(db: Session = Depends(get_db)):
    rows = {row.provider: row for row in db.scalars(select(AuthProvider))}

    def public(provider, key):
        row = rows.get(provider)
        enabled = bool(row and row.is_active and valid_app_id(provider, row.app_id))
        return {'enabled': enabled, key: row.app_id if enabled else None}

    return {'google': public('google', 'client_id'), 'facebook': public('facebook', 'app_id')}


@router.post('/google')
def google_login(data: GoogleLogin, request: Request, db: Session = Depends(get_db)):
    return sign_in(request, db, 'google', lambda app_id: google_identity(data.credential, app_id))


@router.post('/facebook')
def facebook_login(data: FacebookLogin, request: Request, db: Session = Depends(get_db)):
    return sign_in(
        request, db, 'facebook', lambda app_id: facebook_identity(data.access_token, app_id)
    )
