"""Pure scraping logic using yt-dlp."""

from typing import Any, Optional

import yt_dlp


def fetch_channel_info(
  handle: str, playlist_limit: Optional[int] = 0
) -> dict[str, Any]:
  """Fetches channel-level metadata and optionally a flat list of video entries."""
  urls_to_try = [
    f"https://www.youtube.com/{handle}/videos?hl=pt&persist_hl=1",
    f"https://www.youtube.com/{handle}?hl=pt&persist_hl=1",
  ]

  ydl_opts = {
    "extract_flat": "in_playlist",
    "skip_download": True,
    "quiet": True,
    "no_warnings": True,
    "extractor_args": {"youtube": ["lang=pt"]},
  }

  if playlist_limit is not None:
    ydl_opts["playlistend"] = playlist_limit

  last_error = None
  for url in urls_to_try:
    try:
      with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)
    except Exception as e:
      last_error = e
      continue

  raise last_error or Exception(f"Failed to scrape {handle}")
