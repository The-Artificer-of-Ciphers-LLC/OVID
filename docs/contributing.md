# Contributing to OVID

Thank you for your interest in contributing to OVID! This project is community-driven — every disc submission and code contribution makes the database more useful for everyone.

---

## Ways to Contribute

### 1. Submit disc metadata

The most impactful contribution is submitting disc fingerprints and metadata. Every disc you submit helps ARM users everywhere identify their discs automatically.

```bash
# Fingerprint a DVD or Blu-ray
ovid fingerprint /path/to/VIDEO_TS

# Submit with the interactive wizard
ovid submit /path/to/VIDEO_TS --api-url https://api.oviddb.org --token YOUR_JWT
```

The submit wizard walks through:

1. **Fingerprint** — reads the disc structure and computes a unique identifier
2. **Search** — searches TMDB for the movie title
3. **Pick release** — select the matching release (edition, region, format)
4. **Confirm** — review metadata and submit

New submissions start as **unverified**. When a second contributor submits the same disc fingerprint with matching metadata, the entry is promoted to **verified** status. This two-contributor model ensures data quality without requiring moderation.

### 2. Verify existing discs

If you have a disc that's already in the OVID database, you can verify it:

```bash
ovid verify /path/to/VIDEO_TS --api-url https://api.oviddb.org --token YOUR_JWT
```

Verifications are just as valuable as new submissions — they increase confidence in existing data.

### 3. Contribute code

See [Code Contributions](#code-contributions) below.

### 4. Report issues

Found a bug or have a feature request? [Open an issue on GitHub](https://github.com/The-Artificer-of-Ciphers-LLC/OVID/issues).

---

## Getting an API Token

To submit or verify discs, you need a JWT token from the OVID API:

1. **Sign in** via one of the supported OAuth providers (GitHub, Google, Apple) at `https://oviddb.org`
2. **Copy your token** from your account settings
3. **Set it as an environment variable** for CLI use:

```bash
export OVID_TOKEN=your_jwt_token_here
```

Or pass it directly with `--token` on each command.

---

## Code Contributions

### Development environment setup

Follow the [Developer Guide](getting-started-dev.md) to set up your local environment. In summary:

```bash
# Clone the repository
git clone https://github.com/The-Artificer-of-Ciphers-LLC/OVID.git
cd OVID

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install ovid-client in development mode
cd ovid-client
pip install -e '.[dev]'
cd ..

# Install API dependencies
pip install -r api/requirements.txt
pip install pytest httpx

# Start the database
cp .env.example .env
docker compose up -d db

# Run migrations
cd api
DATABASE_URL=postgresql://ovid:ovidlocal@localhost:5432/ovid alembic upgrade head
cd ..
```

### Workflow: Fork → Branch → PR

1. **Fork** the repository on GitHub
2. **Clone** your fork locally
3. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
4. **Make your changes** with clear, focused commits
5. **Run all tests** (see below) — they must pass
6. **Push** your branch and open a Pull Request against `main`

### Coding standards

- **Python 3.9+** — use type hints where practical
- **PEP 8** — follow standard Python style conventions
- **Meaningful names** — clear variable, function, and module names over comments
- **Docstrings** — public functions and classes should have docstrings
- **Keep it simple** — prefer straightforward solutions over clever ones

### Test requirements

All tests must pass before your PR can be merged:

```bash
# ovid-client tests
cd ovid-client && python -m pytest tests/ -v && cd ..

# API tests
cd api && python -m pytest tests/ -v && cd ..

# E2E pipeline tests
PYTHONPATH=api python -m pytest tests/ -v
```

API tests use an in-memory SQLite database — no Docker or PostgreSQL required for running them. Write tests for new features and bug fixes. If you're modifying existing behavior, update the relevant tests.

### Repository structure

```
OVID/
├── api/                    ← FastAPI server
│   ├── app/                ← Application code (models, routes, auth, schemas)
│   ├── alembic/            ← Database migrations
│   ├── scripts/            ← Seed & utility scripts
│   └── tests/              ← API test suite
├── ovid-client/            ← Python fingerprinting library + CLI
│   ├── src/ovid/           ← Library source
│   └── tests/              ← Client test suite
├── tests/                  ← Cross-package E2E tests
├── docs/                   ← Documentation (you are here)
├── scripts/                ← Top-level utility scripts
├── docker-compose.yml      ← Local development stack
└── .env.example            ← Environment variable template
```

---

## Data License

All disc metadata in the OVID database is released under the [Creative Commons CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/) public domain dedication.

**By submitting disc data to OVID, you agree that your contributions are released into the public domain under CC0 1.0.** This means:

- Anyone can use, modify, and redistribute the data for any purpose
- No attribution is required (though it's appreciated)
- The data is free for commercial and non-commercial use
- The CC0 dedication is irrevocable

We chose CC0 because OVID exists to serve the community. Disc metadata — fingerprints, titles, track layouts, region codes — are factual data that should be freely available to everyone. No one should have to pay or ask permission to know what's on a disc they own.

### Exporting the database

The full database can be exported as NDJSON at any time:

```bash
python scripts/dump_cc0.py --output ovid-dump.ndjson.gz
```

Or via the API:

```bash
curl https://api.oviddb.org/v1/sync/snapshot
```

---

## Code of Conduct

Be respectful and constructive. We're all here because we care about preserving physical media metadata. Treat fellow contributors with kindness.

---

## Questions?

- [Open a discussion on GitHub](https://github.com/The-Artificer-of-Ciphers-LLC/OVID/discussions)
- Check existing [documentation](getting-started-dev.md) and [API reference](api-reference.md)

---

## Next Steps

- [Developer Guide](getting-started-dev.md) — detailed development environment setup
- [Self-Hosting Guide](self-hosting.md) — run your own OVID mirror
- [ARM Integration](arm-integration.md) — integrate OVID with ARM
- [API Reference](api-reference.md) — full endpoint documentation
