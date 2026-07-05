# OVID API Reference

**Base URL:** `http://localhost:8000` (development) / `https://api.oviddb.org` (production)
**Version:** v1
**Format:** All responses are JSON. All responses include an `X-Request-ID` header.

---

## Authentication

**Read endpoints** (GET) are unauthenticated — no token needed.

**Write endpoints** (POST) require a Bearer token in the `Authorization` header:

```
Authorization: Bearer <jwt_token>
```

Tokens are obtained via OAuth login flows (GitHub, Apple Sign-In, or IndieAuth).

---

## Endpoints

### Health Check

```
GET /health
```

Returns server liveness status.

**Response 200:**
```json
{
  "status": "ok"
}
```

---

### Look Up Disc by Fingerprint

```
GET /v1/disc/{fingerprint}
```

Returns full disc metadata including release info, titles, and tracks. The path value can be a Primary Fingerprint or a Lookup Alias. The response `fingerprint` is always the disc's Primary Fingerprint.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `fingerprint` | string | Primary Fingerprint or Lookup Alias (e.g. `dvd1-a3f92c...` or `dvdread1-...`) |

**Response 200 — disc found:**

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "fingerprint": "dvd1-a3f92c1b4e8d7f6a2c9e0b1d3f5a8c2e4f6b8d0a",
  "format": "DVD",
  "status": "verified",
  "confidence": "high",
  "region_code": "1",
  "upc": null,
  "edition_name": "Special Edition",
  "disc_number": 1,
  "total_discs": 2,
  "releases": [
    {
      "title": "The Lord of the Rings: The Fellowship of the Ring",
      "year": 2001,
      "content_type": "movie",
      "tmdb_id": 120,
      "imdb_id": "tt0120737"
    }
  ],
  "titles": [
    {
      "title_index": 1,
      "title_type": "main_feature",
      "duration_secs": 10800,
      "chapter_count": 43,
      "audio_tracks": [
        {
          "track_index": 1,
          "language_code": "en",
          "codec": "AC3",
          "channels": 6
        }
      ],
      "subtitle_tracks": [
        {
          "track_index": 1,
          "language_code": "en",
          "codec": null
        }
      ]
    }
  ]
}
```

**Confidence values:**

| Value | Meaning |
|-------|---------|
| `high` | Verified by 2+ contributors |
| `medium` | Single unverified submission |

**Response 404 — not found:**

```json
{
  "request_id": "550e8400-...",
  "error": "disc_not_found",
  "message": "No disc with fingerprint dvd1-a3f92c..."
}
```

---

### Submit a New Disc

```
POST /v1/disc
Authorization: Bearer <token>
Content-Type: application/json
```

Creates a new disc entry with release metadata, titles, and tracks in a single transaction.

**Request body:**

```json
{
  "fingerprint": "dvd1-a3f92c1b4e8d7f6a2c9e0b1d3f5a8c2e4f6b8d0a",
  "fingerprint_aliases": ["dvdread1-7d83f1..."],
  "format": "DVD",
  "region_code": "1",
  "edition_name": "Special Edition",
  "disc_number": 1,
  "total_discs": 2,
  "release": {
    "title": "The Lord of the Rings: The Fellowship of the Ring",
    "year": 2001,
    "content_type": "movie",
    "tmdb_id": 120,
    "imdb_id": "tt0120737"
  },
  "titles": [
    {
      "title_index": 1,
      "title_type": "main_feature",
      "duration_secs": 10800,
      "chapter_count": 43,
      "audio_tracks": [
        {
          "track_index": 1,
          "language_code": "en",
          "codec": "AC3",
          "channels": 6
        }
      ],
      "subtitle_tracks": [
        {
          "track_index": 1,
          "language_code": "en"
        }
      ]
    }
  ]
}
```

**Selected fields:**

| Field | Type | Constraints |
|-------|------|-------------|
| `fingerprint` | string | Non-empty Primary Fingerprint for new records |
| `fingerprint_aliases` | array of strings | Optional; non-empty Lookup Alias values |
| `format` | string | Non-empty |
| `release.title` | string | Non-empty |
| `release.content_type` | string | Non-empty |
| `titles` | array | At least one title |

**Response 201 — created:**

```json
{
  "request_id": "550e8400-...",
  "disc_id": "uuid-here",
  "fingerprint": "dvd1-a3f92c...",
  "status": "unverified",
  "message": "Disc submitted successfully"
}
```

**Response 401 — unauthenticated:**

```json
{
  "request_id": "550e8400-...",
  "error": "missing_token",
  "message": "Authorization header required"
}
```

**Response 409 — duplicate:**

```json
{
  "request_id": "550e8400-...",
  "error": "duplicate_fingerprint",
  "message": "A disc with this fingerprint already exists"
}
```

**Response 409 — identity conflict:**

```json
{
  "request_id": "550e8400-...",
  "error": "identity_conflict",
  "message": "Disc Identity 'dvdread1-...' already resolves to another disc"
}
```

---

### Confirming an Existing Disc

There is no standalone verify endpoint. A disc is promoted from `unverified` to
`verified` when a **second, distinct contributor** re-submits the same disc
through `POST /v1/disc` (see above) — the server independently recomputes the
disc's structure from their submission and compares it against the withheld
stored structure. This is proof-of-possession re-submission, not a bodyless
verify call; see [Contributing](contributing.md#2-confirm-existing-discs).

A confirmation attempt may also fail closed:

**Response 429 — confirmation cooldown active:**

```json
{
  "request_id": "550e8400-...",
  "error": "rate_limited",
  "message": "Confirmation cooldown active"
}
```

Includes a `Retry-After` header (seconds). This is a per-account Postgres-backed
cooldown floor on confirmation actions — distinct from the general API rate
limiter (see [Rate Limiting Notes](#rate-limiting-notes) below).

**Response 403 — insufficient trust signal:**

```json
{
  "request_id": "550e8400-...",
  "error": "insufficient_trust",
  "message": "Confirmation rejected by anti-Sybil weighting"
}
```

**Response 404 — not found:**

```json
{
  "request_id": "550e8400-...",
  "error": "disc_not_found",
  "message": "No disc with fingerprint dvd1-a3f92c..."
}
```

---

### Search Releases

```
GET /v1/search?q={query}&type={type}&year={year}&page={page}
```

Search releases by title with optional filters. Returns paginated results.

**Query parameters:**

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `q` | Yes | — | Search query (case-insensitive title match) |
| `type` | No | (all) | Filter by content type: `movie`, `tv_series`, `special` |
| `year` | No | (all) | Filter by release year |
| `page` | No | `1` | Page number (20 results per page) |

**Response 200:**

```json
{
  "request_id": "550e8400-...",
  "query": "matrix",
  "page": 1,
  "total": 3,
  "results": [
    {
      "title": "The Matrix",
      "year": 1999,
      "content_type": "movie",
      "tmdb_id": 603,
      "imdb_id": "tt0133093",
      "disc_count": 2
    }
  ]
}
```

**Response 400 — missing query:**

```json
{
  "request_id": "550e8400-...",
  "error": "missing_query",
  "message": "Query parameter 'q' is required"
}
```

---

## Authentication Endpoints

### GitHub OAuth

```
GET /v1/auth/github/login          → Redirects to GitHub authorization
GET /v1/auth/github/callback       → Handles GitHub callback, returns JWT
```

### Apple Sign-In

```
GET /v1/auth/apple/login           → Redirects to Apple authorization
POST /v1/auth/apple/callback       → Handles Apple callback, returns JWT
```

### IndieAuth

```
GET /v1/auth/indieauth/login?url=  → Discovers endpoints, redirects to authorization
GET /v1/auth/indieauth/callback    → Handles IndieAuth callback, returns JWT
```

### Current User

```
GET /v1/auth/me
Authorization: Bearer <token>
```

Returns the authenticated user's profile.

**Response 200:**

```json
{
  "id": "uuid-here",
  "email": "user@example.com",
  "display_name": "Jane Doe",
  "role": "contributor",
  "created_at": "2026-04-01T12:00:00Z"
}
```

---

## Error Response Format

All error responses use a consistent shape:

```json
{
  "request_id": "uuid",
  "error": "error_code",
  "message": "Human-readable description"
}
```

**Error codes:**

| HTTP | Code | Description |
|------|------|-------------|
| 400 | `missing_query` | Required query parameter missing |
| 400 | `invalid_url` | Invalid IndieAuth URL |
| 401 | `missing_token` | No Authorization header |
| 401 | `invalid_token` | Token malformed or signature invalid |
| 401 | `expired_token` | Token has expired |
| 404 | `disc_not_found` | No disc matches the fingerprint |
| 409 | `duplicate_fingerprint` | Fingerprint already exists |
| 422 | (Pydantic) | Request body validation failure |
| 501 | `not_configured` | OAuth provider not configured |
| 502 | `provider_error` | Upstream OAuth provider error |

---

## Rate Limiting Notes

OVID has two independent throttling mechanisms — they are not redundant and
serve different purposes:

- **Confirmation cooldown** (this endpoint, `POST /v1/disc` re-submission
  path) — a permanent, Postgres-backed, per-account cap on confirmation
  actions. It is part of the anti-Sybil trust model, not general API-abuse
  protection, and holds regardless of how many gunicorn workers are running.
- **General API rate limiter** — a separate `slowapi`-based limiter across all
  endpoints, backed by Redis in multi-worker deployments (see
  [privacy policy](privacy.md#confirmation-cooldown-vs-general-api-rate-limiting)
  for the full note).

---

## Request Tracing

Every response includes an `X-Request-ID` header containing a UUID v4. Include this in bug reports for server-side log correlation.

---

## OpenAPI / Swagger

When running locally, auto-generated interactive API documentation is available at:

- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
