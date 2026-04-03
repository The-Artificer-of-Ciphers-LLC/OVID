# ARM Integration Guide

Integrate [OVID](https://oviddb.org) into [ARM (Automatic Ripping Machine)](https://github.com/automatic-ripping-machine/automatic-ripping-machine) for accurate, disc-level metadata identification. OVID provides a fingerprint-based lookup that identifies the exact disc pressing — not just the movie title — giving ARM the correct title, edition, track layout, and region information in a single API call.

---

## What OVID Provides vs. TMDB / OMDb

| Capability | OVID | TMDB / OMDb |
|-----------|------|-------------|
| Identifies **exact disc pressing** | ✅ | ❌ |
| Distinguishes editions (Theatrical, Director's Cut, etc.) | ✅ | ❌ |
| Provides track layout (titles, chapters, audio streams) | ✅ | ❌ |
| Region and disc format metadata | ✅ | ❌ |
| Works offline with a local mirror | ✅ | ❌ |
| Movie title and year | ✅ | ✅ |
| Cast, crew, posters, plot summary | ❌ | ✅ |

**OVID and TMDB are complementary.** OVID identifies *which disc* is in the drive and provides ripping-relevant metadata (track layout, edition, region). TMDB provides *movie-level* metadata (cast, plot, artwork). ARM can query OVID first for disc identification, then enrich with TMDB data for media server libraries.

---

## Configuration

Add the following environment variables to your ARM configuration (typically `arm.yaml` or your environment file):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OVID_ENABLED` | Yes | `false` | Set to `true` to enable OVID lookups |
| `OVID_API_URL` | No | `https://api.oviddb.org` | OVID API endpoint for disc lookups |
| `OVID_MIRROR_URL` | No | *(none)* | If set, used instead of `OVID_API_URL` — for local mirror setups |

### Minimal configuration (public API)

```yaml
# arm.yaml
OVID_ENABLED: true
```

This uses the public OVID API at `https://api.oviddb.org`. No API key is required — disc lookups are free and unauthenticated.

### Local mirror configuration

```yaml
# arm.yaml
OVID_ENABLED: true
OVID_API_URL: http://192.168.1.50:8000
```

Replace `192.168.1.50` with the IP address of your OVID mirror server. See the [Self-Hosting Guide](self-hosting.md) to set up a local mirror.

---

## Integration Code Sample

ARM's `identify.py` module can be extended with an OVID provider. The following code shows how OVID fits into ARM's metadata lookup chain:

```python
# In ARM's metadata lookup chain (identify.py):
def identify_disc(drive_path, settings):
    # 1. Try OVID first (disc-level fingerprint)
    if settings.get("OVID_ENABLED"):
        from ovid import Disc, OVIDClient

        # Use mirror URL if configured, otherwise the public API
        base_url = settings.get(
            "OVID_MIRROR_URL",
            settings.get("OVID_API_URL", "https://api.oviddb.org"),
        )

        disc = Disc.from_path(drive_path)
        client = OVIDClient(base_url=base_url)
        result = client.lookup(disc.fingerprint)

        if result and result.confidence in ("high", "medium"):
            return build_arm_job_from_ovid(result)

    # 2. Fall back to existing TMDB/OMDb lookup
    return identify_via_tmdb(drive_path, settings)
```

### How it works

1. **Fingerprint the disc** — `Disc.from_path()` reads the disc structure (IFO files for DVD, AACS certificate hash for Blu-ray) and computes a unique fingerprint.
2. **Look up the fingerprint** — `OVIDClient.lookup()` sends a `GET /v1/disc/{fingerprint}` request to the OVID API (public or local mirror).
3. **Check confidence** — OVID returns a confidence level based on how many independent contributors have verified the disc. High/medium confidence means at least one verification.
4. **Build the ARM job** — If OVID returns a match, use the disc metadata (title, edition, tracks) to build the ARM ripping job.
5. **Fall back** — If OVID doesn't have the disc or confidence is low, ARM falls back to its existing TMDB/OMDb lookup chain.

### Installing ovid-client

The `ovid` Python library provides `Disc` and `OVIDClient`:

```bash
pip install ovid-client
```

Or install from source:

```bash
git clone https://github.com/The-Artificer-of-Ciphers-LLC/OVID.git
cd OVID/ovid-client
pip install -e .
```

**System dependencies:** `ovid-client` uses `libdvdread` (for DVD fingerprinting) and optionally `libaacs` (for Blu-ray). These are typically already installed on ARM setups since they're required for ripping.

---

## Fallback Behavior

OVID is designed to be non-blocking — if it's unavailable, ARM continues normally:

| Scenario | Behavior |
|----------|----------|
| OVID API unreachable | `OVIDClient.lookup()` times out (default: 5 seconds) and returns `None`. ARM falls back to TMDB/OMDb. |
| Disc not in OVID database | API returns `404`. ARM falls back to TMDB/OMDb. |
| Low confidence match | ARM ignores the result and falls back to TMDB/OMDb. |
| OVID returns a match | ARM uses OVID metadata. No TMDB/OMDb call needed for disc identification. |
| Network is completely offline | With a [local mirror](self-hosting.md), lookups still work. Without a mirror, falls back to TMDB/OMDb (which also requires internet). |

**Key design principle:** OVID failure should never block a rip. The lookup is always a best-effort enhancement to ARM's existing identification pipeline.

---

## Using a Local Mirror for Offline Ripping

For fully offline disc identification — no internet required during ripping:

1. **Set up an OVID mirror** on your local network. See the [Self-Hosting Guide](self-hosting.md) for step-by-step instructions.
2. **Point ARM at the mirror** by setting `OVID_API_URL` to your mirror's address.
3. **Rip without internet** — ARM queries your local mirror for disc metadata. The mirror syncs from the canonical server when internet is available, but lookups are entirely local.

This is the recommended setup for dedicated ripping stations or air-gapped environments.

```
┌───────────────┐     ┌──────────────┐     ┌───────────────────┐
│   ARM Server  │────▶│  OVID Mirror │────▶│  PostgreSQL (local)│
│  (ripping PC) │     │  (port 8000) │     │                   │
└───────────────┘     └──────┬───────┘     └───────────────────┘
                             │ (periodic sync when online)
                             ▼
                      ┌──────────────┐
                      │ api.oviddb.org│
                      │  (canonical) │
                      └──────────────┘
```

---

## Contributing Disc Data Back

When ARM rips a disc that isn't in the OVID database, you can submit it to help the community:

```bash
# Interactive submission wizard
ovid submit /path/to/VIDEO_TS --api-url https://api.oviddb.org --token YOUR_JWT
```

The wizard walks you through: fingerprint → search TMDB for the title → pick the release → confirm edition and disc number → submit.

New submissions require verification by a second contributor before they're considered confirmed. See the [Contributing Guide](contributing.md) for details.

---

## API Endpoints Used by ARM

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/v1/disc/{fingerprint}` | No | Look up disc metadata by fingerprint |
| `GET` | `/v1/search?q=` | No | Search releases by title (used by submit wizard) |
| `GET` | `/health` | No | Check if the OVID API is reachable |

Full API documentation: [API Reference](api-reference.md)

---

## Next Steps

- [Self-Hosting Guide](self-hosting.md) — set up a local OVID mirror
- [CLI Reference](cli-reference.md) — `ovid` command-line tool usage
- [Fingerprint Spec](fingerprint-spec.md) — how OVID-DVD-1 fingerprints work
- [Contributing](contributing.md) — submit disc data to the community database
