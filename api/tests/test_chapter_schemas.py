"""Tests for chapter Pydantic schemas — ChapterCreate, ChapterResponse, SyncChapterRecord."""

import pytest
from pydantic import ValidationError


class TestChapterCreate:
    """ChapterCreate validation rules per D-05."""

    def test_valid_full_chapter(self):
        from app.schemas import ChapterCreate
        ch = ChapterCreate(chapter_index=1, name="Opening", start_time_secs=0)
        assert ch.chapter_index == 1
        assert ch.name == "Opening"
        assert ch.start_time_secs == 0

    def test_chapter_index_zero_rejected(self):
        from app.schemas import ChapterCreate
        with pytest.raises(ValidationError):
            ChapterCreate(chapter_index=0)

    def test_chapter_index_negative_rejected(self):
        from app.schemas import ChapterCreate
        with pytest.raises(ValidationError):
            ChapterCreate(chapter_index=-1)

    def test_name_max_length_exceeded(self):
        from app.schemas import ChapterCreate
        with pytest.raises(ValidationError):
            ChapterCreate(chapter_index=1, name="x" * 201)

    def test_name_at_max_length(self):
        from app.schemas import ChapterCreate
        ch = ChapterCreate(chapter_index=1, name="x" * 200)
        assert len(ch.name) == 200

    def test_optional_fields_default_none(self):
        from app.schemas import ChapterCreate
        ch = ChapterCreate(chapter_index=1)
        assert ch.name is None
        assert ch.start_time_secs is None

    def test_start_time_secs_negative_rejected(self):
        from app.schemas import ChapterCreate
        with pytest.raises(ValidationError):
            ChapterCreate(chapter_index=1, start_time_secs=-1)


class TestChapterResponse:
    """ChapterResponse round-trip."""

    def test_round_trip(self):
        from app.schemas import ChapterResponse
        ch = ChapterResponse(chapter_index=1, name="Ch 1", start_time_secs=120)
        assert ch.chapter_index == 1
        assert ch.name == "Ch 1"
        assert ch.start_time_secs == 120

    def test_optional_fields(self):
        from app.schemas import ChapterResponse
        ch = ChapterResponse(chapter_index=5)
        assert ch.name is None
        assert ch.start_time_secs is None


class TestSyncChapterRecord:
    """SyncChapterRecord serialization."""

    def test_serialization(self):
        from app.schemas import SyncChapterRecord
        ch = SyncChapterRecord(chapter_index=3, name="Act 2", start_time_secs=3600)
        data = ch.model_dump()
        assert data["chapter_index"] == 3
        assert data["name"] == "Act 2"
        assert data["start_time_secs"] == 3600


class TestTitleCreateChapters:
    """TitleCreate with chapters field — backward compatibility."""

    def test_title_create_empty_chapters(self):
        from app.schemas import TitleCreate
        t = TitleCreate(title_index=0, chapters=[])
        assert t.chapters == []

    def test_title_create_no_chapters_field(self):
        from app.schemas import TitleCreate
        t = TitleCreate(title_index=0)
        assert t.chapters == []

    def test_title_create_with_chapters(self):
        from app.schemas import ChapterCreate, TitleCreate
        t = TitleCreate(
            title_index=0,
            chapters=[ChapterCreate(chapter_index=1, name="Ch1", start_time_secs=0)],
        )
        assert len(t.chapters) == 1
        assert t.chapters[0].chapter_index == 1


class TestTitleResponseChapters:
    """TitleResponse includes chapters list."""

    def test_title_response_default_empty(self):
        from app.schemas import TitleResponse
        t = TitleResponse(title_index=0)
        assert t.chapters == []

    def test_title_response_with_chapters(self):
        from app.schemas import ChapterResponse, TitleResponse
        t = TitleResponse(
            title_index=0,
            chapters=[ChapterResponse(chapter_index=1, name="Intro", start_time_secs=0)],
        )
        assert len(t.chapters) == 1


class TestSyncTitleRecordChapters:
    """SyncTitleRecord includes chapters list."""

    def test_sync_title_record_default_empty(self):
        from app.schemas import SyncTitleRecord
        t = SyncTitleRecord(title_index=0)
        assert t.chapters == []

    def test_sync_title_record_with_chapters(self):
        from app.schemas import SyncChapterRecord, SyncTitleRecord
        t = SyncTitleRecord(
            title_index=0,
            chapters=[SyncChapterRecord(chapter_index=1, name="Ch", start_time_secs=0)],
        )
        assert len(t.chapters) == 1
