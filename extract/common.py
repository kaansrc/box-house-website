"""Shared config + helpers for the Box House content extractor."""
import json
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
try:
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover
    from requests.packages.urllib3.util.retry import Retry

BASE = "https://theboxhousehotel.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) BoxHouseArchiver/1.0 (own-site migration)"

# Repo root = parent of extract/
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
RAW_HTML = RAW / "html"
CONTENT = ROOT / "content"
ASSETS = ROOT / "assets"
IMAGES = ASSETS / "images"

for d in (RAW, RAW_HTML, CONTENT, ASSETS, IMAGES):
    d.mkdir(parents=True, exist_ok=True)

# Be gentle: the site's robots.txt asks for a crawl-delay. It's our own site, so we
# don't need the full 10s, but we stay modest.
REQUEST_WAIT = 0.4


def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    retry = Retry(
        total=5,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


def get(session, url, **kwargs):
    """GET with a polite pause afterward."""
    kwargs.setdefault("timeout", 30)
    r = session.get(url, **kwargs)
    time.sleep(REQUEST_WAIT)
    return r


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
