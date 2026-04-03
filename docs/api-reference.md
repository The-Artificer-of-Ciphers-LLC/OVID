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

Returns full disc metadata including release info, titles, and tracks.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `fingerprint` | string | OVID fingerprint (e.g. `dvd1-a3f92c...`) |

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

**Required fields:**

| Field | Type | Constraints |
|-------|------|-------------|
| `fingerprint` | string | Non-empty, unique |
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

---

### Verify an Existing Disc

```
POST /v1/disc/{fingerprint}/verify
Authorization: Bearer <token>
```

Promotes an unverified disc to verified status. Idempotent — verifying an already-verified disc returns success.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `fingerprint` | string | OVID fingerprint to verify |

**Response 200 — promoted to verified:**

```json
{
  "request_id": "550e8400-...",
  "fingerprint": "dvd1-a3f92c...",
  "status": "verified",
  "message": "Disc verified"
}
```

**Response 200 — already verified:**

```json
{
  "request_id": "550e8400-...",
  "fingerprint": "dvd1-a3f92c...",
  "status": "verified",
  "message": "Disc already verified"
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

## Request Tracing

Every response includes an `X-Request-ID` header containing a UUID v4. Include this in bug reports for server-side log correlation.

---

## OpenAPI / Swagger

When running locally, auto-generated interactive API documentation is available at:

- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
