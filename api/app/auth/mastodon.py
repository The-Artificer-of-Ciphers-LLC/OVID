import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import MastodonOAuthClient

logger = logging.getLogger(__name__)

def validate_mastodon_domain(domain: str) -> str:
    """Validate Mastodon domain to prevent SSRF.
    
    Rejects private IP ranges, localhost, and invalid hostnames.
    """
    domain = domain.strip().lower()
    
    # Strip scheme if accidentally provided
    if "://" in domain:
        parsed = urlparse(domain)
        domain = parsed.hostname or domain
        
    if not domain or " " in domain:
        raise ValueError("Invalid domain format")
        
    # Dual-stack DNS resolution (IPv4 + IPv6). An AAAA-only or dual-stack host
    # pointing at a private/loopback IPv6 address must not slip past an
    # IPv4-only check (AUTH-05).
    try:
        infos = socket.getaddrinfo(domain, None)
    except socket.gaierror:
        raise ValueError("Could not resolve domain")

    resolved_ips = {info[4][0] for info in infos}
    for ip_str in resolved_ips:
        ip = ipaddress.ip_address(ip_str)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
        ):
            raise ValueError("Domain resolves to private or restricted IP")

    return domain


async def get_or_register_client(db: Session, domain: str) -> MastodonOAuthClient:
    """Get registered client from DB, or register dynamically."""
    client = db.query(MastodonOAuthClient).filter_by(domain=domain).first()
    if client:
        return client
        
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
        raise HTTPException(status_code=504, detail={"error": "gateway_timeout", "reason": "Timeout communicating with Mastodon instance"})
    except Exception as e:
        # LO-02: log the real exception server-side only — reflecting str(e) to
        # the client can leak internal DNS/host/connection details for a
        # user-supplied Mastodon domain (a mild SSRF-adjacent info leak).
        logger.warning("mastodon_registration error domain=%s detail=%s", domain, str(e))
        raise HTTPException(status_code=502, detail={"error": "bad_gateway", "reason": "Connection error communicating with the Mastodon instance"})
        
    if resp.status_code != 200:
        logger.warning("mastodon_registration failed domain=%s status=%d", domain, resp.status_code)
        raise HTTPException(status_code=502, detail={"error": "bad_gateway", "reason": f"Registration failed with status {resp.status_code}"})
        
    data = resp.json()
    client_id = data.get("client_id")
    client_secret = data.get("client_secret")
    
    if not client_id or not client_secret:
        logger.warning("mastodon_registration malformed domain=%s", domain)
        raise HTTPException(status_code=502, detail={"error": "bad_gateway", "reason": "Malformed registration response"})
        
    new_client = MastodonOAuthClient(
        domain=domain,
        client_id=client_id,
        client_secret=client_secret
    )
    db.add(new_client)
    db.commit()
    db.refresh(new_client)
    logger.info("mastodon_registration success domain=%s", domain)
    return new_client
