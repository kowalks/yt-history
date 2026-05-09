"""Tests for the tracker coordinator (tracker.py).

Covers: thumbnail URL construction, visual drift detection logic,
and the channel name retrieval behavior. All external I/O is mocked.
"""

import uuid
from unittest.mock import MagicMock, patch, call
import pandas as pd
import pytest

import tracker


# ---------------------------------------------------------------------------
# get_channel_name
# ---------------------------------------------------------------------------


class TestGetChannelName:
  def test_returns_uploader_name(self):
    fake_info = {"uploader": "Cool Channel", "channel": "Other"}
    with patch("tracker.scraper.fetch_channel_info", return_value=fake_info):
      assert tracker.get_channel_name("@cool") == "Cool Channel"

  def test_falls_back_to_channel_field(self):
    fake_info = {"channel": "Fallback Name"}
    with patch("tracker.scraper.fetch_channel_info", return_value=fake_info):
      assert tracker.get_channel_name("@cool") == "Fallback Name"

  def test_returns_none_on_exception(self):
    with patch(
      "tracker.scraper.fetch_channel_info", side_effect=Exception("404")
    ):
      assert tracker.get_channel_name("@invalid@@") is None

  def test_returns_none_when_no_name_fields(self):
    with patch("tracker.scraper.fetch_channel_info", return_value={}):
      assert tracker.get_channel_name("@nobody") is None


# ---------------------------------------------------------------------------
# Thumbnail URL construction
# ---------------------------------------------------------------------------


class TestThumbnailUrlConstruction:
  """Ensures we always use canonical YouTube thumbnail URLs, not yt-dlp's
  storyboard/sprite sheet URLs returned in flat extraction mode."""

  def test_canonical_url_always_used(self, test_db):
    """The stored thumbnail_url must always be the hqdefault.jpg pattern."""
    entries = [
      {
        "id": "abc123",
        "title": "Test Video",
        "description": "desc",
        # yt-dlp flat extraction might provide a storyboard URL
        "thumbnail": "https://i.ytimg.com/sb/abc123/storyboard3_L1/M0.jpg",
        "upload_date": "20240101",
        "duration": 300,
      }
    ]
    fake_info = {"uploader": "Chan", "entries": entries}

    with (
      patch("tracker.scraper.fetch_channel_info", return_value=fake_info),
      patch("tracker.db.update_channel_name"),
      patch("tracker.db.log_channel_scrape_result"),
      patch("tracker.db.finalize_scrape"),
      patch("tracker.audit_session_thumbnails"),
      patch("tracker.db.process_scraped_video") as mock_process,
    ):
      scrape_id = str(uuid.uuid4())
      tracker.scrape_channel("@chan", scrape_uuid=scrape_id)

    _, kwargs = mock_process.call_args[0], mock_process.call_args[1]
    stored_url = (
      mock_process.call_args.kwargs.get("thumbnail")
      or mock_process.call_args[0][5]
    )
    assert "hqdefault.jpg" in stored_url
    assert "storyboard" not in stored_url

  def test_entries_without_thumbnail_field_get_canonical_url(self, test_db):
    """Entries with no thumbnail key must still get canonical URL."""
    entries = [
      {
        "id": "xyz789",
        "title": "No Thumb",
        "description": "",
        "upload_date": "20240101",
        "duration": 60,
      }
    ]
    fake_info = {"uploader": "Chan", "entries": entries}

    with (
      patch("tracker.scraper.fetch_channel_info", return_value=fake_info),
      patch("tracker.db.update_channel_name"),
      patch("tracker.db.log_channel_scrape_result"),
      patch("tracker.db.finalize_scrape"),
      patch("tracker.audit_session_thumbnails"),
      patch("tracker.db.process_scraped_video") as mock_process,
    ):
      scrape_id = str(uuid.uuid4())
      tracker.scrape_channel("@chan", scrape_uuid=scrape_id)

    stored_url = mock_process.call_args.kwargs.get("thumbnail", "")
    assert "xyz789" in stored_url
    assert "hqdefault.jpg" in stored_url


# ---------------------------------------------------------------------------
# Visual drift detection (audit_session_thumbnails)
# ---------------------------------------------------------------------------


