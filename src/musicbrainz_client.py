"""
Pulls DragonForce's studio album + track metadata from the MusicBrainz API.
No API key required, just a courteous User-Agent header (MB will rate-limit
or block requests that don't identify themselves).

Every response is cached to data/raw/ as JSON on first fetch and read back
from disk on every call after that, so re-running a notebook top to bottom
costs nothing and works offline. Pass refresh=True to force a re-fetch when
you actually want fresh data from MusicBrainz.

Docs: https://musicbrainz.org/doc/MusicBrainz_API
"""

import hashlib
import json
import time
import warnings
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

MB_BASE_URL: str = "https://musicbrainz.org/ws/2"
USER_AGENT: str = "dragonforce-analysis/0.1 ( your-email@example.com )"
DRAGONFORCE_MBID: str = "ef58d4c9-0d40-42ba-bfab-9186c1483edd"  # musicbrainz.org/artist/ef58d4c9-...

CACHE_DIR: Path = Path(__file__).resolve().parent.parent / "data" / "raw"
MIN_REQUEST_INTERVAL: float = 1.0  # MusicBrainz asks for max ~1 request/sec unauthenticated

_last_request_time: float = 0.0


def _cache_path(endpoint: str, params: dict[str, str]) -> Path:
    """Map an endpoint + params pair to a stable, filesystem-safe cache filename.

    The endpoint goes in readable (so `release/<mbid>` stays greppable), and a
    short hash of the params disambiguates different queries against the same
    endpoint without producing an unreadable 200-character filename.
    """
    slug: str = endpoint.replace("/", "_")
    digest: str = hashlib.sha256(urlencode(sorted(params.items())).encode()).hexdigest()[:8]
    return CACHE_DIR / f"{slug}__{digest}.json"


def _rate_limit() -> None:
    """Block until at least MIN_REQUEST_INTERVAL has passed since the last request."""
    global _last_request_time
    elapsed: float = time.monotonic() - _last_request_time
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.monotonic()


def _get(endpoint: str, params: dict[str, str], refresh: bool = False) -> dict[str, Any]:
    """Return a MusicBrainz response, from data/raw/ if cached, otherwise over HTTP.

    A successful fetch is written to the cache before returning, so a failure
    part way through a multi-album pull keeps whatever it already retrieved.
    """
    path: Path = _cache_path(endpoint, params)
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    _rate_limit()
    headers: dict[str, str] = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    response: requests.Response = requests.get(
        f"{MB_BASE_URL}/{endpoint}", params=params, headers=headers
    )
    response.raise_for_status()
    data: dict[str, Any] = response.json()

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def get_release_groups(
    artist_mbid: str = DRAGONFORCE_MBID, refresh: bool = False
) -> list[dict[str, Any]]:
    """Fetch all studio albums (release groups) for the artist."""
    params: dict[str, str] = {
        "artist": artist_mbid,
        "type": "album",
        "limit": "100",
    }
    data: dict[str, Any] = _get("release-group", params, refresh=refresh)
    return data.get("release-groups", [])


def get_release_tracks(release_mbid: str, refresh: bool = False) -> list[dict[str, Any]]:
    """Fetch the tracklist for a specific release (a specific pressing of an album)."""
    params: dict[str, str] = {"inc": "recordings"}
    data: dict[str, Any] = _get(f"release/{release_mbid}", params, refresh=refresh)
    media: list[dict[str, Any]] = data.get("media", [])
    tracks: list[dict[str, Any]] = []
    for medium in media:
        tracks.extend(medium.get("tracks", []))
    return tracks


def get_releases_for_group(
    release_group_mbid: str, refresh: bool = False
) -> list[dict[str, Any]]:
    """Fetch every release (pressing) that belongs to one release group.

    A release group is the abstract album; a release is one specific pressing of
    it, and only a release carries a tracklist. That is why get_release_tracks()
    needs a release MBID and the release-group listing alone can't feed it.

    inc=media brings back each pressing's format, disc count and track count,
    which is what tells an original single-CD pressing apart from a 2-disc
    reissue or a bonus-track edition without opening a browser.
    """
    params: dict[str, str] = {
        "release-group": release_group_mbid,
        "inc": "media",
        "limit": "100",
    }
    data: dict[str, Any] = _get("release", params, refresh=refresh)
    releases: list[dict[str, Any]] = data.get("releases", [])
    total: int = data.get("release-count", len(releases))
    if total > len(releases):
        # Silently analysing a truncated list is exactly how you end up
        # concluding an album has no CD pressing when page two says otherwise.
        warnings.warn(
            f"{release_group_mbid}: {total} releases exist but only "
            f"{len(releases)} were fetched. Raise the limit or paginate.",
            stacklevel=2,
        )
    return releases


def summarize_release(release: dict[str, Any]) -> dict[str, Any]:
    """Flatten the fields that actually matter when picking a canonical pressing.

    Track count is summed across media so a 2-disc edition reports its real
    total, and formats are joined ("CD+DVD") so mixed-media editions are visible
    rather than hidden behind whichever disc happened to be first.
    """
    media: list[dict[str, Any]] = release.get("media", [])
    formats: str = "+".join(m.get("format") or "?" for m in media) or "?"
    track_count: int = sum(m.get("track-count") or 0 for m in media)
    return {
        "release_mbid": release.get("id") or "",
        "title": release.get("title") or "",
        "date": release.get("date") or "",
        "country": release.get("country") or "",
        "status": release.get("status") or "",
        "format": formats,
        "discs": len(media),
        "tracks": track_count,
        "disambiguation": release.get("disambiguation") or "",
    }


if __name__ == "__main__":
    albums: list[dict[str, Any]] = get_release_groups()
    for album in albums:
        print(album.get("title"), "-", album.get("first-release-date"))
