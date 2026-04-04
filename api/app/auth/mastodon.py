"""Mastodon OAuth — domain validation, dynamic client registration, cache management."""

import ipaddress
import logging
import os
import socket
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import MastodonOAuthClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Blocked instances — known-bad Mastodon-compatible servers
# ---------------------------------------------------------------------------
_BLOCKED_INSTANCES: frozenset[str] = frozenset({
    "gab.com",
    "truthsocial.com",
    "spinster.xyz",
})

# ---------------------------------------------------------------------------
# Domain registration rate limiting (in-memory, per-IP)
# ---------------------------------------------------------------------------
_domain_registrations: dict[str, list[float]] = {}
_DOMAIN_RATE_LIMIT = 3  # max new domains per hour per IP
_DOMAIN_RATE_WINDOW = 3600  # seconds


def _check_domain_rate_limit(ip: str) -> None:
    """Raise 429 if IP has registered too many new domains recently."""
    now = time.time()
    timestamps = _domain_registrations.get(ip, [])
    # Prune old entries
    timestamps = [t for t in timestamps if now - t < _DOMAIN_RATE_WINDOW]
    _domain_registrations[ip] = timestamps

    if len(timestamps) >= _DOMAIN_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail={"error": "domain_registration_rate_limited"},
        )


def _record_domain_registration(ip: str) -> None:
    """Record a new domain registration for rate limiting."""
    _domain_registrations.setdefault(ip, []).append(time.time())


# ---------------------------------------------------------------------------
# Domain validation
# ---------------------------------------------------------------------------

def validate_mastodon_domain(domain: str) -> str:
    """Validate and normalize a Mastodon instance domain.

    Rejects private IP ranges, localhost, blocked instances, and invalid
    hostnames. Returns the normalized domain string.
    """
    domain = domain.strip().lower()

    # Strip scheme if accidentally provided
    if "://" in domain:
        parsed = urlparse(domain)
        domain = parsed.hostname or domain

    if not domain or " " in domain:
        raise ValueError("Invalid domain format")

    # Check blocklist before DNS resolution
    if domain in _BLOCKED_INSTANCES:
        raise HTTPException(
            status_code=400,
            detail={"error": "blocked_instance", "message": f"Instance '{domain}' is not allowed"},
        )

    # DNS resolution
    try:
        ip_addr = socket.gethostbyname(domain)
    except socket.gaierror:
        raise ValueError("Could not resolve domain")

    ip = ipaddress.ip_address(ip_addr)
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
        raise ValueError("Domain resolves to private or restricted IP")

    return domain


# ---------------------------------------------------------------------------
# Client registration with upsert and TTL
# ---------------------------------------------------------------------------

async def get_or_register_client(
    db: Session, domain: str, client_ip: str | None = None
) -> MastodonOAuthClient:
    """Get registered client from DB, or register dynamically.

    Checks expires_at on cached clients — expired or NULL entries trigger
    re-registration.  Uses ON CONFLICT DO NOTHING for race-condition safety.
    """
    client = db.query(MastodonOAuthClient).filter_by(domain=domain).first()
    if client:
        # Check expiry — None (legacy rows) treated as expired
        if client.expires_at is not None:
            exp = client.expires_at
            # SQLite returns naive datetimes; treat as UTC
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp > datetime.now(timezone.utc):
                return client
        # Expired or legacy — delete and re-register
        db.delete(client)
        db.flush()

    # Rate limit new domain registrations
    if client_ip:
        _check_domain_rate_limit(client_ip)

    # Dynamic registration
    api_url = os.environ.get("OVID_API_URL", "http://localhost:8000")
    redirect_uris = f"{api_url}/v1/auth/mastodon/callback"
    client_name = "OVID"
    scopes = "read"
    website = api_url

    registration_url = f"https://{domain}/api/v1/apps"
    try:
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.post(
                registration_url,
                data={
                    "client_name": client_name,
                    "redirect_uris": redirect_uris,
                    "scopes": scopes,
                    "website": website
                },
                timeout=10.0
            )
    except httpx.TimeoutException:
        logger.warning("mastodon_registration timeout domain=%s", domain)
        raise HTTPException(
            status_code=504,
            detail={"error": "gateway_timeout", "reason": "Timeout communicating with Mastodon instance"},
        )
    except Exception:
        logger.warning("mastodon_registration error domain=%s", domain, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={"error": "bad_gateway", "reason": "Failed to connect to Mastodon instance"},
        )

    if resp.status_code != 200:
        logger.warning("mastodon_registration failed domain=%s status=%d", domain, resp.status_code)
        raise HTTPException(
            status_code=502,
            detail={"error": "bad_gateway", "reason": "Registration failed"},
        )

    data = resp.json()
    client_id = data.get("client_id")
    client_secret = data.get("client_secret")

    if not client_id or not client_secret:
        logger.warning("mastodon_registration malformed domain=%s", domain)
        raise HTTPException(
            status_code=502,
            detail={"error": "bad_gateway", "reason": "Malformed registration response"},
        )

    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    # Use try/except for upsert safety — handles concurrent inserts
    try:
        new_client = MastodonOAuthClient(
            domain=domain,
            client_id=client_id,
            client_secret=client_secret,
            expires_at=expires_at,
        )
        db.add(new_client)
        db.commit()
        db.refresh(new_client)
    except Exception:
        # Race condition: another request inserted first — rollback and re-query
        db.rollback()
        new_client = db.query(MastodonOAuthClient).filter_by(domain=domain).first()
        if new_client is None:
            raise HTTPException(
                status_code=500,
                detail={"error": "internal_error", "reason": "Client registration failed"},
            )

    if client_ip:
        _record_domain_registration(client_ip)

    logger.info("mastodon_registration success domain=%s", domain)
    return new_client
