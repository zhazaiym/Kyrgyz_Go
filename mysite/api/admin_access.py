"""Restrict the SQLAdmin and admin API surface to configured source networks."""

import ipaddress
import json
import logging
import os

from mysite.api.network_identity import client_network

logger = logging.getLogger(__name__)


def _allowed_networks():
    configured = os.getenv('ADMIN_ALLOWED_IPS', '127.0.0.1/32,::1/128')
    networks = []
    try:
        for value in configured.split(','):
            value = value.strip()
            if value:
                networks.append(ipaddress.ip_network(value, strict=False))
    except ValueError:
        logger.exception('Invalid ADMIN_ALLOWED_IPS; admin access is disabled')
        return ()
    if not networks:
        logger.error('ADMIN_ALLOWED_IPS is empty; admin access is disabled')
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
            identity = client_network(client[0]) if client else None
            raw_address = ipaddress.ip_address(client[0]) if client else None
            address = (
                ipaddress.ip_address(identity) if identity and '/' not in identity else raw_address
            )
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
