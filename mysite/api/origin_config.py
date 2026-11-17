import os
from urllib.parse import urlsplit

DEFAULT_CORS_ORIGINS = 'http://localhost:3000;http://127.0.0.1:3000'


def configured_origins(variable: str, default: str = DEFAULT_CORS_ORIGINS) -> tuple[str, ...]:
    """Read an explicit semicolon-separated list of trusted browser origins."""
    return tuple(
        origin.strip() for origin in os.getenv(variable, default).split(';') if origin.strip()
    )


LOOPBACK_HOSTS = {'localhost', '127.0.0.1', '[::1]'}


def validate_origin_settings():
    """Every trusted origin is an https site or a loopback address for local development.

    A plain http address, a wildcard or a path would trust what the company does
    not control, so the application refuses to start instead.
    """
    for variable in ('CORS_ALLOWED_ORIGINS', 'CHAT_ALLOWED_ORIGINS'):
        for origin in configured_origins(variable):
            parts = urlsplit(origin)
            loopback = parts.scheme == 'http' and parts.netloc.rsplit(':', 1)[0] in LOOPBACK_HOSTS
            if (
                (parts.scheme != 'https' and not loopback)
                or not parts.netloc
                or '*' in origin
                or '@' in parts.netloc
                or f'{parts.scheme}://{parts.netloc}' != origin
            ):
                raise RuntimeError(
                    f'{variable}: {origin!r} must be https://host or http://localhost:port'
                )
