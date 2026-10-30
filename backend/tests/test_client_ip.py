import ipaddress

import pytest
from starlette.requests import Request

import app.deps as deps


class _Settings:
    def __init__(self, nets):
        self.trusted_proxy_networks = tuple(ipaddress.ip_network(n) for n in nets)


def make(peer, headers=None):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request(
        {"type": "http", "headers": raw, "client": (peer, 1234) if peer else None, "method": "GET", "path": "/"}
    )


@pytest.fixture
def trust(monkeypatch):
    def _set(*nets):
        monkeypatch.setattr(deps, "settings", _Settings(nets))

    return _set


def test_untrusted_peer_ignores_forwarded_headers(trust):
    trust("10.0.0.0/8")
    r = make("203.0.113.9", {"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "5.6.7.8"})
    assert deps.get_client_ip(r) == "203.0.113.9"


def test_default_trusts_nothing(trust):
    trust()
    assert deps.get_client_ip(make("10.0.0.2", {"X-Forwarded-For": "1.2.3.4"})) == "10.0.0.2"


def test_trusted_peer_uses_xff(trust):
    trust("10.0.0.0/8")
    assert deps.get_client_ip(make("10.0.0.2", {"X-Forwarded-For": "198.51.100.7"})) == "198.51.100.7"


def test_spoofed_left_entries_are_ignored(trust):
    trust("10.0.0.0/8")
    r = make("10.0.0.2", {"X-Forwarded-For": "6.6.6.6, 198.51.100.7, 10.0.0.5"})
    assert deps.get_client_ip(r) == "198.51.100.7"


def test_malformed_hop_is_not_skipped(trust):
    trust("10.0.0.0/8")
    r = make("10.0.0.2", {"X-Forwarded-For": "6.6.6.6, garbage", "X-Real-IP": "198.51.100.7"})
    assert deps.get_client_ip(r) == "198.51.100.7"  # falls back to X-Real-IP, never 6.6.6.6


def test_x_real_ip_fallback_and_ports(trust):
    trust("10.0.0.0/8")
    assert deps.get_client_ip(make("10.0.0.2", {"X-Real-IP": "198.51.100.7:5555"})) == "198.51.100.7"
    assert deps.get_client_ip(make("10.0.0.2", {"X-Forwarded-For": "[2001:db8::1]:443"})) == "2001:db8::1"


def test_falls_back_to_peer_when_nothing_usable(trust):
    trust("10.0.0.0/8")
    assert deps.get_client_ip(make("10.0.0.2", {"X-Forwarded-For": "10.0.0.7"})) == "10.0.0.2"
    assert deps.get_client_ip(make(None)) == "unknown"


def test_ipv4_mapped_normalised(trust):
    trust()
    assert deps.get_client_ip(make("::ffff:203.0.113.9")) == "203.0.113.9"


def test_ipv6_rate_key_collapses_to_64(trust):
    trust()
    a = deps.client_rate_key(make("2001:db8:1:2::1"))
    b = deps.client_rate_key(make("2001:db8:1:2:ffff::9"))
    c = deps.client_rate_key(make("2001:db8:1:3::1"))
    assert a == b and a != c
    assert deps.client_rate_key(make("203.0.113.9")) == "203.0.113.9"
