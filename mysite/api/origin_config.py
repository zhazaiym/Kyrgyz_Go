import os

DEFAULT_CORS_ORIGINS = 'http://localhost:3000;http://127.0.0.1:3000'


def configured_origins(variable: str, default: str = DEFAULT_CORS_ORIGINS) -> tuple[str, ...]:
    """Read an explicit semicolon-separated list of trusted browser origins."""
    return tuple(
        origin.strip() for origin in os.getenv(variable, default).split(';') if origin.strip()
    )
