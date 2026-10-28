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
