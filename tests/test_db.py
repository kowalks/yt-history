"""Tests for the database layer (db.py).

Covers: normalization, channel management, video deduplication,
versioning, visual fingerprint storage, and reset behavior.
"""

import sqlite3
import uuid
import pytest
import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_channel(handle="@testchan", name="Test Channel"):
    db.add_channel(handle, name=name)
    return handle


def _scrape_video(scrape_id, handle, video_id="vid001", title="My Title",
                  description="desc", thumbnail=None, duration=120,
                  upload_date="20240101"):
    thumbnail = thumbnail or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    db.process_scraped_video(
        scrape_id=scrape_id,
        handle=handle,
        video_id=video_id,
        title=title,
        description=description,
        thumbnail=thumbnail,
        upload_date=upload_date,
        duration=duration,
        record_uuid=str(uuid.uuid4()),
    )


# ---------------------------------------------------------------------------
# normalize_handle
# ---------------------------------------------------------------------------

class TestNormalizeHandle:
    def test_adds_at_prefix(self):
        assert db.normalize_handle("mkbhd") == "@mkbhd"

    def test_preserves_existing_at(self):
        assert db.normalize_handle("@mkbhd") == "@mkbhd"

    def test_strips_extra_at(self):
        assert db.normalize_handle("@@mkbhd") == "@mkbhd"

    def test_mixed_case_preserved(self):
        assert db.normalize_handle("MrBeast") == "@MrBeast"


# ---------------------------------------------------------------------------
# Channel management
# ---------------------------------------------------------------------------

class TestChannelManagement:
    def test_add_channel(self, test_db):
        _add_channel("@chan1", "Chan One")
        df = db.get_channels_df()
        assert "@chan1" in df["handle"].values

    def test_add_duplicate_channel_is_idempotent(self, test_db):
        _add_channel("@chan1")
        _add_channel("@chan1")  # should not raise
        df = db.get_channels_df()
        assert len(df[df["handle"] == "@chan1"]) == 1

    def test_remove_channel_soft_deletes(self, test_db):
        _add_channel("@chan1")
        db.remove_channel("@chan1")
        df = db.get_channels_df()
        assert "@chan1" not in df["handle"].values

    def test_update_channel_name(self, test_db):
        _add_channel("@chan1", name="Old Name")
        db.update_channel_name("@chan1", "New Name")
        df = db.get_channels_df()
        row = df[df["handle"] == "@chan1"].iloc[0]
        assert row["name"] == "New Name"


# ---------------------------------------------------------------------------
# process_scraped_video — deduplication & versioning
# ---------------------------------------------------------------------------

class TestVideoProcessing:
    def _setup(self, test_db):
        handle = _add_channel()
        scrape_id = str(uuid.uuid4())
        db.start_scrape_session(scrape_id)
        return handle, scrape_id

    def test_first_scrape_creates_record_with_is_change_zero(self, test_db):
        handle, scrape_id = self._setup(test_db)
        _scrape_video(scrape_id, handle)

        conn = sqlite3.connect(test_db)
        row = conn.execute("SELECT is_change FROM videos WHERE video_id = 'vid001'").fetchone()
        conn.close()
        assert row[0] == 0

    def test_same_metadata_reuses_existing_uuid(self, test_db):
        handle, scrape_id = self._setup(test_db)
        _scrape_video(scrape_id, handle)

        scrape_id2 = str(uuid.uuid4())
        db.start_scrape_session(scrape_id2)
        _scrape_video(scrape_id2, handle)  # identical metadata

        conn = sqlite3.connect(test_db)
        count = conn.execute("SELECT COUNT(*) FROM videos WHERE video_id = 'vid001'").fetchone()[0]
        conn.close()
        assert count == 1, "Duplicate metadata should NOT create a new record"

    def test_title_change_creates_new_version(self, test_db):
        handle, scrape_id = self._setup(test_db)
        _scrape_video(scrape_id, handle, title="Original Title")

        scrape_id2 = str(uuid.uuid4())
        db.start_scrape_session(scrape_id2)
        _scrape_video(scrape_id2, handle, title="Updated Title")

        conn = sqlite3.connect(test_db)
        rows = conn.execute("SELECT is_change FROM videos WHERE video_id = 'vid001' ORDER BY created_at").fetchall()
        conn.close()
        assert len(rows) == 2
        assert rows[0][0] == 0   # original: not a change
        assert rows[1][0] == 1   # updated: is a change

    def test_video_linked_to_scrape_session(self, test_db):
        handle, scrape_id = self._setup(test_db)
        _scrape_video(scrape_id, handle)

        conn = sqlite3.connect(test_db)
        linked = conn.execute(
            "SELECT COUNT(*) FROM scrape_videos WHERE scrape_id = ?", (scrape_id,)
        ).fetchone()[0]
        conn.close()
        assert linked == 1


# ---------------------------------------------------------------------------
# Visual fingerprinting storage
# ---------------------------------------------------------------------------

