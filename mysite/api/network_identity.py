import os
from ipaddress import IPv6Address, ip_address, ip_network


def client_network(address):
    try:
        identity = ip_address(address)
    except ValueError:
        return address
    if isinstance(identity, IPv6Address):
        if identity.ipv4_mapped:
            return str(identity.ipv4_mapped)
        return str(ip_network(f'{identity}/64', strict=False))
    return str(identity)


def request_network(request):
    return client_network(request.client.host if request.client else 'unknown')


def rate_limits_enabled():
    return os.getenv('RATE_LIMIT_ENABLED', 'true').strip().casefold() not in {'0', 'false', 'no'}
