from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---- Simple in-process rate limiter (>= 0.5s between requests) ----
_RATE_LIMIT_SECONDS = 0.5
_last_request_ts = 0.0
_lock = threading.Lock()

DEFAULT_CACHE_DIR = Path("data/raw/http_cache")


@dataclass(frozen=True)
class HttpResult:
    url: str
    from_cache: bool
    path: Path
    fetched_at: datetime


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _cache_path(cache_dir: Path, url: str) -> Path:
    return cache_dir / f"{_hash(url)}.json"


def _is_fresh(path: Path, ttl_hours: int) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return datetime.now(UTC) - mtime < timedelta(hours=ttl_hours)


def _sleep_if_needed() -> None:
    global _last_request_ts
    with _lock:
        now = time.monotonic()
        delta = now - _last_request_ts
        if delta < _RATE_LIMIT_SECONDS:
            time.sleep(_RATE_LIMIT_SECONDS - delta)
        _last_request_ts = time.monotonic()


def get_json(
    url: str,
    *,
    force_refresh: bool = False,
    ttl_hours: int = 6,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    timeout: float = 10.0,
    max_retries: int = 4,
) -> dict[str, Any]:
    """
    Fetch a JSON from URL with disk cache + retry + simple rate limiting.

    Returns parsed JSON (dict) and writes raw to cache for reproducibility.
    """
    _ensure_dir(cache_dir)
    cache_path = _cache_path(cache_dir, url)

    if not force_refresh and _is_fresh(cache_path, ttl_hours):
        logger.info("cache hit: %s -> %s", url, cache_path)
        with cache_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    # Request with exponential backoff
    headers = {
        "User-Agent": "fpl-optimizer/0.1 (+github.com/your/repo)",
        "Accept": "application/json",
    }
    backoff = 0.5
    attempt = 0
    while True:
        attempt += 1
        try:
            _sleep_if_needed()
            resp = requests.get(url, headers=headers, timeout=timeout)
            status = resp.status_code
            if status >= 200 and status < 300:
                text = resp.text
                # Write raw text (as returned) to cache for traceability
                with cache_path.open("w", encoding="utf-8") as f:
                    f.write(text)
                logger.info("fetched: %s (attempt %d) -> %s", url, attempt, cache_path)
                return resp.json()
            elif status in (429, 500, 502, 503, 504):
                if attempt >= max_retries:
                    resp.raise_for_status()
                logger.warning("retryable status %d for %s (attempt %d)", status, url, attempt)
                time.sleep(backoff)
                backoff *= 2
                continue
            else:
                # Non-retryable: log body snippet and raise
                body = resp.text[:200]
                logger.error("http %d for %s: %s...", status, url, body)
                resp.raise_for_status()
        except requests.RequestException as e:
            if attempt >= max_retries:
                logger.exception("request failed (max retries reached) for %s", url)
                raise
            logger.warning("request error (%s) for %s (attempt %d) -> retrying", e, url, attempt)
            time.sleep(backoff)
            backoff *= 2


# ---- Convenience: known FPL endpoints ----

BASE = "https://fantasy.premierleague.com/api"
BOOTSTRAP_STATIC = f"{BASE}/bootstrap-static/"
FIXTURES = f"{BASE}/fixtures/"
EVENT_LIVE = lambda gw: f"{BASE}/event/{gw}/live/"  # noqa: E731
ELEMENT_SUMMARY = lambda pid: f"{BASE}/element-summary/{pid}/"  # noqa: E731
