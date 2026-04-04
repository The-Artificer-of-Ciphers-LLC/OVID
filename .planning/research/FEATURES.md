# Feature Landscape

**Domain:** Community-driven physical disc metadata database (DVD/Blu-ray/UHD identification)
**Researched:** 2026-04-04
**Comparable systems studied:** MusicBrainz, Discogs, OpenLibrary, FreeDB/GnuDB

## Table Stakes

Features users expect from a community metadata database. Missing any of these and OVID feels broken or untrustworthy to its target audience (ARM users, data hoarders, media archivists).

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Multi-disc set grouping** | Box sets and multi-disc editions are ~20-30% of Blu-ray releases. MusicBrainz models multi-disc as multiple "mediums" within a single "release," grouped under a "release group." Users will immediately hit this with LOTR, MCU collections, TV series box sets. Without it, each disc is an orphan. | Medium | OVID already has a `DiscSet` table. Need: set CRUD endpoints, disc-to-set linking, sibling disc display. MusicBrainz's approach of ordered mediums within a release is the proven model. |
| **Disc position within set** | Users need to know "Disc 2 of 4" to select the right rip profile. MusicBrainz stores medium position as an integer within a release. | Low | Add `disc_number` and `total_discs` fields to the disc-set membership relation. |
| **Edit history / audit trail** | MusicBrainz records every edit as a first-class entity with before/after values, editor attribution, and timestamp. Discogs tracks all changes with full diffs. Without visible edit history, contributors don't trust the data and can't debug bad edits. This is table stakes for any wiki-style database. | Medium | OVID already has a `DiscEdit` table. Need: expose edit history via API and web UI, store structured diffs (not just "something changed"), show who changed what and when. |
| **Contributor attribution** | Every edit must credit the editor. MusicBrainz shows editor username on every edit. Discogs shows contributor on every submission. Contributors won't contribute if they get no credit. | Low | Already have user model. Ensure every edit/submission links to user and is visible in UI. |
| **Database dumps (CC0)** | MusicBrainz publishes full PostgreSQL dumps weekly. OpenLibrary publishes monthly TSV/JSON dumps. This is the social contract of CC0 open data: if the data is public domain, it must be actually downloadable in bulk. Without dumps, "open data" is marketing. | Medium | Monthly dumps planned. Use pg_dump for PostgreSQL native format plus a JSON export for portability. Host at snapshots.oviddb.org. |
| **Sync feed for mirrors** | MusicBrainz provides replication packets (change logs) that mirrors consume to stay current without re-downloading the full dump. OVID already has `/v1/sync/head`, `/v1/sync/diff`, `/v1/sync/snapshot`. This is table stakes for any self-hostable database. | Low (already built) | Harden existing sync: error recovery, partial resume, integrity checksums on packets. |
| **Self-hosting documentation** | MusicBrainz has a full Docker-based mirror setup guide. OpenLibrary is actively working on self-hosted import scripts (issues #10583, #10598). Users expect `docker compose up` to produce a working mirror. | Medium | Document the mirror profile, sync setup, and snapshot import. One-command setup script. |
| **Basic dispute mechanism** | When two contributors disagree on metadata (e.g., "is this the theatrical or director's cut?"), there must be a way to flag and resolve it. MusicBrainz uses edit voting. Discogs uses moderator review. At minimum: flag a disc as "disputed" and surface it for resolution. | Medium | OVID has disc status states including "disputed." Need: dispute creation endpoint, dispute queue for moderators, resolution workflow with audit trail. |
| **Email+password auth** | OAuth-only excludes users who don't have GitHub/Google accounts or don't want to link them. MusicBrainz uses email+password as primary auth. For a community database targeting technical users, OAuth is great as an option but shouldn't be the only path. | Medium | Planned as P1. Include: registration, email verification, password reset via email link. Use bcrypt/argon2 for hashing. |
| **CLI scanner tool** | ARM integration is the primary adoption channel. A standalone `ovid scan` command that fingerprints, looks up, and auto-submits is how most data will enter the system. MusicBrainz Picard (desktop app) is the primary submission vector for disc IDs. | High | Three modes: auto (minimal prompts), wizard (guided TMDB match), batch (folder of ISOs). Cross-platform binary distribution. |
| **UPC/barcode lookup** | Users expect to look up a disc by scanning or typing its barcode. MusicBrainz and Discogs both support barcode search. Already shipped in v0.2.0. | Low (already built) | Maintain and document. |

## Differentiators

Features that set OVID apart. Not expected by users on day one, but create competitive advantage and community loyalty.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Structural fingerprinting (already shipped)** | No other public database identifies discs by IFO/BDMV structure. dvdid uses timestamps (breaks on ISOs/copies). MusicBrainz disc IDs are audio-CD-only. OVID's two-tier BD fingerprint (AACS preferred, BDMV fallback) is novel. This is the core differentiator. | N/A (shipped) | Protect this: algorithm changes require version bumps, never modify existing output. |
| **Chapter name data** | No public database stores per-chapter names for DVD/Blu-ray titles. Kodi and Plex users want chapter names for navigation. MusicBrainz stores track names but not CD chapter points. This is unique metadata OVID can own. | Medium | New `disc_chapters` table. Community-contributed, optional. Low barrier to add during submission. High value for media players. |
| **Two-contributor verification** | MusicBrainz requires voting (3 unanimous votes or 7-day timeout). Discogs has moderators review. OVID's simpler model -- a second independent contributor confirms a disc entry -- is faster and more appropriate for a small community. Lowers friction while maintaining data quality. | Low (already built) | Shipped in v0.2.0. The simplicity IS the differentiator vs MusicBrainz's heavyweight voting. |
| **ARM-native integration** | No other disc database has first-party integration with Automatic Ripping Machine. ARM auto-submit on miss is already shipped. This makes OVID the default disc database for the largest open-source ripping tool. | Low (already built) | The CLI scanner extends this: ARM users who want to contribute actively use `ovid scan --wizard`. |
| **Federated login (Mastodon/IndieAuth)** | MusicBrainz uses its own auth. Discogs uses its own auth. OpenLibrary uses Internet Archive accounts. OVID supporting Mastodon and IndieAuth login appeals to the FOSS/self-hosting community, which is exactly the target audience. | N/A (shipped) | Already shipped. Unique among comparable databases. |
| **Per-title track metadata** | OVID stores audio tracks, subtitle tracks, duration, and chapter count per title on a disc. MusicBrainz stores per-track data for audio CDs but nothing equivalent exists for video discs. This is structural data that ripping tools need. | N/A (shipped) | Already shipped. Extend with chapter names in 0.3.0. |
| **Monthly CC0 dumps with JSON export** | MusicBrainz dumps are PostgreSQL-native only (requires PG to import). OVID should offer both pg_dump format AND a portable JSON/JSONL format. This lowers the barrier for downstream tools that want disc data without running PostgreSQL. | Low | JSON export is trivial to generate alongside pg_dump. Publish both at snapshots.oviddb.org. |

## Anti-Features

Features to explicitly NOT build for 0.3.0. Each has a clear rationale.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **MusicBrainz-style edit voting** | MusicBrainz's voting system (3 unanimous votes, 7-day open period, auto-editor privileges) is designed for millions of editors. OVID will have <100 active contributors at beta. A voting system with nobody voting creates the illusion of quality control while actually being a friction barrier. | Use two-contributor verification for new entries. Use moderator review (admin/trusted user) for disputed entries. Defer community voting to v0.4.0 when there are enough contributors to make it meaningful. |
| **Gamification / reputation system** | Discogs has a Contributor Improvement Program with submission limits based on vote quality. MusicBrainz has editor statistics and privileges. At OVID's scale, gamification adds complexity without benefit and can incentivize quantity over quality. | Track contribution counts for attribution (visible on profile). No badges, levels, or submission limits. Revisit when contributor count exceeds 200. |
| **TV series episode-to-title mapping** | Extremely complex: a single BD may have 20+ titles for episodes, extras, and menus. Mapping "Title 3 = S02E05" requires manual editor knowledge and a much richer data model. | Defer to v0.4.0. For now, store titles with durations and chapter counts. Users can infer episodes from duration patterns. |
| **Movie metadata (plot, cast, ratings)** | TMDB, OMDb, and TheMovieDB already do this well. Duplicating their data is wasted effort and creates a maintenance burden. OVID identifies discs; it doesn't catalog movies. | Link to TMDB ID as a foreign key. Let downstream tools (ARM, Plex, Kodi) fetch movie metadata from TMDB using the ID OVID provides. |
| **Visual UI polish** | The target audience is ARM users and data hoarders, not casual consumers. Functional completeness matters more than visual design at this stage. | Ship functional UI for all features. Apply polish in a later milestone. |
| **Federated node mode (local writes + upstream)** | Allowing mirrors to accept writes and push upstream requires conflict resolution, merge logic, and distributed consensus. Massive complexity for a feature nobody needs yet. | Mirrors are read-only replicas via sync feed. Contributors submit to the central API. Defer federation to v0.4.0+. |
| **Mobile barcode scanning app** | Building a native mobile app is a large effort. The web UI can do barcode lookup via text input. | Defer entirely. If needed, a PWA with camera access could be a lighter approach later. |
| **DRM/decryption key storage** | Legal liability. Explicitly out of scope. | Store only structural metadata (fingerprints, layout, track info). Never store keys, encryption status, or circumvention data. |

## Feature Dependencies

```
Email+Password Auth ─── (independent, no deps)

Multi-Disc Set Support
  ├── Set CRUD API ──→ Web UI set management
  ├── Disc-to-set linking ──→ CLI wizard set prompts
  └── Sibling disc display ──→ API response enrichment

Chapter Name Data
  ├── disc_chapters table (migration) ──→ API schema update
  ├── API create/read chapter data ──→ Web UI chapter display
  └── CLI wizard chapter step ──→ (requires API)

Edit History / Moderation
  ├── Structured diff storage ──→ Edit history API
  ├── Edit history API ──→ Web UI edit history view
  ├── Dispute creation ──→ Dispute queue (moderator view)
  └── Resolution workflow ──→ Audit trail

Self-Hosted Node Hardening
  ├── Snapshot generation ──→ snapshots.oviddb.org hosting
  ├── Sync protocol hardening ──→ Mirror setup documentation
  └── One-command installer ──→ Self-hosting guide

CLI Scanner Tool
  ├── ovid scan (auto) ──→ ARM workflow parity
  ├── ovid scan --wizard ──→ TMDB integration, set/chapter prompts
  └── ovid scan --batch ──→ ISO scanning (requires fingerprint lib)

Documentation Suite
  ├── Self-hosting guide ──→ (requires hardened sync + snapshots)
  ├── Sync spec ──→ (requires hardened sync protocol)
  ├── Moderation guide ──→ (requires dispute resolution workflow)
  ├── Governance model ──→ (independent)
  └── Data license FAQ ──→ (independent)
```

## MVP Recommendation

For 0.3.0 beta launch, prioritize in this order:

**Must ship (blocks beta credibility):**

1. **P0 bug fixes and security hardening** -- 11 known issues. Ship none of the features below until these are resolved. A community database with JWT-in-URL and broken rate limiting will lose trust on day one.
2. **Multi-disc set support** -- Box sets are too common to ignore. Without this, the first user who rips a LOTR extended edition hits a dead end. MusicBrainz considers multi-disc a core data model primitive, not an add-on.
3. **Chapter name data** -- This is OVID's unique value proposition beyond fingerprinting. No other database has this. Ship it with the submission form so early contributors populate it from day one.
4. **CLI scanner tool** -- This is how the database gets seeded. The founder needs `ovid scan --batch` to reach 500 entries. ARM users need `ovid scan` to contribute. Without the CLI, the database stays empty and the API is useless.
5. **Edit history (visible)** -- Contributors need to see what changed and who changed it. Without this, the first edit war (and it will happen) has no resolution path.
6. **Database dumps** -- The CC0 social contract. Publish monthly dumps before announcement so the community can verify the data is real and downloadable.

**Ship for launch but can be minimal:**

7. **Self-hosting documentation + hardened sync** -- One working Docker mirror guide. Doesn't need to be perfect, but must work end-to-end.
8. **Dispute resolution (basic)** -- Flag as disputed, moderator resolves, audit trail. No voting system.
9. **Documentation suite** -- Governance, moderation guide, sync spec, data license FAQ. These documents build community trust for the public announcement.

**Defer past beta:**

10. **Email+password auth (P1)** -- OAuth covers the target audience (ARM users have GitHub). Ship post-beta.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Multi-disc set patterns | HIGH | MusicBrainz's release/medium/release-group model is well-documented and proven at scale. Direct applicability to OVID's disc/set model. |
| Moderation patterns | MEDIUM | MusicBrainz voting and Discogs moderator review are well-understood, but OVID's scale is orders of magnitude smaller. The recommendation to skip voting and use simple verification is an informed bet, not a proven pattern. |
| Self-hosting/mirror patterns | HIGH | MusicBrainz Docker mirror is mature, open source, well-documented. Replication via change packets is proven. OVID's sync feed follows the same model. |
| Chapter name data | LOW | No comparable system stores video disc chapter names. This is genuinely novel. The data model is straightforward but community contribution patterns are unproven. |
| Documentation patterns | MEDIUM | MusicBrainz has extensive style guides, governance docs, and contributor guides. OpenLibrary has less. The recommendation to ship governance + moderation guide + data license FAQ is based on MusicBrainz's example but adapted for OVID's smaller scale. |

## Sources

- MusicBrainz Release Group documentation: https://musicbrainz.org/doc/Release_Group
- MusicBrainz Release (multi-disc as mediums): https://musicbrainz.org/doc/Release
- MusicBrainz Edit system: https://musicbrainz.org/doc/Edit
- MusicBrainz Introduction to Voting: https://musicbrainz.org/doc/Introduction_to_Voting
- MusicBrainz Database Download / Replication: https://musicbrainz.org/doc/MusicBrainz_Database/Download
- MusicBrainz Docker mirror: https://github.com/metabrainz/musicbrainz-docker
- MusicBrainz Replication Mechanics: https://musicbrainz.org/doc/Replication_Mechanics
- MusicBrainz Style Guidelines: https://musicbrainz.org/doc/Style
- Discogs Submission Guidelines evolution: https://blog.discogs.com/en/database-submission-guidelines/
- Discogs Contributor Improvement Program: https://support.discogs.com/hc/en-us/articles/360005007014
- OpenLibrary Data Dumps: https://openlibrary.org/developers/dumps
- OpenLibrary self-hosted import discussion: https://github.com/internetarchive/openlibrary/issues/10583
- FreeDB/GnuDB (cautionary tale of community data privatization): https://en.wikipedia.org/wiki/Freedb
