"""Keep the admin routes public at the network layer; account auth is enforced separately."""


class AdminAccessMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        return await self.app(scope, receive, send)
