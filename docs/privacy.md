# Privacy Policy

OVID is a community-driven, CC0-licensed metadata database. Our goal is to
collect the minimum data needed to run the service and keep the disc-metadata
dataset trustworthy — not to profile contributors. This page discloses every
category of personal data OVID stores and why.

---

## Data Categories

### Account data

When you sign in via GitHub, Google, Apple, Mastodon, or IndieAuth, OVID
stores your provider user ID, display name/handle, and (where applicable) an
encrypted-at-rest OAuth refresh token, so you can be recognized as the
submitter/confirmer of a disc entry. No password is ever stored — all sign-in
is delegated to the OAuth/IndieAuth provider.

### Disc metadata (CC0, not personal data)

Fingerprints, titles, chapters, track layouts, and region codes are factual
data about physical discs, not personal data. All disc metadata is released
under [CC0 1.0](contributing.md#data-license).

### Edit history

Every create, update, confirm ("verify"), and dispute action is logged in an
audit table (`disc_edits`) tied to the acting user's account, so data quality
issues can be traced and reverted if needed.

### IP-hash confirmation signal (new data category)

As of the two-contributor verification workflow, OVID stores **one additional
category of data it has never stored before**: a pseudonymized signal derived
from the IP address of a user confirming an existing disc entry.

- **What is stored:** a **salted HMAC-SHA256 hash** of the client IP address,
  **truncated to the /24 subnet before hashing** for IPv4 addresses (or the
  /48 subnet for IPv6 addresses). The full, raw IP address is **never stored
  or logged anywhere** — only the salted hash of the truncated subnet.
- **Why:** this hash is used purely as a soft, offsetting **anti-Sybil
  independence signal** on disc *confirmation* (a second contributor
  re-submitting a disc that already exists) — it helps distinguish a genuinely
  distinct confirmer from the same actor confirming their own submission from
  a fresh throwaway account. It is never used to identify, geolocate, or track
  an individual, and by itself it never blocks a confirmation — see
  [Anti-Sybil confirmation gate](#anti-sybil-confirmation-gate) below.
- **Retention:** OVID's *target* retention window for the IP-hash is
  approximately **90 days**, for fraud-prevention purposes only — it is not
  intended to be kept indefinitely. **As of this writing, that window is not
  enforced automatically: there is no scheduled job or process anywhere in
  OVID that deletes `disc_edits.ip_hash` values once they age past 90
  days.** Enforcing the window today is a manual/operator responsibility
  (a self-hosted instance operator would need to periodically purge old
  hashes themselves); automating this purge is a planned future capability,
  not a currently-shipped one. Do not assume IP-hashes are automatically
  purged after 90 days on any OVID instance today.
- **Legal basis (GDPR):** even a salted, truncated hash of an IP address is
  treated as personal data under GDPR (it can, in principle, be linked back to
  an individual with additional information). OVID's basis for processing this
  category is **fraud prevention / legitimate interest** — protecting the
  integrity of the two-contributor confirmation model — and the
  truncation + salting + short retention window together form the
  pseudonymization floor required for that basis to hold.
- **Configuration:** the salt used to compute this hash is configured via the
  `OVID_IP_HASH_SALT` environment variable (see `.env.example`). It is
  **optional**: if unset, the IP-diversity signal is simply absent for that
  deployment (fail-open) — confirmations are not blocked or degraded in any
  other way, and the server does not refuse to start.

### Anti-Sybil confirmation gate

Disc confirmation (a second, distinct contributor re-submitting a disc
already in the database) passes through a lightweight anti-Sybil gate before
being accepted:

1. A **per-account cooldown floor**, enforced in Postgres, capping how many
   confirmations one account can perform in a rolling window.
2. The **IP-hash signal** described above (fail-open when absent).
3. A **weighted, offsetting trust score** combining account age and IP
   diversity. Any single absent signal counts for nothing against the
   confirmer — the gate is deliberately fail-open, because falsely rejecting a
   genuine early contributor is treated as a worse outcome than a rare missed
   Sybil attempt at this stage of the project.

### Confirmation cooldown vs. general API rate limiting

These are **two distinct mechanisms** and are not redundant:

- The **confirmation cooldown** above is a permanent, Postgres-backed,
  per-account cap that is part of the anti-Sybil trust model. It exists
  specifically to protect the two-contributor confirmation guarantee and does
  not change based on deployment topology.
- The **general API rate limiter** (`slowapi`) throttles overall API abuse
  across all endpoints and is backed by Redis in multi-worker production
  deployments (a Phase 3 hardening item). It is unrelated to the confirmation
  trust model above and one is never a substitute for the other.

---

## Data We Do Not Collect

- No raw IP addresses are ever stored or logged.
- No passwords (authentication is delegated to OAuth/IndieAuth providers).
- No DRM decryption keys, and no video content or disc images are ever
  transmitted or stored — see [Data License](contributing.md#data-license)
  and the project's legal constraints.
- No tracking cookies, analytics beacons, or third-party ad/tracking scripts
  on the web frontend.

## Your Rights

Because account data is tied to your OAuth identity, you can request account
deletion (which removes your account record and OAuth links) by opening an
issue or discussion on [GitHub](https://github.com/The-Artificer-of-Ciphers-LLC/OVID).
Disc metadata you contributed remains in the CC0 public-domain dataset (per
the [Data License](contributing.md#data-license) you agreed to on submission)
even if your account is later deleted, since it is factual data about a
physical disc, not personal data about you.

## Questions

Open a [discussion on GitHub](https://github.com/The-Artificer-of-Ciphers-LLC/OVID/discussions)
for any privacy question not answered here.
