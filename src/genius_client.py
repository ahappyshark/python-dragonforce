"""
Pulls lyrics via the Genius API (lyricsgenius wrapper) for LOCAL analysis only.

Needs GENIUS_ACCESS_TOKEN in your .env (create an app at
https://genius.com/api-clients).

⚠️ Copyright note: this is fine for pulling lyrics into your own local
word-frequency / sentiment / theme-clustering analysis. Don't publish or
redistribute the raw lyric text in your portfolio piece — publish your
*findings* (charts, word frequencies, theme buckets), not the lyrics.
data/raw/lyrics/ is gitignored for exactly this reason, and only derived
counts ever reach data/processed/.

Responses are cached to data/raw/lyrics/<track_id>.json, including misses, so
a failed lookup doesn't re-query on every run. The cache holds the RAW text as
Genius returned it and cleaning happens on read, so the scrubbing rules can be
improved without re-fetching a single song.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import lyricsgenius
from dotenv import load_dotenv

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

CACHE_DIR: Path = REPO_ROOT / "data" / "raw" / "lyrics"
OVERRIDES_CSV: Path = REPO_ROOT / "data" / "annotations" / "genius_overrides.csv"

# Junk lyricsgenius leaves in the text. Each is anchored so it can only strip
# what it is meant to strip; an unanchored "Lyrics" or "Embed" would happily
# eat song text that happens to contain the word.
HEADER_PATTERNS: list[str] = [
    # "12 ContributorsTranslationsEspañolPortuguêsSong Title Lyrics"
    r"\A\d+\s*Contributors?.*?Lyrics\s*",
    # Same header without a contributor count.
    r"\A(?:Translations)?(?:[A-Z][a-zà-ÿ]+)*?[^\n]{0,120}?\s*Lyrics\s*",
]
BODY_PATTERNS: list[str] = [
    r"You might also like",
    r"See .{1,60} LiveGet tickets as low as \$\d+",
]
# A trailing view count fused to "Embed", e.g. "1.2KEmbed" or "537Embed".
TRAILER_PATTERN: str = r"\s*\d*(?:\.\d+)?[KM]?Embed\s*\Z"
SECTION_HEADER_PATTERN: str = r"^\[[^\]]{0,80}\]\s*$"


def get_client() -> lyricsgenius.Genius:
    """Build an authenticated lyricsgenius client.

    remove_section_headers is left OFF deliberately. Section markers are
    stripped by strip_section_headers() instead, so the cached text keeps the
    song's structure and a later phase (matching a key change to "the last
    chorus", say) can still see where the choruses were.
    """
    token: str | None = os.getenv("GENIUS_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("Set GENIUS_ACCESS_TOKEN in .env")
    return lyricsgenius.Genius(
        token,
        skip_non_songs=True,
        excluded_terms=["(Remix)", "(Live)"],
        remove_section_headers=False,
        verbose=False,
        timeout=15,
        retries=3,
    )


def clean_lyrics(raw: str) -> str:
    """Strip Genius' page furniture, leaving the song text.

    Kept separate from fetching so it can be unit-tested against fixtures and
    re-run over the existing cache. A silent regression here would corrupt
    every word count downstream without changing a single API response.
    """
    if not raw:
        return ""
    text: str = raw
    for pattern in HEADER_PATTERNS:
        new_text: str = re.sub(pattern, "", text, count=1, flags=re.DOTALL)
        if new_text != text:
            text = new_text
            break
    for pattern in BODY_PATTERNS:
        text = re.sub(pattern, "\n", text)
    text = re.sub(TRAILER_PATTERN, "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_section_headers(text: str) -> str:
    """Remove [Verse 1] / [Chorus] markers, for word-frequency work."""
    without: str = re.sub(SECTION_HEADER_PATTERN, "", text, flags=re.MULTILINE)
    return re.sub(r"\n{3,}", "\n\n", without).strip()


def lyric_stats(text: str) -> dict[str, int]:
    """Word and line counts over cleaned, header-free lyrics."""
    body: str = strip_section_headers(text)
    words: list[str] = re.findall(r"[a-zA-Z']+", body.lower())
    return {
        "lyric_word_count": len(words),
        "lyric_unique_words": len(set(words)),
        "lyric_line_count": len([ln for ln in body.splitlines() if ln.strip()]),
    }


def load_overrides() -> dict[str, dict[str, str]]:
    """Read the hand-maintained Genius match corrections, keyed by track_id.

    Genius search gets a meaningful share of tracks wrong — live cuts, other
    bands' songs sharing a title, and alternate versions that don't exist there
    as separate entries. This file is how a human overrules it.
    """
    import csv

    if not OVERRIDES_CSV.exists():
        return {}
    with OVERRIDES_CSV.open(encoding="utf-8-sig", newline="") as fh:
        return {
            row["track_id"]: {k: (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(fh)
            if row.get("track_id")
        }


def _cache_path(track_id: str) -> Path:
    return CACHE_DIR / f"{track_id}.json"


def fetch_lyrics(
    genius: lyricsgenius.Genius | None,
    track_id: str,
    track_title: str,
    artist: str = "DragonForce",
    override: dict[str, str] | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Return a cache record for one track, fetching only if not already cached.

    Misses are cached alongside hits. Without that, every run re-queries every
    song Genius doesn't have, which is slow and burns rate limit for a result
    that will not change.

    The record always reports which title was actually searched and what Genius
    returned, so a wrong match is visible in the data rather than silently
    becoming that track's lyrics.
    """
    path: Path = _cache_path(track_id)
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    override = override or {}
    record: dict[str, Any] = {
        "track_id": track_id,
        "track_title": track_title,
        "searched_title": track_title,
        "genius_song_id": None,
        "genius_title": None,
        "genius_artist": None,
        "genius_url": None,
        "lyrics_raw": None,
        "status": "not_found",
        "note": override.get("note", ""),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    if override.get("no_lyrics_reason"):
        record["status"] = "no_lyrics"
        record["note"] = override["no_lyrics_reason"]
    elif override.get("same_as_track_id"):
        record["status"] = "same_as"
        record["genius_song_id"] = override["same_as_track_id"]
        record["note"] = override.get("note", "") or "lyrics taken from another track"
    else:
        if genius is None:
            raise RuntimeError(f"{track_id} is not cached and no Genius client was given")
        search_title: str = override.get("search_title") or track_title
        record["searched_title"] = search_title
        song: Any = (
            genius.search_song(song_id=int(override["genius_song_id"]))
            if override.get("genius_song_id")
            else genius.search_song(search_title, artist)
        )
        if song is not None:
            record.update({
                "genius_song_id": getattr(song, "id", None),
                "genius_title": getattr(song, "title", None),
                "genius_artist": getattr(song, "artist", None),
                "genius_url": getattr(song, "url", None),
                "lyrics_raw": getattr(song, "lyrics", None),
                "status": "ok" if getattr(song, "lyrics", None) else "empty",
            })

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return record


def load_cached(track_id: str) -> dict[str, Any] | None:
    """Read one cached record without touching the network."""
    path: Path = _cache_path(track_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
