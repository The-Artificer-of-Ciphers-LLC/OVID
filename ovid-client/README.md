# ovid-client

**OVID disc fingerprinting client** — generates stable, deterministic identifiers for DVD, Blu-ray, and 4K UHD discs.

Part of the [OVID (Open Video Disc Identification Database)](https://github.com/The-Artificer-of-Ciphers-LLC/OVID) project.

## Installation

```bash
pip install ovid-client
```

Requires Python 3.9+.

## CLI Quickstart

### Fingerprint a disc

```bash
# DVD (VIDEO_TS folder or ISO)
ovid fingerprint /path/to/VIDEO_TS

# Blu-ray / UHD (BDMV folder)
ovid fingerprint /path/to/BDMV

# JSON output
ovid fingerprint /path/to/VIDEO_TS --json
```

### Look up a disc in the OVID database

```bash
ovid lookup <fingerprint> --api-url https://holodeck.nomorestars.com
```

### Submit a disc

```bash
ovid submit /path/to/VIDEO_TS --api-url https://holodeck.nomorestars.com --token YOUR_JWT
```

The `submit` command runs an interactive wizard: fingerprint → TMDB search → pick release → edition/disc number → submit.

## Python API

```python
from ovid.disc import Disc

disc = Disc.from_path("/path/to/VIDEO_TS")
print(disc.fingerprint)   # e.g. "ovid-dvd1-a1b2c3d4..."
print(disc.disc_type)     # "dvd" or "bluray"
print(len(disc.titles))   # number of titles on the disc
```

```python
from ovid.client import OVIDClient

client = OVIDClient(base_url="https://holodeck.nomorestars.com")
result = client.lookup("ovid-dvd1-a1b2c3d4...")
```

## Supported Formats

| Format | Algorithm | Status |
|--------|-----------|--------|
| DVD    | OVID-DVD-1 (IFO structural hash) | ✅ Stable |
| Blu-ray | OVID-BD-1 (MPLS structural hash) | ✅ Stable |
| 4K UHD | OVID-BD-1 (same as Blu-ray) | ✅ Stable |

## License

AGPL-3.0-or-later. See [LICENSE](https://github.com/The-Artificer-of-Ciphers-LLC/OVID/blob/main/LICENSE) for details.

Disc metadata contributed to the OVID database is released under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).
