"""Restrict the SQLAdmin and admin API surface to configured source networks."""

import ipaddress
import json
import os


def _allowed_networks():
    configured = os.getenv('ADMIN_ALLOWED_IPS', '127.0.0.1/32,::1/128')
    networks = []
    for value in configured.split(','):
        value = value.strip()
        if value:
            networks.append(ipaddress.ip_network(value, strict=False))
    if not networks:
        raise RuntimeError('ADMIN_ALLOWED_IPS must contain at least one IP or network')
    return tuple(networks)


class AdminAccessMiddleware:
    def __init__(self, app):
        self.app = app
        self.networks = _allowed_networks()

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        path = scope.get('path', '')
        if path != '/admin' and not path.startswith('/admin/'):
            return await self.app(scope, receive, send)
        client = scope.get('client')
        try:
            address = ipaddress.ip_address(client[0]) if client else None
            allowed = address is not None and any(address in network for network in self.networks)
        except ValueError:
            allowed = False
        if allowed:
            return await self.app(scope, receive, send)
        if scope['type'] == 'websocket':
            await send({'type': 'websocket.close', 'code': 1008})
            return
        body = json.dumps({'detail': 'Admin access is restricted by source IP policy'}).encode()
        await send(
            {
                'type': 'http.response.start',
                'status': 403,
                'headers': [
                    (b'content-type', b'application/json'),
                    (b'content-length', str(len(body)).encode()),
                ],
            }
        )
        await send({'type': 'http.response.body', 'body': body})
