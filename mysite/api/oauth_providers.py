import base64
import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
import jwt

from mysite.api.social_auth import (TIMEOUT_SECONDS, Identity, SocialLoginError, apple_parts,
                                    clean_email, tls)

APPLE_ISSUER = 'https://appleid.apple.com'
http = httpx.Client(timeout=TIMEOUT_SECONDS, verify=tls, headers={'User-Agent': 'KerbenTravel'})
apple_keys = jwt.PyJWKClient(
    f'{APPLE_ISSUER}/auth/keys',
    cache_keys=True,
    lifespan=3600,
    timeout=TIMEOUT_SECONDS,
    ssl_context=tls,
)


@dataclass(frozen=True)
class OAuthProvider:
    key: str
    authorize_url: str
    token_url: str
    scope: str
    profile: Callable[[dict, str], Identity]
    pkce: bool = False
    basic_auth: bool = False
    client_id_param: str = 'client_id'
    callback_params: tuple[str, ...] = ()
    authorize_extra: tuple[tuple[str, str], ...] = ()
    client_secret: Callable[[str, str], str] | None = None


def call(method, url, expect=dict, **kwargs):
    try:
        response = http.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise SocialLoginError(503, 'service_unavailable') from exc
    if 400 <= response.status_code < 500:
        raise SocialLoginError(401, 'invalid_credentials')
    if response.status_code != 200:
        raise SocialLoginError(503, 'service_unavailable')
    try:
        payload = response.json()
    except ValueError as exc:
        raise SocialLoginError(503, 'service_unavailable') from exc
    if not isinstance(payload, expect):
        raise SocialLoginError(503, 'service_unavailable')
    return payload


def bearer(token):
    return {'Authorization': f'Bearer {token}'}


def subject_of(value):
    subject = str(value or '')
    if not subject or len(subject) > 255:
        raise SocialLoginError(401, 'invalid_credentials')
    return subject


def vk_profile(payload, app_id):
    token = payload['access_token']
    user = (
        call(
            'POST',
            'https://id.vk.ru/oauth2/user_info',
            data={'access_token': token, 'client_id': app_id},
        ).get('user')
        or {}
    )
    return Identity(
        subject=subject_of(user.get('user_id')),
        email=clean_email(user.get('email')),
        email_trusted=False,
    )


def yandex_profile(payload, app_id):
    token = payload['access_token']
    data = call(
        'GET',
        'https://login.yandex.ru/info',
        params={'format': 'json'},
        headers={'Authorization': f'OAuth {token}'},
    )
    if data.get('client_id') not in (None, app_id):
        raise SocialLoginError(401, 'invalid_credentials')
    return Identity(
        subject=subject_of(data.get('id')),
        email=clean_email(data.get('default_email')),
        email_trusted=False,
    )


def x_profile(payload, app_id):
    token = payload['access_token']
    data = call('GET', 'https://api.x.com/2/users/me', headers=bearer(token)).get('data') or {}
    return Identity(subject=subject_of(data.get('id')), email=None, email_trusted=False)


def github_profile(payload, app_id):
    token = payload['access_token']
    headers = {**bearer(token), 'Accept': 'application/vnd.github+json'}
    user = call('GET', 'https://api.github.com/user', headers=headers)
    emails = call('GET', 'https://api.github.com/user/emails', expect=list, headers=headers)
    primary = next(
        (
            item.get('email')
            for item in emails
            if isinstance(item, dict) and item.get('primary') and item.get('verified')
        ),
        None,
    )
    email = clean_email(primary)
    return Identity(subject=subject_of(user.get('id')), email=email, email_trusted=bool(email))


def discord_profile(payload, app_id):
    token = payload['access_token']
    user = call('GET', 'https://discord.com/api/users/@me', headers=bearer(token))
    verified = user.get('verified') is True
    return Identity(
        subject=subject_of(user.get('id')),
        email=clean_email(user.get('email')) if verified else None,
        email_trusted=verified,
    )


def microsoft_profile(payload, app_id):
    token = payload['access_token']
    user = call(
        'GET',
        'https://graph.microsoft.com/v1.0/me',
        params={'$select': 'id,mail,userPrincipalName'},
        headers=bearer(token),
    )
    return Identity(
        subject=subject_of(user.get('id')), email=clean_email(user.get('mail')), email_trusted=False
    )


def tiktok_profile(payload, app_id):
    token = payload['access_token']
    data = call(
        'GET',
        'https://open.tiktokapis.com/v2/user/info/',
        params={'fields': 'open_id,display_name'},
        headers=bearer(token),
    )
    user = (data.get('data') or {}).get('user') or {}
    return Identity(subject=subject_of(user.get('open_id')), email=None, email_trusted=False)


def kakao_profile(payload, app_id):
    user = call('GET', 'https://kapi.kakao.com/v2/user/me', headers=bearer(payload['access_token']))
    account = user.get('kakao_account') or {}
    trusted = account.get('is_email_verified') is True and account.get('is_email_valid') is True
    return Identity(
        subject=subject_of(user.get('id')),
        email=clean_email(account.get('email')) if trusted else None,
        email_trusted=trusted,
    )


def naver_profile(payload, app_id):
    data = call(
        'GET', 'https://openapi.naver.com/v1/nid/me', headers=bearer(payload['access_token'])
    )
    user = data.get('response') or {}
    return Identity(
        subject=subject_of(user.get('id')),
        email=clean_email(user.get('email')),
        email_trusted=False,
    )


def line_profile(payload, app_id):
    user = call('GET', 'https://api.line.me/v2/profile', headers=bearer(payload['access_token']))
    return Identity(subject=subject_of(user.get('userId')), email=None, email_trusted=False)


