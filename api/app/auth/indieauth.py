"""IndieAuth endpoint discovery and PKCE helpers.

IndieAuth uses link-rel discovery to find a user's authorization and token
endpoints from their personal URL.  PKCE (RFC 7636) protects the code exchange.
"""

import base64
import hashlib
import logging
import os
import re
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Timeout for discovery fetch (seconds)
_DISCOVERY_TIMEOUT = 10.0


class DiscoveryError(Exception):
    """Raised when IndieAuth endpoint discovery fails."""


def validate_url(url: str, *, allow_localhost: bool = False) -> str:
    """Validate and normalise an IndieAuth profile URL.

    Rules:
    - Must be https (or http://localhost for dev)
    - Must have a host
    - Trailing slash normalisation

    Returns the normalised URL.  Raises ValueError on invalid input.
    """
    parsed = urlparse(url)

    if not parsed.scheme:
        # Try adding https if bare domain
        url = f"https://{url}"
        parsed = urlparse(url)

    if parsed.scheme == "http":
        if allow_localhost and parsed.hostname in ("localhost", "127.0.0.1"):
            pass  # OK for dev
        else:
            raise ValueError("IndieAuth URLs must use https")
    elif parsed.scheme != "https":
        raise ValueError("IndieAuth URLs must use https")

    if not parsed.hostname:
        raise ValueError("IndieAuth URL must have a host")

    # Normalise: ensure path has trailing slash if it's just the domain
    if not parsed.path or parsed.path == "/":
        url = f"{parsed.scheme}://{parsed.netloc}/"
    
    return url


async def discover_endpoints(url: str) -> dict[str, str]:
    """Fetch *url* and discover IndieAuth endpoints from HTML link rels.

    Looks for:
    - ``<link rel="authorization_endpoint" href="...">``
    - ``<link rel="token_endpoint" href="...">``

    Also checks HTTP Link headers.

    Returns ``{"authorization_endpoint": ..., "token_endpoint": ...}``.
    Raises ``DiscoveryError`` on failure.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, timeout=_DISCOVERY_TIMEOUT)
            resp.raise_for_status()
    except httpx.TimeoutException:
        logger.warning("indieauth_discovery timeout url=%s", url)
        raise DiscoveryError("Endpoint discovery timed out")
    except httpx.HTTPError as e:
        logger.warning("indieauth_discovery fetch_error url=%s detail=%s", url, str(e))
        raise DiscoveryError(f"Failed to fetch URL: {e}")

    endpoints: dict[str, str] = {}

    # Check HTTP Link headers first
    link_header = resp.headers.get("link", "")
    for rel_name in ("authorization_endpoint", "token_endpoint"):
        # Match: <https://example.com/auth>; rel="authorization_endpoint"
        pattern = r'<([^>]+)>\s*;\s*rel="?' + re.escape(rel_name) + r'"?'
        m = re.search(pattern, link_header)
        if m:
            endpoints[rel_name] = m.group(1)

    # Parse HTML for <link rel="..."> tags (simple regex — no BS4 needed)
    body = resp.text
    for rel_name in ("authorization_endpoint", "token_endpoint"):
        if rel_name in endpoints:
            continue  # already found in Link header
        # Match <link rel="authorization_endpoint" href="...">
        # Handle attributes in either order
        patterns = [
            rf'<link[^>]+rel=["\']?{re.escape(rel_name)}["\']?[^>]+href=["\']([^"\']+)["\']',
            rf'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']?{re.escape(rel_name)}["\']?',
        ]
        for pat in patterns:
            m = re.search(pat, body, re.IGNORECASE)
            if m:
                endpoints[rel_name] = m.group(1)
                break

    if "authorization_endpoint" not in endpoints:
        raise DiscoveryError("No authorization_endpoint found")
    if "token_endpoint" not in endpoints:
        raise DiscoveryError("No token_endpoint found")

    logger.info(
        "indieauth_discovery url=%s auth_endpoint=%s token_endpoint=%s",
        url, endpoints["authorization_endpoint"], endpoints["token_endpoint"],
    )
    return endpoints


def generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge (S256).

    Returns ``(code_verifier, code_challenge)``.
    """
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge
