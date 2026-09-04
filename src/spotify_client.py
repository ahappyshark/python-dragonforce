"""
Pulls album/track metadata from Spotify via the spotipy wrapper.

⚠️ IMPORTANT: as of Nov 27 2024, Spotify killed the audio-features and
audio-analysis endpoints for any NEW app (yours will be new). That means
get_audio_features() below will 403 for you — there is currently no
official replacement. Options if you want tempo/key/energy/valence data:
  1. Skip it. Lean harder on lyrics + your manual key-change annotation.
  2. Run local DSP (librosa/essentia) against audio you legally own
     (your own CD rips/purchases) instead of pulling from Spotify's API.
  3. A few third-party "audio features" APIs exist as unofficial
     replacements, but they're inconsistent/unreliable — treat as
     experimental if you go this route.
Album/track/artist lookups below are unaffected and still work fine.

Needs SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET in your .env
(create an app at https://developer.spotify.com/dashboard).

Docs: https://developer.spotify.com/documentation/web-api
"""

import os
from typing import Any

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyClientCredentials

load_dotenv()

DRAGONFORCE_ARTIST_ID: str = "2pH3wEn4eYlMMIIQyKPbVR"  # open.spotify.com/artist/2pH3wEn4eYlMMIIQyKPbVR


def get_client() -> spotipy.Spotify:
    """Build an authenticated spotipy client using client-credentials flow."""
    client_id: str | None = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret: str | None = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in .env")
    auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
    return spotipy.Spotify(auth_manager=auth_manager)


def get_all_albums(sp: spotipy.Spotify, artist_id: str = DRAGONFORCE_ARTIST_ID) -> list[dict[str, Any]]:
    """Fetch all studio albums for the artist (paginated)."""
    albums: list[dict[str, Any]] = []
    results: dict[str, Any] = sp.artist_albums(artist_id, album_type="album", limit=50)
    albums.extend(results["items"])
    while results.get("next"):
        results = sp.next(results)
        albums.extend(results["items"])
    return albums


def get_album_tracks(sp: spotipy.Spotify, album_id: str) -> list[dict[str, Any]]:
    """Fetch tracklist for a single album."""
    results: dict[str, Any] = sp.album_tracks(album_id)
    return results["items"]


def get_audio_features(sp: spotipy.Spotify, track_ids: list[str]) -> list[dict[str, Any]]:
    """
    Fetch audio features (tempo, key, mode, energy, valence...) for up to 100 track IDs at a time.

    ⚠️ Will raise a 403 for apps created after Nov 27 2024 — see module docstring.
    Left in place in case Spotify restores access or you get a grandfathered app.
    """
    features: list[dict[str, Any]] = []
    batch_size: int = 100
    for i in range(0, len(track_ids), batch_size):
        batch: list[str] = track_ids[i : i + batch_size]
        features.extend(sp.audio_features(batch))
    return features


if __name__ == "__main__":
    client: spotipy.Spotify = get_client()
    albums: list[dict[str, Any]] = get_all_albums(client)
    for album in albums:
        print(album["name"], "-", album["release_date"])
