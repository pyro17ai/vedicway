from __future__ import annotations

import ipaddress
from collections.abc import Iterable


IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

YOOKASSA_NOTIFICATION_NETWORKS: tuple[IPNetwork, ...] = tuple(
    ipaddress.ip_network(value)
    for value in (
        "185.71.76.0/27",
        "185.71.77.0/27",
        "77.75.153.0/25",
        "77.75.156.11/32",
        "77.75.156.35/32",
        "77.75.154.128/25",
        "2a02:5180::/32",
    )
)


def _address(value: str) -> IPAddress | None:
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _in_networks(address: IPAddress, networks: Iterable[IPNetwork]) -> bool:
    return any(address.version == network.version and address in network for network in networks)


def is_yookassa_source(value: str) -> bool:
    address = _address(value)
    return address is not None and _in_networks(address, YOOKASSA_NOTIFICATION_NETWORKS)


def effective_client_ip(
    peer_ip: str,
    forwarded_for: str | None,
    trusted_proxy_networks: Iterable[IPNetwork],
) -> str:
    """Return the first untrusted hop, walking a trusted proxy chain right-to-left."""
    peer = _address(peer_ip)
    if peer is None:
        return peer_ip
    trusted = tuple(trusted_proxy_networks)
    if not forwarded_for or not _in_networks(peer, trusted):
        return str(peer)

    forwarded: list[IPAddress] = []
    for raw in forwarded_for.split(","):
        parsed = _address(raw)
        if parsed is None:
            return str(peer)
        forwarded.append(parsed)
    if not forwarded:
        return str(peer)
    for candidate in reversed(forwarded):
        if not _in_networks(candidate, trusted):
            return str(candidate)
    return str(forwarded[0])
