"""Update-channel proxy.

Fetches the latest `versions.json` from a public CDN/raw URL on behalf of
the frontend. Browsers can't fetch Gitee Raw directly because Gitee sets
`Access-Control-Allow-Credentials: true` without `Access-Control-Allow-Origin`,
which fails CORS. Going through this same-origin endpoint sidesteps that.

A short in-process cache absorbs bursty refresh clicks so we don't hammer
the upstream when many windows refresh at once. Manual refresh bypasses
the cache via the `force=true` query parameter.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query
from loguru import logger

router = APIRouter(prefix="/api/updates", tags=["updates"])

UPSTREAM_URL = (
    "https://gitee.com/sun124578963_0/TokenMind/raw/main/versions.json"
)
SERVER_CACHE_TTL_S = 60.0
REQUEST_TIMEOUT_S = 6.0

_cache: dict[str, Any] = {"payload": None, "fetched_at": 0.0}


@router.get("/versions")
async def get_versions(
    force: bool = Query(False, description="Bypass the in-process cache."),
) -> Any:
    """Return the upstream versions.json verbatim."""
    now = time.monotonic()
    if (
        not force
        and _cache["payload"] is not None
        and now - _cache["fetched_at"] < SERVER_CACHE_TTL_S
    ):
        return _cache["payload"]

    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT_S,
            follow_redirects=True,
        ) as client:
            response = await client.get(
                UPSTREAM_URL, headers={"Accept": "application/json"}
            )
    except httpx.HTTPError as exc:
        logger.warning("Failed to fetch upstream versions.json: {}", exc)
        # Serve stale cache on transient upstream failure rather than 5xx-ing
        # the frontend, which would leave the user with no data at all.
        if _cache["payload"] is not None:
            return _cache["payload"]
        raise HTTPException(status_code=502, detail="upstream unavailable") from exc

    if response.status_code != 200:
        logger.warning(
            "Upstream versions.json returned {}: {}",
            response.status_code,
            response.text[:200],
        )
        if _cache["payload"] is not None:
            return _cache["payload"]
        raise HTTPException(
            status_code=502,
            detail=f"upstream returned {response.status_code}",
        )

    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning("Upstream versions.json is not valid JSON: {}", exc)
        if _cache["payload"] is not None:
            return _cache["payload"]
        raise HTTPException(status_code=502, detail="upstream returned invalid JSON") from exc

    _cache["payload"] = payload
    _cache["fetched_at"] = now
    return payload
