"""With ADMIN_DOMAIN set, the panel lives on its own host and the API host has no /admin."""

from starlette.responses import JSONResponse, RedirectResponse

from mysite.api.errors import error_detail
from mysite.settings import admin_domain


class AdminHostMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        domain = admin_domain()
        if domain is None or scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        host = dict(scope.get('headers', [])).get(b'host', b'').decode('latin-1')
        on_panel_host = host.rsplit(':', 1)[0].casefold() == domain
        path = scope.get('path', '')
        if on_panel_host and path == '/' and scope['type'] == 'http':
            return await RedirectResponse('/admin/')(scope, receive, send)
        panel_path = path == '/admin' or path.startswith('/admin/')
        if path.startswith('/media/') or panel_path == on_panel_host:
            return await self.app(scope, receive, send)
        if scope['type'] == 'websocket':
            return await send({'type': 'websocket.close', 'code': 1008})
        await JSONResponse({'detail': error_detail('not_found')}, status_code=404)(
            scope, receive, send
        )
