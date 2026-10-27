from urllib.parse import urlsplit


def validate_whatsapp_link(value: str | None) -> str | None:
    if not value:
        return None

    value = value.strip()
    parsed = urlsplit(value)

    allowed_hosts = {
        'wa.me',
        'api.whatsapp.com',
        'web.whatsapp.com',
        'chat.whatsapp.com',
        'www.whatsapp.com',
        'whatsapp.com',
    }

    if (
        len(value) > 500
        or parsed.scheme != 'https'
        or (parsed.hostname or '').lower() not in allowed_hosts
        or parsed.username
        or parsed.password
        or not parsed.path.strip('/')
    ):
        raise ValueError('WhatsApp үчүн шилтеме жазыңыз: https://wa.me/996700123456')

    return value