class TestVisualDriftDetection:
  """These are the most critical tests — they verify the three-state
  logic that was previously broken by a None comparison bug."""

  def _make_video_df(self, video_uuid, video_id, old_hash):
    return pd.DataFrame(
      [
        {
          "video_uuid": video_uuid,
          "video_id": video_id,
          "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
          "thumbnail_hash": old_hash,
          "thumbnail_etag": "etag-old" if old_hash else None,
        }
      ]
    )

  def test_first_time_stores_hash_only(self):
    """When old_hash is None, only update_video_visuals must be called.
    promote_video_to_new_version must NOT be called."""
    vid_uuid = str(uuid.uuid4())
    scrape_id = str(uuid.uuid4())
    df = self._make_video_df(vid_uuid, "vid001", old_hash=None)

    with (
      patch("tracker.db.get_scrape_videos_with_visuals", return_value=df),
      patch(
        "tracker.fingerprinter.get_visual_fingerprint",
        return_value=("etag-new", "hash-first", b"imgdata"),
      ),
      patch("tracker.db.update_video_visuals") as mock_update,
      patch("tracker.db.promote_video_to_new_version") as mock_promote,
      patch("tracker.fingerprinter.archive_thumbnail"),
    ):
      tracker.audit_session_thumbnails(scrape_id)

    mock_update.assert_called_once_with(vid_uuid, "hash-first", "etag-new")
    mock_promote.assert_not_called()

  def test_same_thumbnail_is_no_op(self):
    """When hash matches, neither update nor promote should be called."""
    vid_uuid = str(uuid.uuid4())
    scrape_id = str(uuid.uuid4())
    df = self._make_video_df(vid_uuid, "vid001", old_hash="same-hash")

    with (
      patch("tracker.db.get_scrape_videos_with_visuals", return_value=df),
      patch(
        "tracker.fingerprinter.get_visual_fingerprint",
        return_value=("etag", "same-hash", b"imgdata"),
      ),
      patch("tracker.db.update_video_visuals") as mock_update,
      patch("tracker.db.promote_video_to_new_version") as mock_promote,
      patch("tracker.fingerprinter.archive_thumbnail"),
    ):
      tracker.audit_session_thumbnails(scrape_id)

    mock_update.assert_not_called()
    mock_promote.assert_not_called()

  def test_visual_drift_promotes_new_version(self):
    """When old_hash differs from new phash, promote must be called."""
    vid_uuid = str(uuid.uuid4())
    scrape_id = str(uuid.uuid4())
    df = self._make_video_df(vid_uuid, "vid001", old_hash="old-hash")

    with (
      patch("tracker.db.get_scrape_videos_with_visuals", return_value=df),
      patch(
        "tracker.fingerprinter.get_visual_fingerprint",
        return_value=("etag-new", "new-hash", b"imgdata"),
      ),
      patch("tracker.db.update_video_visuals") as mock_update,
      patch("tracker.db.promote_video_to_new_version") as mock_promote,
      patch("tracker.fingerprinter.archive_thumbnail"),
    ):
      tracker.audit_session_thumbnails(scrape_id)

    mock_update.assert_not_called()
    assert mock_promote.call_count == 1
    args = mock_promote.call_args
    assert (
      args.kwargs.get("thumb_hash") == "new-hash" or args[0][3] == "new-hash"
    )

  def test_failed_fingerprint_fetch_is_skipped(self):
    """If fingerprinter returns no phash, the video is silently skipped."""
    vid_uuid = str(uuid.uuid4())
    scrape_id = str(uuid.uuid4())
    df = self._make_video_df(vid_uuid, "vid001", old_hash="old-hash")

    with (
      patch("tracker.db.get_scrape_videos_with_visuals", return_value=df),
      patch(
        "tracker.fingerprinter.get_visual_fingerprint",
        return_value=(None, None, None),
      ),
      patch("tracker.db.update_video_visuals") as mock_update,
      patch("tracker.db.promote_video_to_new_version") as mock_promote,
    ):
      tracker.audit_session_thumbnails(scrape_id)

    mock_update.assert_not_called()
    mock_promote.assert_not_called()

  def test_empty_session_returns_early(self):
    """An empty scrape session should exit without any DB calls."""
    scrape_id = str(uuid.uuid4())

    with (
      patch(
        "tracker.db.get_scrape_videos_with_visuals", return_value=pd.DataFrame()
      ),
      patch("tracker.fingerprinter.get_visual_fingerprint") as mock_fp,
    ):
      tracker.audit_session_thumbnails(scrape_id)

    mock_fp.assert_not_called()
