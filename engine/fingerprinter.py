"""High-speed visual fingerprinting engine."""

import os
from io import BytesIO
from typing import Optional

import imagehash
import requests
from PIL import Image

THUMB_DIR = "data/thumbnails"


def get_visual_fingerprint(
  url: str,
) -> tuple[Optional[str], Optional[str], Optional[bytes]]:
  """Fetches a thumbnail, returns (ETag, pHash, raw_bytes)."""
  try:
    # 1. HEAD request for ETag/Size
    head = requests.head(url, timeout=5)
    etag = head.headers.get("ETag") or head.headers.get("Content-Length")

    # 2. Download and Hash
    resp = requests.get(url, timeout=10)
    if resp.status_code != 200:
      return None, None, None

    img = Image.open(BytesIO(resp.content))
    # Use dhash (Difference Hash) as it's very fast and effective for this
    phash = str(imagehash.dhash(img))

    return etag, phash, resp.content
  except Exception as e:
    print(f"Fingerprint error for {url}: {e}")
    return None, None, None


def archive_thumbnail(video_id: str, phash: str, content: bytes) -> str:
  """Saves the thumbnail to local storage."""
  filename = f"{video_id}_{phash}.jpg"
  path = os.path.join(THUMB_DIR, filename)
  if not os.path.exists(path):
    with open(path, "wb") as f:
      f.write(content)
  return path
