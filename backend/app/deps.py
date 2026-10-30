from __future__ import annotations

import ipaddress

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import Role, User
from app.schemas import TokenUser
from app.security import cookie_name, decode_token, require_csrf, token_user_from_payload

settings = get_settings()

_IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def _parse_ip(raw: str | None) -> _IPAddress | None:
    """Parse an address from a header or socket peer, tolerating ports and IPv6 brackets."""
    if not raw:
        return None
    raw = raw.strip().strip('"')
    if raw.startswith("["):  # [::1] or [::1]:443
        raw = raw[1:].split("]", 1)[0]
    elif raw.count(":") == 1:  # 1.2.3.4:5678
        raw = raw.split(":", 1)[0]
    try:
        addr = ipaddress.ip_address(raw)
    except ValueError:
        return None
    # Unwrap ::ffff:a.b.c.d so one client isn't seen as two identities.
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        return addr.ipv4_mapped
    return addr


def _is_trusted(addr: _IPAddress) -> bool:
    return any(addr in net for net in settings.trusted_proxy_networks)


def get_client_ip(request: Request) -> str:
    """Resolve the real client IP, honouring forwarded headers only from trusted proxies.

    The socket peer is authoritative unless it is in TRUSTED_PROXIES. For a trusted peer,
    X-Forwarded-For is walked right-to-left (the end appended by our own proxies is the only
    part a client can't forge), skipping further trusted hops; the first untrusted address is
    the client. X-Real-IP is the fallback. Anything unparsable is ignored, never trusted.
    """
    peer = _parse_ip(request.client.host if request.client else None)
    if peer is None:
        return "unknown"
    if not _is_trusted(peer):
        return str(peer)

    for hop in reversed(request.headers.get("x-forwarded-for", "").split(",")):
        addr = _parse_ip(hop)
        if addr is None:
            # Malformed hop: stop rather than skip past it to an attacker-controlled value.
            break
        if not _is_trusted(addr):
            return str(addr)

    real_ip = _parse_ip(request.headers.get("x-real-ip"))
    if real_ip is not None and not _is_trusted(real_ip):
        return str(real_ip)
    return str(peer)


def client_rate_key(request: Request) -> str:
    """Stable rate-limit identity: IPv4 as-is, IPv6 collapsed to its /64 (a single subscriber
    controls a whole /64, so per-address limits are trivially evaded)."""
    ip = get_client_ip(request)
    addr = _parse_ip(ip)
    if isinstance(addr, ipaddress.IPv6Address):
        return str(ipaddress.ip_network(f"{addr}/64", strict=False).network_address) + "/64"
    return ip


def _site_from_request(request: Request) -> str:
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    if settings.admin_origin in origin or request.headers.get("X-Nexus-Site") == "admin":
        return "admin"
    host = request.headers.get("host", "")
    if "8081" in host:
        return "admin"
    return "chat"


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    require_csrf(request)
    site = _site_from_request(request)
    token = request.cookies.get(cookie_name(site))
    if not token:
        # admin cookie might be used if host detection failed
        token = request.cookies.get(settings.admin_cookie) or request.cookies.get(settings.chat_cookie)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(token)
    user = await db.get(User, token_user_from_payload(payload).id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Account disabled")
    return user


async def get_current_user_optional(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    try:
        return await get_current_user(request, db)
    except HTTPException:
        return None


def require_roles(*roles: Role):
    async def _inner(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return _inner


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user
