import hashlib
import hmac
import secrets
import time
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mysite.api.client_auth import issue_token
from mysite.api.errors import error_detail
from mysite.api.network_identity import request_network
from mysite.api.oauth_providers import OAUTH_PROVIDERS, authorize_params, exchange_code
from mysite.api.origin_config import configured_origins
from mysite.api.rate_limit import enforce_rate_limit
from mysite.api.social_auth import Identity, SocialLoginError, client_for, configured, credentials
from mysite.database.chat_models import ChatClient
from mysite.database.db import get_db
from mysite.database.social_models import AuthProvider, OAuthState, SocialLoginCode
from mysite.database.token_utils import digest, utcnow

router = APIRouter(tags=['Client authentication'])

STATE_COOKIE = 'kt_oauth'
STATE_TTL = timedelta(minutes=10)
CODE_TTL = timedelta(seconds=60)
TELEGRAM_MAX_AGE = 86400


class LoginCode(BaseModel):
    login_code: str = Field(min_length=20, max_length=128)


class TelegramLogin(BaseModel):
    model_config = ConfigDict(extra='allow')

    id: int
    auth_date: int
    hash: str = Field(pattern=r'^[0-9a-f]{64}$')


def limit(scope, request):
    enforce_rate_limit(scope, request_network(request), max_requests=30, window_seconds=600)


def oauth_provider(key):
    provider = OAUTH_PROVIDERS.get(key)
    if provider is None:
        raise HTTPException(404, error_detail('not_found'))
    return provider


def allowed_return(url):
    if len(url) > 2048:
        return False
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.netloc or '@' in parts.netloc:
        return False
    return f'{parts.scheme}://{parts.netloc}' in configured_origins('CORS_ALLOWED_ORIGINS')


def with_query(url, **params):
    parts = urlsplit(url)
    query = urlencode([*parse_qsl(parts.query), *params.items()])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def drop_expired(db):
    now = utcnow()
    db.execute(delete(OAuthState).where(OAuthState.expires_at < now))
    db.execute(delete(SocialLoginCode).where(SocialLoginCode.expires_at < now))


def callback_url(request, key):
    return str(request.url_for('oauth_callback', provider=key))


def login_code_for(db, client):
    code = secrets.token_urlsafe(32)
    db.add(
        SocialLoginCode(code_hash=digest(code), client_id=client.id, expires_at=utcnow() + CODE_TTL)
    )
    db.commit()
    return code


@router.get('/providers')
def providers(db: Session = Depends(get_db)):
    rows = {row.provider: row for row in db.scalars(select(AuthProvider))}
    found = {key: configured(row) for key, row in rows.items()}

    def public_id(key):
        return found[key][0] if found.get(key) else None

    return {
        'google': {'enabled': bool(found.get('google')), 'client_id': public_id('google')},
        'facebook': {'enabled': bool(found.get('facebook')), 'app_id': public_id('facebook')},
        'telegram': {'enabled': bool(found.get('telegram')), 'bot': public_id('telegram')},
        'redirect': [
            {'provider': key, 'title': rows[key].title, 'start_url': f'/auth/oauth/{key}/start'}
            for key in OAUTH_PROVIDERS
            if found.get(key)
        ],
    }


@router.get('/oauth/{provider}/start', name='oauth_start')
def oauth_start(provider: str, return_to: str, request: Request, db: Session = Depends(get_db)):
    limit('oauth-start', request)
    spec = oauth_provider(provider)
    if not allowed_return(return_to):
        raise HTTPException(400, error_detail('invalid_request'))
    app_id, _ = credentials(db, provider)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64) if spec.pkce else None
    drop_expired(db)
    db.add(
        OAuthState(
            state_hash=digest(state),
            provider=provider,
            code_verifier=verifier,
            return_to=return_to,
            expires_at=utcnow() + STATE_TTL,
        )
    )
    db.commit()
    params = authorize_params(spec, app_id, callback_url(request, provider), state, verifier)
    response = RedirectResponse(f'{spec.authorize_url}?{urlencode(params)}', status_code=302)
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=int(STATE_TTL.total_seconds()),
        path='/auth/oauth',
        httponly=True,
        secure=request.url.scheme == 'https',
        samesite='lax',
    )
    return response


def take_state(db, provider, state, cookie):
    if not state or not cookie or not secrets.compare_digest(state, cookie):
        return None
    flow = db.get(OAuthState, digest(state), with_for_update=True)
    if flow is None:
        return None
    db.delete(flow)
    db.commit()
    if flow.provider != provider or flow.expires_at <= utcnow():
        return None
    return flow


@router.get('/oauth/{provider}/callback', name='oauth_callback')
def oauth_callback(provider: str, request: Request, db: Session = Depends(get_db)):
    limit('oauth-callback', request)
    spec = oauth_provider(provider)
    query = request.query_params
    flow = take_state(db, provider, query.get('state'), request.cookies.get(STATE_COOKIE))
    if flow is None:
        raise HTTPException(400, error_detail('invalid_request'))

    def back(**params):
        response = RedirectResponse(with_query(flow.return_to, **params), status_code=302)
        response.delete_cookie(STATE_COOKIE, path='/auth/oauth')
        return response

    code = query.get('code')
    if query.get('error') or not code or len(code) > 2048:
        return back(login_error='denied')
    try:
        app_id, secret = credentials(db, provider)
        db.rollback()
        token = exchange_code(
            spec,
            app_id,
            secret,
            code,
            callback_url(request, provider),
            flow.code_verifier,
            {name: query.get(name) for name in spec.callback_params},
        )
        identity = spec.profile(token, app_id)
    except HTTPException:
        return back(login_error='unavailable')
    except SocialLoginError as exc:
        return back(login_error=exc.code)
    return back(login_code=login_code_for(db, client_for(db, provider, identity)))


@router.post('/oauth/exchange')
def oauth_exchange(data: LoginCode, request: Request, db: Session = Depends(get_db)):
    limit('oauth-exchange', request)
    row = db.get(SocialLoginCode, digest(data.login_code), with_for_update=True)
    if row is None or row.expires_at <= utcnow():
        raise HTTPException(401, error_detail('invalid_credentials'))
    client = db.get(ChatClient, row.client_id)
    db.delete(row)
    db.commit()
    if client is None:
        raise HTTPException(401, error_detail('invalid_credentials'))
    return issue_token(db, client)


def telegram_identity(data, bot_token):
    fields = data.model_dump(exclude={'hash'}, exclude_none=True)
    if len(fields) > 20 or not all(isinstance(value, str | int) for value in fields.values()):
        raise SocialLoginError(401, 'invalid_credentials')
    check = '\n'.join(f'{key}={value}' for key, value in sorted(fields.items()))
    key = hashlib.sha256(bot_token.encode()).digest()
    expected = hmac.new(key, check.encode(), hashlib.sha256).hexdigest()
    age = int(time.time()) - data.auth_date
    if not hmac.compare_digest(expected, data.hash) or not -60 <= age <= TELEGRAM_MAX_AGE:
        raise SocialLoginError(401, 'invalid_credentials')
    return Identity(subject=str(data.id), email=None, email_trusted=False)


@router.post('/telegram')
def telegram_login(data: TelegramLogin, request: Request, db: Session = Depends(get_db)):
    limit('client-telegram', request)
    _, bot_token = credentials(db, 'telegram')
    db.rollback()
    try:
        identity = telegram_identity(data, bot_token)
    except SocialLoginError as exc:
        raise HTTPException(exc.status_code, error_detail(exc.code)) from exc
    return issue_token(db, client_for(db, 'telegram', identity))
