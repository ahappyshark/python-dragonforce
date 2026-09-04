"""
Fetches lyrics for every non-instrumental track and caches them locally.

Run from the repo root, with GENIUS_ACCESS_TOKEN set in .env:

    python scripts/fetch_lyrics.py

Roughly 90 API calls on the first run — a few minutes. Everything is cached to
data/raw/lyrics/ (gitignored), so later runs are instant and cost nothing.
--refresh re-fetches; --only <track_id> re-fetches one track after correcting
its override row.

The cache is never published. Only derived counts reach data/processed/.

The match report at the end is the point of this script. Genius search returns
the wrong song a meaningful share of the time — live cuts, other bands sharing
a title, alternate versions that don't exist there separately — and a wrong
match becomes that track's lyrics silently. Every row where Genius returned a
different title or a different artist is flagged for you to check against
data/annotations/genius_overrides.csv.
"""

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.genius_client import (  # noqa: E402
    _cache_path,
    clean_lyrics,
    fetch_lyrics,
    get_client,
    load_overrides,
    lyric_stats,
)
from scripts.build_dataset import make_title_key  # noqa: E402

TRACKS_CSV: Path = REPO_ROOT / "data" / "processed" / "tracks.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Re-fetch everything.")
    parser.add_argument("--only", metavar="TRACK_ID", help="Re-fetch a single track.")
    args = parser.parse_args()

    tracks: pd.DataFrame = pd.read_csv(TRACKS_CSV)
    overrides: dict[str, dict[str, str]] = load_overrides()
    print(f"{len(tracks)} tracks, {len(overrides)} override(s) loaded")

    unknown: set[str] = set(overrides) - set(tracks["track_id"])
    if unknown:
        raise SystemExit(f"ERROR: genius_overrides.csv references unknown track_id(s): "
                         f"{sorted(unknown)}")

    if args.only:
        tracks = tracks[tracks["track_id"] == args.only]
        if tracks.empty:
            raise SystemExit(f"ERROR: no track with track_id {args.only!r}")

    # The client is built lazily: a fully cached run needs no token at all.
    client: Any = None
    records: list[dict[str, Any]] = []
    refresh: bool = args.refresh or bool(args.only)
    total: int = len(tracks)

    for position, row in enumerate(tracks.itertuples(), start=1):
        override: dict[str, str] = overrides.get(row.track_id, {})
        cached: bool = _cache_path(row.track_id).exists()

        if str(row.is_instrumental).lower() == "yes":
            # Instrumentals have no lyrics by definition. Recording that as a
            # reason rather than a blank means the validation gate can tell
            # "correctly absent" apart from "we failed to fetch this".
            override = {**override, "no_lyrics_reason": override.get("no_lyrics_reason")
                        or "instrumental"}

        needs_network: bool = (
            (not cached or refresh)
            and not override.get("no_lyrics_reason")
            and not override.get("same_as_track_id")
        )
        if needs_network and client is None:
            client = get_client()

        record: dict[str, Any] = fetch_lyrics(
            client, row.track_id, row.track_title,
            override=override, refresh=refresh,
        )
        records.append({**record, "album": row.album, "expected_title": row.track_title})

        # One line per track, flushed, because the network calls are slow enough
        # that a silent run is indistinguishable from a hung one. "cached" lines
        # blur past; "fetch" lines are the ones actually costing a second or two.
        source: str = "fetch " if needs_network else "cached"
        title: str = row.track_title if len(row.track_title) <= 44 else row.track_title[:41] + "..."
        print(f"[{position:>3}/{total}] {source} {title:<44} {record['status']}", flush=True)

    print("\n=== match report ===")
    suspicious: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for record in records:
        counts[record["status"]] = counts.get(record["status"], 0) + 1
        if record["status"] != "ok":
            continue
        got: str = record.get("genius_title") or ""
        want: str = record.get("searched_title") or record["expected_title"]
        artist: str = (record.get("genius_artist") or "").lower()
        if make_title_key(got) != make_title_key(want) or "dragonforce" not in artist:
            suspicious.append(record)

    for status, count in sorted(counts.items()):
        print(f"  {status:<12} {count}")

    if suspicious:
        print(f"\n{len(suspicious)} match(es) need a human eye:")
        for record in suspicious:
            print(f"  {record['track_id']:<28} searched {record['searched_title']!r}")
            print(f"  {'':<28} got      {record.get('genius_title')!r} "
                  f"by {record.get('genius_artist')!r}")
            print(f"  {'':<28} {record.get('genius_url')}")
    else:
        print("\nEvery successful match agrees with the track title. "
              "Spot-check a few anyway.")

    ok: list[dict[str, Any]] = [r for r in records if r["status"] == "ok" and r["lyrics_raw"]]
    if ok:
        words: list[int] = [lyric_stats(clean_lyrics(r["lyrics_raw"]))["lyric_word_count"]
                            for r in ok]
        shortest = min(zip(words, [r["track_id"] for r in ok]))
        print(f"\nword counts: min {min(words)}, median {sorted(words)[len(words)//2]}, "
              f"max {max(words)}")
        print(f"shortest is {shortest[1]} at {shortest[0]} words — if that looks too "
              f"small, the cleaner probably ate something it shouldn't have")
    print("\nNext: python scripts/build_dataset.py to join these counts into tracks.csv")


if __name__ == "__main__":
    main()