def apple_profile(payload, app_id):
    id_token = payload.get('id_token')
    if not isinstance(id_token, str):
        raise SocialLoginError(401, 'invalid_credentials')
    try:
        key = apple_keys.get_signing_key_from_jwt(id_token)
    except jwt.PyJWKClientConnectionError as exc:
        raise SocialLoginError(503, 'service_unavailable') from exc
    except jwt.PyJWTError as exc:
        raise SocialLoginError(401, 'invalid_credentials') from exc
    try:
        claims = jwt.decode(
            id_token,
            key.key,
            algorithms=['RS256'],
            audience=app_id,
            issuer=APPLE_ISSUER,
            options={'require': ['exp', 'iat', 'iss', 'aud', 'sub']},
        )
    except jwt.PyJWTError as exc:
        raise SocialLoginError(401, 'invalid_credentials') from exc
    trusted = str(claims.get('email_verified')).lower() == 'true'
    return Identity(
        subject=subject_of(claims.get('sub')),
        email=clean_email(claims.get('email')) if trusted else None,
        email_trusted=trusted,
    )


def apple_client_secret(app_id, secret):
    team_id, key_id, key = apple_parts(secret)
    now = int(time.time())
    claims = {'iss': team_id, 'iat': now, 'exp': now + 300, 'aud': APPLE_ISSUER, 'sub': app_id}
    return jwt.encode(claims, key, algorithm='ES256', headers={'kid': key_id})


OAUTH_PROVIDERS = {
    provider.key: provider
    for provider in (
        OAuthProvider(
            key='vk',
            authorize_url='https://id.vk.ru/authorize',
            token_url='https://id.vk.ru/oauth2/auth',
            scope='email',
            profile=vk_profile,
            pkce=True,
            callback_params=('device_id', 'state'),
        ),
        OAuthProvider(
            key='yandex',
            authorize_url='https://oauth.yandex.ru/authorize',
            token_url='https://oauth.yandex.ru/token',
            scope='login:info login:email',
            profile=yandex_profile,
        ),
        OAuthProvider(
            key='x',
            authorize_url='https://x.com/i/oauth2/authorize',
            token_url='https://api.x.com/2/oauth2/token',
            scope='users.read tweet.read',
            profile=x_profile,
            pkce=True,
            basic_auth=True,
        ),
        OAuthProvider(
            key='github',
            authorize_url='https://github.com/login/oauth/authorize',
            token_url='https://github.com/login/oauth/access_token',
            scope='read:user user:email',
            profile=github_profile,
        ),
        OAuthProvider(
            key='discord',
            authorize_url='https://discord.com/oauth2/authorize',
            token_url='https://discord.com/api/oauth2/token',
            scope='identify email',
            profile=discord_profile,
        ),
        OAuthProvider(
            key='microsoft',
            authorize_url='https://login.microsoftonline.com/common/oauth2/v2.0/authorize',
            token_url='https://login.microsoftonline.com/common/oauth2/v2.0/token',
            scope='User.Read',
            profile=microsoft_profile,
        ),
        OAuthProvider(
            key='tiktok',
            authorize_url='https://www.tiktok.com/v2/auth/authorize/',
            token_url='https://open.tiktokapis.com/v2/oauth/token/',
            scope='user.info.basic',
            profile=tiktok_profile,
            client_id_param='client_key',
        ),
        OAuthProvider(
            key='apple',
            authorize_url=f'{APPLE_ISSUER}/auth/authorize',
            token_url=f'{APPLE_ISSUER}/auth/token',
            scope='name email',
            profile=apple_profile,
            authorize_extra=(('response_mode', 'form_post'),),
            client_secret=apple_client_secret,
        ),
        OAuthProvider(
            key='kakao',
            authorize_url='https://kauth.kakao.com/oauth/authorize',
            token_url='https://kauth.kakao.com/oauth/token',
            scope='',
            profile=kakao_profile,
        ),
        OAuthProvider(
            key='naver',
            authorize_url='https://nid.naver.com/oauth2.0/authorize',
            token_url='https://nid.naver.com/oauth2.0/token',
            scope='',
            profile=naver_profile,
            callback_params=('state',),
        ),
        OAuthProvider(
            key='line',
            authorize_url='https://access.line.me/oauth2/v2.1/authorize',
            token_url='https://api.line.me/oauth2/v2.1/token',
            scope='profile',
            profile=line_profile,
        ),
    )
}


def code_challenge(verifier):
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode()


def authorize_params(provider, app_id, redirect_uri, state, verifier):
    params = {
        'response_type': 'code',
        provider.client_id_param: app_id,
        'redirect_uri': redirect_uri,
        'state': state,
        **dict(provider.authorize_extra),
    }
    if provider.scope:
        params['scope'] = provider.scope
    if provider.pkce:
        params['code_challenge'] = code_challenge(verifier)
        params['code_challenge_method'] = 'S256'
    return params


def exchange_code(provider, app_id, secret, code, redirect_uri, verifier, callback):
    data = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': redirect_uri}
    auth = None
    if provider.client_secret is not None:
        secret = provider.client_secret(app_id, secret)
    if provider.basic_auth:
        auth = (app_id, secret)
    else:
        data[provider.client_id_param] = app_id
        data['client_secret'] = secret
    if provider.pkce:
        data['code_verifier'] = verifier
    for name in provider.callback_params:
        if callback.get(name):
            data[name] = callback[name]
    payload = call(
        'POST', provider.token_url, data=data, auth=auth, headers={'Accept': 'application/json'}
    )
    if not isinstance(payload.get('access_token'), str) or not payload['access_token']:
        raise SocialLoginError(401, 'invalid_credentials')
    return payload
