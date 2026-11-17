"""Every API path ends with a slash; a request without it is served the same, with no redirect.

A redirect would break browser requests from the site: a CORS preflight may not
follow it. SQLAdmin pages, media, the API schema and metrics keep their own paths.
"""

UNCHANGED = ('/admin', '/media/', '/docs', '/redoc', '/openapi.json', '/metrics')


class TrailingSlashMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        if (
            scope['type'] == 'http'
            and not path.endswith('/')
            and not path.startswith(UNCHANGED)
            and '.' not in path.rsplit('/', 1)[-1]
        ):
            scope = {**scope, 'path': path + '/'}
            if 'raw_path' in scope:
                scope['raw_path'] += b'/'
        await self.app(scope, receive, send)
