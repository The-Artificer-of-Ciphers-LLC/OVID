"""OVID API client — wraps GET /v1/disc/{fingerprint} and POST /v1/disc."""

from __future__ import annotations

import os

import click
import requests


class OVIDClient:
    """HTTP wrapper for the OVID disc metadata API.

    Uses ``requests.Session`` for connection reuse and consistent headers.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.environ.get("OVID_API_URL", "http://localhost:8000")
        ).rstrip("/")
        self.token = token or os.environ.get("OVID_TOKEN")
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def lookup(self, fingerprint: str) -> dict | None:
        """GET /v1/disc/{fingerprint}.

        Returns parsed JSON on 200, ``None`` on 404.
        Raises ``click.ClickException`` on other HTTP errors.
        """
        url = f"{self.base_url}/v1/disc/{fingerprint}"
        resp = self._session.get(url)

        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            return None

        self._raise_for_status(resp, "lookup")

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def submit(self, payload: dict) -> dict:
        """POST /v1/disc with Bearer token header.

        Returns response JSON on 201.
        Raises ``click.ClickException`` on auth/conflict/server errors.
        """
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        url = f"{self.base_url}/v1/disc"
        resp = self._session.post(url, json=payload, headers=headers)

        if resp.status_code == 201:
            return resp.json()

        self._raise_for_status(resp, "submit")

    # ------------------------------------------------------------------
    # Sets
    # ------------------------------------------------------------------

    def search_sets(self, query: str, page: int = 1) -> dict | None:
        """Search disc sets by release title or edition name.

        GET /v1/set?q={query}&page={page}

        Returns:
            Parsed JSON response with results, page, total_pages, total_results.
            None if the request failed.
        """
        url = f"{self.base_url}/v1/set"
        resp = self._session.get(url, params={"q": query, "page": page})
        if resp.status_code == 200:
            return resp.json()
        return None

    def create_set(
        self,
        release_id: str,
        edition_name: str | None = None,
        total_discs: int = 1,
    ) -> dict:
        """Create a new disc set.

        POST /v1/set with Bearer token.

        Args:
            release_id: UUID of the release this set belongs to.
            edition_name: Optional edition name (e.g., "Extended Edition").
            total_discs: Number of discs in the set.

        Returns:
            Parsed JSON response with id, release_id, edition_name,
            total_discs, created_at.

        Raises:
            click.ClickException: On HTTP error.
        """
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        url = f"{self.base_url}/v1/set"
        payload: dict[str, str | int] = {
            "release_id": release_id,
            "total_discs": total_discs,
        }
        if edition_name:
            payload["edition_name"] = edition_name
        resp = self._session.post(url, json=payload, headers=headers)
        if resp.status_code == 201:
            return resp.json()
        self._raise_for_status(resp, "create_set")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _raise_for_status(resp: requests.Response, action: str) -> None:
        """Raise a ``click.ClickException`` with status code and message."""
        try:
            body = resp.json()
            detail = body.get("message") or body.get("error") or resp.text
        except (ValueError, KeyError):
            detail = resp.text

        raise click.ClickException(
            f"API {action} failed ({resp.status_code}): {detail}"
        )
