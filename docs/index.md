# OVID — Open Video Disc Database

OVID is an open, community-driven database of optical disc fingerprints.
It lets media software identify Blu-ray and DVD discs by their structure,
retrieve accurate metadata, and integrate with media managers like
[ARM (Automatic Ripping Machine)](arm-integration.md).

All disc data is released under **CC0 (public domain)** — free to use,
mirror, and redistribute.

---

## Key Features

- **Disc Fingerprinting** — deterministic SHA-256 fingerprints computed from
  disc structure (playlist layout, stream attributes, title durations) so
  every copy of the same disc produces the same ID.
  [Read the spec →](fingerprint-spec.md)

- **REST API** — query discs by fingerprint, browse titles and tracks, submit
  new discs, and sync your local mirror.
  [API Reference →](api-reference.md)

- **Mirror Sync** — run your own OVID mirror for offline or low-latency
  lookups, with incremental sync via the `/v1/sync/changes` endpoint.
  [Self-Hosting Guide →](self-hosting.md)

- **CC0 Data Dumps** — full database snapshots published monthly as
  compressed NDJSON, ready for bulk import or offline use.

- **CLI Client** — `ovid-client` command-line tool for submitting and
  querying discs directly from your ripping pipeline.
  [CLI Reference →](cli-reference.md)

---

## Quick Start

The fastest way to get OVID running locally is with Docker Compose:

```bash
git clone https://github.com/The-Artificer-of-Ciphers-LLC/OVID.git
cd OVID
docker compose up -d
```

See the [Docker Quick Start](docker-quickstart.md) for the full walkthrough,
or the [Development Setup](getting-started-dev.md) if you want to run from
source.

---

## For Developers

| Resource | Description |
|----------|-------------|
| [API Reference](api-reference.md) | Full REST API documentation |
| [Fingerprint Spec](fingerprint-spec.md) | How disc fingerprints are computed |
| [Contributing](contributing.md) | How to submit discs and code |
| [Deployment](deployment.md) | Production deployment guide |
| [ARM Integration](arm-integration.md) | Using OVID with Automatic Ripping Machine |

---

## License

All disc metadata in OVID is released under
[CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/).
The OVID software is open source — see the repository for license details.