class TestVisualFingerprinting:
    def _setup_video(self, test_db):
        handle = _add_channel()
        scrape_id = str(uuid.uuid4())
        db.start_scrape_session(scrape_id)
        _scrape_video(scrape_id, handle)
        conn = sqlite3.connect(test_db)
        row = conn.execute("SELECT uuid FROM videos WHERE video_id = 'vid001'").fetchone()
        conn.close()
        return scrape_id, row[0]

    def test_update_video_visuals_stores_hash(self, test_db):
        _, video_uuid = self._setup_video(test_db)
        db.update_video_visuals(video_uuid, "abc123hash", "etag-001")

        conn = sqlite3.connect(test_db)
        row = conn.execute(
            "SELECT thumbnail_hash, thumbnail_etag FROM videos WHERE uuid = ?",
            (video_uuid,)
        ).fetchone()
        conn.close()
        assert row[0] == "abc123hash"
        assert row[1] == "etag-001"

    def test_promote_video_creates_new_version(self, test_db):
        scrape_id, old_uuid = self._setup_video(test_db)
        # Store initial hash
        db.update_video_visuals(old_uuid, "oldhash", "etag-old")

        new_uuid = str(uuid.uuid4())
        db.promote_video_to_new_version(scrape_id, old_uuid, new_uuid, "newhash", "etag-new")

        conn = sqlite3.connect(test_db)
        new_row = conn.execute(
            "SELECT thumbnail_hash, is_change FROM videos WHERE uuid = ?", (new_uuid,)
        ).fetchone()
        # Scrape should now link to new version
        link = conn.execute(
            "SELECT video_uuid FROM scrape_videos WHERE scrape_id = ?", (scrape_id,)
        ).fetchone()
        conn.close()

        assert new_row[0] == "newhash"
        assert new_row[1] == 1             # marked as a change
        assert link[0] == new_uuid         # scrape now points to new version


# ---------------------------------------------------------------------------
# Database reset
# ---------------------------------------------------------------------------

class TestResetDb:
    def test_reset_clears_all_data(self, test_db):
        _add_channel()
        db.reset_db()

        df = db.get_channels_df()
        assert df.empty

    def test_reset_preserves_schema(self, test_db):
        db.reset_db()
        # Should be able to add channels again without error
        _add_channel("@fresh")
        df = db.get_channels_df()
        assert "@fresh" in df["handle"].values


# ---------------------------------------------------------------------------
# Delete channel removes associated video records from view
# ---------------------------------------------------------------------------

class TestDeleteChannelRecords:
    def test_deleted_channel_videos_hidden_from_listing(self, test_db):
        handle = _add_channel()
        scrape_id = str(uuid.uuid4())
        db.start_scrape_session(scrape_id)
        _scrape_video(scrape_id, handle, video_id="vid_del")

        db.remove_channel(handle)

        df = db.get_video_records_df()
        assert "vid_del" not in df["video_id"].values


# ---------------------------------------------------------------------------
# mark_missing_videos_deleted
# ---------------------------------------------------------------------------

class TestDeletedVideoDetection:
    def _setup(self, test_db):
        handle = _add_channel()
        scrape_id = str(uuid.uuid4())
        db.start_scrape_session(scrape_id)
        return handle, scrape_id

    def test_no_deletions_when_same_ids(self, test_db):
        handle, scrape_id = self._setup(test_db)
        _scrape_video(scrape_id, handle, video_id="vid001")

        # Second scrape still has the video
        scrape_id2 = str(uuid.uuid4())
        db.start_scrape_session(scrape_id2)
        db.mark_missing_videos_deleted(scrape_id2, handle, {"vid001"})

        conn = sqlite3.connect(test_db)
        deleted = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE video_id='vid001' AND status='DELETED'"
        ).fetchone()[0]
        conn.close()
        assert deleted == 0

    def test_missing_video_gets_deleted_status(self, test_db):
        handle, scrape_id = self._setup(test_db)
        _scrape_video(scrape_id, handle, video_id="vid001")
        _scrape_video(scrape_id, handle, video_id="vid002")

        # Second scrape: vid002 is gone
        scrape_id2 = str(uuid.uuid4())
        db.start_scrape_session(scrape_id2)
        db.mark_missing_videos_deleted(scrape_id2, handle, {"vid001"})

        conn = sqlite3.connect(test_db)
        status = conn.execute(
            "SELECT status FROM videos WHERE video_id='vid002' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()[0]
        conn.close()
        assert status == "DELETED"

    def test_already_deleted_not_duplicated(self, test_db):
        handle, scrape_id = self._setup(test_db)
        _scrape_video(scrape_id, handle, video_id="vid001")

        # Mark deleted in scrape 2
        scrape_id2 = str(uuid.uuid4())
        db.start_scrape_session(scrape_id2)
        db.mark_missing_videos_deleted(scrape_id2, handle, set())

        # Mark deleted again in scrape 3 — should not add another record
        scrape_id3 = str(uuid.uuid4())
        db.start_scrape_session(scrape_id3)
        db.mark_missing_videos_deleted(scrape_id3, handle, set())

        conn = sqlite3.connect(test_db)
        deleted_count = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE video_id='vid001' AND status='DELETED'"
        ).fetchone()[0]
        conn.close()
        assert deleted_count == 1, "Should only have one DELETED record, not one per scrape"


# ---------------------------------------------------------------------------
# New video detected on second scrape
# ---------------------------------------------------------------------------

class TestNewVideoDetection:
    def test_new_video_on_second_scrape(self, test_db):
        handle = _add_channel()
        scrape_id1 = str(uuid.uuid4())
        db.start_scrape_session(scrape_id1)
        _scrape_video(scrape_id1, handle, video_id="vid001")

        # Second scrape adds a brand-new video
        scrape_id2 = str(uuid.uuid4())
        db.start_scrape_session(scrape_id2)
        _scrape_video(scrape_id2, handle, video_id="vid002", title="Brand New Video")

        conn = sqlite3.connect(test_db)
        count = conn.execute("SELECT COUNT(DISTINCT video_id) FROM videos").fetchone()[0]
        conn.close()
        assert count == 2
