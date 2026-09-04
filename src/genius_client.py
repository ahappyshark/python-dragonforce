"""
Pulls lyrics via the Genius API (lyricsgenius wrapper) for LOCAL analysis only.

Needs GENIUS_ACCESS_TOKEN in your .env (create an app at
https://genius.com/api-clients).

⚠️ Copyright note: this is fine for pulling lyrics into your own local
word-frequency / sentiment / theme-clustering analysis. Don't publish or
redistribute the raw lyric text in your portfolio piece — publish your
*findings* (charts, word frequencies, theme buckets), not the lyrics.
"""

import os
from typing import Any

import lyricsgenius
from dotenv import load_dotenv

load_dotenv()


def get_client() -> lyricsgenius.Genius:
    """Build an authenticated lyricsgenius client."""
    token: str | None = os.getenv("GENIUS_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("Set GENIUS_ACCESS_TOKEN in .env")
    genius: lyricsgenius.Genius = lyricsgenius.Genius(
        token,
        skip_non_songs=True,
        excluded_terms=["(Remix)", "(Live)"],
        remove_section_headers=True,
        verbose=False,
    )
    return genius


def get_song_lyrics(genius: lyricsgenius.Genius, title: str, artist: str = "DragonForce") -> str | None:
    """Fetch lyrics for a single song. Returns None if not found."""
    song: Any = genius.search_song(title, artist)
    if song is None:
        return None
    return song.lyrics


if __name__ == "__main__":
    client: lyricsgenius.Genius = get_client()
    lyrics: str | None = get_song_lyrics(client, "Through the Fire and Flames")
    print(lyrics[:200] if lyrics else "Not found")
