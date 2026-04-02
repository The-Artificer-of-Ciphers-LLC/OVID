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
