"""TMDB search module — wraps tmdbv3api for movie lookup.

Gracefully degrades when TMDB_API_KEY is not set (returns empty results).
"""

from __future__ import annotations

import os

from tmdbv3api import Movie, TMDb


def search_movies(query: str) -> list[dict]:
    """Search TMDB for movies matching *query*.

    Returns a list of ``{id, title, year, overview}`` dicts.
    Returns an empty list if ``TMDB_API_KEY`` is not set or the search
    raises an error.
    """
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        return []

    try:
        tmdb = TMDb()
        tmdb.api_key = api_key
        movie_api = Movie()
        results = movie_api.search(query)
    except Exception:
        return []

    out: list[dict] = []
    for r in results:
        release_date = getattr(r, "release_date", "") or ""
        year = release_date[:4] if len(release_date) >= 4 else ""
        out.append({
            "id": r.id,
            "title": r.title,
            "year": year,
            "overview": getattr(r, "overview", ""),
        })
    return out


def get_movie(tmdb_id: int) -> dict | None:
    """Fetch TMDB movie details by ID.

    Returns ``{id, title, year, overview, imdb_id}`` or ``None`` on error.
    """
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        return None

    try:
        tmdb = TMDb()
        tmdb.api_key = api_key
        movie_api = Movie()
        details = movie_api.details(tmdb_id)
    except Exception:
        return None

    release_date = getattr(details, "release_date", "") or ""
    year = release_date[:4] if len(release_date) >= 4 else ""

    # imdb_id may be in details directly or via external_ids
    imdb_id = getattr(details, "imdb_id", None) or ""

    return {
        "id": details.id,
        "title": details.title,
        "year": year,
        "overview": getattr(details, "overview", ""),
        "imdb_id": imdb_id,
    }
