---
phase: 03-chapter-name-data
plan: 01
status: complete
started: 2026-04-04
completed: 2026-04-04
---

## Summary

Added chapter metadata support to the OVID API layer: database table, ORM model, Pydantic schemas, Alembic migration, disc submit/lookup route extensions, and sync feed chapter support.

## What Was Built

- **DiscChapter ORM model** with `chapter_index` (1-based), `name` (optional, max 200 chars), `start_time_secs` (optional) — linked to DiscTitle via FK with CASCADE delete
- **Alembic migration 900000000005** creating `disc_chapters` table with unique constraint on (disc_title_id, chapter_index)
- **ChapterCreate/ChapterResponse/SyncChapterRecord** Pydantic schemas with validation (ge=1 index, max_length=200 name)
- **Submit route** extended to accept chapters nested in titles, with DoS protection (max 999 per title) and duplicate index rejection
- **Lookup route** extended with eager loading of chapters via joinedload
- **Sync feed** extended with `build_sync_chapter` helper and chapter data in title records

## Key Files

### Created
- `api/alembic/versions/900000000005_add_disc_chapters.py`
- `api/tests/test_chapter_schemas.py`

### Modified
- `api/app/models.py` — DiscChapter class, DiscTitle.chapters relationship
- `api/app/schemas.py` — ChapterCreate, ChapterResponse, SyncChapterRecord; TitleCreate/TitleResponse/SyncTitleRecord extended
- `api/app/routes/disc.py` — chapter creation in submit, eager loading in lookup, ChapterResponse building
- `api/app/sync.py` — build_sync_chapter, chapter data in build_sync_title
- `api/app/routes/sync.py` — import update
- `api/tests/test_disc_submit.py` — chapter submit tests
- `api/tests/test_disc_lookup.py` — chapter lookup test
- `api/tests/test_sync.py` — chapter sync test

## Commits
- `4a47913` feat(03-01): add DiscChapter model, schemas, and migration
- `8b764f0` feat(03-01): chapter integration in submit, lookup, and sync feed

## Self-Check: PASSED
- All API tests pass
- DiscChapter model imports correctly
- Schemas validate as specified
- Migration creates disc_chapters table
- Backward compatibility maintained (empty chapters default)
