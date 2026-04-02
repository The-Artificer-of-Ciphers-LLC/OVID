# ovid-client CLI Reference

The `ovid` command-line tool fingerprints DVD discs, looks up disc metadata, and submits new entries to the OVID database.

**Version:** 0.1.0
**Install:** `pip install -e '.[dev]'` (from `ovid-client/` directory)

---

## Commands

### `ovid fingerprint`

Generate a fingerprint from a DVD source.

```bash
ovid fingerprint <path>
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `path` | Path to a VIDEO_TS directory, ISO image file, or mounted drive |

**Output:** Prints the fingerprint string to stdout.

**Examples:**

```bash
# From a VIDEO_TS folder
$ ovid fingerprint /mnt/dvd/VIDEO_TS
dvd1-59863dd2519845852f991036aabe2a725fc5d751

# From an ISO image
$ ovid fingerprint ~/movies/the-matrix.iso
dvd1-a3f92c1b4e8d7f6a2c9e0b1d3f5a8c2e4f6b8d0a

# From a parent directory containing VIDEO_TS
$ ovid fingerprint /mnt/dvd
dvd1-59863dd2519845852f991036aabe2a725fc5d751
```

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (path not found, no VIDEO_TS, invalid IFO, etc.) |

---

### `ovid lookup`

Look up a disc fingerprint in the OVID database and display metadata.

```bash
ovid lookup <fingerprint> [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `fingerprint` | An OVID fingerprint string (e.g. `dvd1-a3f92c...`) |

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--api-url` | `http://localhost:8000` | OVID API base URL |
| `--token` | (none) | JWT auth token (also reads `OVID_TOKEN` env var) |

**Output:** Rich-formatted table showing release title, year, edition, confidence, and disc structure (titles with duration, chapters, audio/subtitle tracks).

**Examples:**

```bash
# Look up against local API
$ ovid lookup dvd1-a3f92c1b4e8d7f6a2c9e0b1d3f5a8c2e4f6b8d0a

# Against a remote server
$ ovid lookup dvd1-a3f92c... --api-url https://api.oviddb.org
```

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | Disc found — metadata displayed |
| 1 | Disc not found (404) or API error |

---

### `ovid submit`

Submit a new disc entry via an interactive wizard.

```bash
ovid submit <path> [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `path` | Path to a VIDEO_TS directory, ISO image, or mounted drive |

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--api-url` | `http://localhost:8000` | OVID API base URL |
| `--token` | (none) | JWT auth token (required; also reads `OVID_TOKEN`) |

**Wizard flow:**

1. **Fingerprint** — reads the disc and computes the fingerprint
2. **TMDB search** — prompts for a title search query, displays matching results from TMDB (requires `TMDB_API_KEY` env var; falls back to manual entry if absent)
3. **Pick release** — select the correct movie/TV release from results
4. **Edition** — enter edition name (e.g. "Director's Cut", "Special Edition")
5. **Disc number** — enter disc number and total disc count (for multi-disc sets)
6. **Submit** — sends the disc data to the API

**Examples:**

```bash
# Submit with token flag
$ ovid submit /mnt/dvd --api-url http://localhost:8000 --token eyJhbG...

# Submit using env vars
$ export OVID_TOKEN=eyJhbG...
$ export TMDB_API_KEY=abc123...
$ ovid submit /mnt/dvd
```

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | Disc submitted successfully |
| 1 | Error (auth failure, duplicate fingerprint, API error, etc.) |

---

## Environment Variables

The CLI reads these environment variables as defaults:

| Variable | Used by | Description |
|----------|---------|-------------|
| `OVID_API_URL` | `lookup`, `submit` | API base URL (default: `http://localhost:8000`) |
| `OVID_TOKEN` | `lookup`, `submit` | JWT authentication token |
| `TMDB_API_KEY` | `submit` | TMDB API key for movie search |

Command-line flags override environment variables when both are set.

---

## Python API

The `ovid` package can also be used as a library:

```python
from ovid import Disc, OVIDClient

# Fingerprint a disc
disc = Disc.from_path("/path/to/VIDEO_TS")
print(disc.fingerprint)      # "dvd1-a3f92c..."
print(disc.canonical_string)  # "OVID-DVD-1|3|8|..."
print(disc.vts_info)          # list of VtsInfo objects

# Look up in the database
client = OVIDClient(base_url="http://localhost:8000")
result = client.lookup(disc.fingerprint)

# Submit (requires auth)
client = OVIDClient(base_url="http://localhost:8000", token="eyJhbG...")
client.submit({
    "fingerprint": disc.fingerprint,
    "format": "DVD",
    "release": {"title": "The Matrix", "year": 1999, "content_type": "movie"},
    "titles": [...]
})
```

See [API Reference](api-reference.md) for the full request/response schema.
