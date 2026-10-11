"""GET with retries, shared by the live sources.

Retries timeouts, connection errors, 5xx and 429 (honouring the rate-limit reset header), then gives up
and raises, so the caller can fall back to synthetic data.
"""

from __future__ import annotations

import logging
import time

import httpx

log = logging.getLogger("dusttrace")

RETRY_STATUS = {429, 500, 502, 503, 504}


def get(client: httpx.Client, url: str, params: dict | None = None, tries: int = 4,
        backoff: float = 2.0, sleep=time.sleep) -> httpx.Response:
    for attempt in range(1, tries + 1):
        try:
            r = client.get(url, params=params)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            if attempt == tries:
                raise
            wait = backoff * 2 ** (attempt - 1)
            log.info("%s failed (%s); retry %d in %.0fs", url, e, attempt, wait)
        else:
            if r.status_code not in RETRY_STATUS or attempt == tries:
                r.raise_for_status()
                return r
            wait = backoff * 2 ** (attempt - 1)
            if r.status_code == 429:
                reset = r.headers.get("x-ratelimit-reset") or r.headers.get("retry-after")
                if reset and reset.isdigit():
                    wait = min(int(reset) + 1, 65)
            log.info("%s returned %d; retry %d in %.0fs", url, r.status_code, attempt, wait)
        sleep(wait)
    raise AssertionError("unreachable")
