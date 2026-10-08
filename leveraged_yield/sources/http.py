"""Small JSON-over-HTTP helpers with an on-disk cache."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import requests

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
USER_AGENT = "leveraged-yield-optimizer/1.0"


def _cache_file(key: str) -> Path:
    return CACHE_DIR / (hashlib.sha256(key.encode()).hexdigest()[:24] + ".json")


def _cached(key: str, max_age_s: float):
    path = _cache_file(key)
    if path.exists() and time.time() - path.stat().st_mtime < max_age_s:
        return json.loads(path.read_text())
    return None


def _store(key: str, data) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_file(key).write_text(json.dumps(data))


def get_json(url: str, max_age_s: float = 3600, timeout: float = 90, retries: int = 3):
    key = "GET " + url
    data = _cached(key, max_age_s)
    if data is not None:
        return data
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            data = resp.json()
            _store(key, data)
            return data
        except (requests.RequestException, ValueError) as err:
            last_err = err
            time.sleep(2 ** attempt)
    raise RuntimeError(f"GET {url} failed: {last_err}")


def post_graphql(url: str, query: str, variables: dict | None = None,
                 max_age_s: float = 3600, timeout: float = 90, retries: int = 3):
    body = {"query": query, "variables": variables or {}}
    key = "POST " + url + json.dumps(body, sort_keys=True)
    data = _cached(key, max_age_s)
    if data is not None:
        return data
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.post(url, json=body, timeout=timeout,
                                 headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("errors"):
                raise RuntimeError(f"GraphQL errors from {url}: {payload['errors']}")
            _store(key, payload["data"])
            return payload["data"]
        except (requests.RequestException, ValueError) as err:
            last_err = err
            time.sleep(2 ** attempt)
    raise RuntimeError(f"POST {url} failed: {last_err}")
