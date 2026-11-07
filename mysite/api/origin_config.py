import os


def configured_origins(variable: str, default: str) -> tuple[str, ...]:
    """Read an explicit semicolon-separated list of trusted browser origins."""
    return tuple(
        origin.strip() for origin in os.getenv(variable, default).split(';') if origin.strip()
    )
