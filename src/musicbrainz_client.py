"""
Pulls DragonForce's studio album + track metadata from the MusicBrainz API.
No API key required, just a courteous User-Agent header (MB will rate-limit
or block requests that don't identify themselves).

Docs: https://musicbrainz.org/doc/MusicBrainz_API
"""

import time
from typing import Any

import requests

MB_BASE_URL: str = "https://musicbrainz.org/ws/2"
USER_AGENT: str = "dragonforce-analysis/0.1 ( your-email@example.com )"
DRAGONFORCE_MBID: str = "ef58d4c9-0d40-42ba-bfab-9186c1483edd"  # musicbrainz.org/artist/ef58d4c9-...


def _get(endpoint: str, params: dict[str, str]) -> dict[str, Any]:
    """Single MusicBrainz GET request with required headers and a polite delay."""
    headers: dict[str, str] = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    response: requests.Response = requests.get(
        f"{MB_BASE_URL}/{endpoint}", params=params, headers=headers
    )
    response.raise_for_status()
    time.sleep(1.0)  # MusicBrainz asks for max ~1 request/sec unauthenticated
    return response.json()


def get_release_groups(artist_mbid: str = DRAGONFORCE_MBID) -> list[dict[str, Any]]:
    """Fetch all studio albums (release groups) for the artist."""
    params: dict[str, str] = {
        "artist": artist_mbid,
        "type": "album",
        "limit": "100",
    }
    data: dict[str, Any] = _get("release-group", params)
    return data.get("release-groups", [])


def get_release_tracks(release_mbid: str) -> list[dict[str, Any]]:
    """Fetch the tracklist for a specific release (a specific pressing of an album)."""
    params: dict[str, str] = {"inc": "recordings"}
    data: dict[str, Any] = _get(f"release/{release_mbid}", params)
    media: list[dict[str, Any]] = data.get("media", [])
    tracks: list[dict[str, Any]] = []
    for medium in media:
        tracks.extend(medium.get("tracks", []))
    return tracks


if __name__ == "__main__":
    albums: list[dict[str, Any]] = get_release_groups()
    for album in albums:
        print(album.get("title"), "-", album.get("first-release-date"))
