"""
Builds the spine table: one row per track across all nine studio albums.

Reads the canonical release chosen for each album in data/albums.json, fetches
that release's tracklist from MusicBrainz (cached, so only the first run costs
network), validates the result, and writes data/processed/tracks.csv.

Run from the repo root:

    python scripts/build_dataset.py

First run makes 9 API calls at ~1/sec. Later runs read data/raw/ and are
instant. Pass --refresh to force fresh fetches.

This is a script and not a notebook on purpose. A notebook that builds your
dataset is how you end up unable to reproduce your own numbers, because one
time cell 12 ran before cell 8. Explore in notebooks; build in scripts.

Nothing is written unless every check passes. A half-written tracks.csv that
looks plausible is worse than no file at all, because you'd analyse it.
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.musicbrainz_client import get_release_tracks  # noqa: E402

ALBUMS_JSON: Path = REPO_ROOT / "data" / "albums.json"
TRACKS_CSV: Path = REPO_ROOT / "data" / "processed" / "tracks.csv"
FLAGS_CSV: Path = REPO_ROOT / "data" / "annotations" / "track_flags.csv"

# Hand-annotated columns the spine carries but MusicBrainz cannot supply.
FLAG_COLUMNS: list[str] = ["is_bonus_track", "is_cover", "is_instrumental"]

EARLIEST_YEAR: int = 2003
LATEST_YEAR: int = 2030

# Apostrophes are deleted rather than turned into separators. Sources disagree
# about which character to use — MusicBrainz's canonical recording titles favour
# the typographic U+2019 while this pressing's track titles use ASCII — and the
# two must not normalize differently. Dropping the character entirely maps both
# "Tomorrow's Kings" and "Tomorrow’s Kings" onto "tomorrows kings".
APOSTROPHES: str = "'\u2018\u2019\u02bc\u00b4`"


def _strip_apostrophes(text: str) -> str:
    """Remove apostrophe-like characters so they never become word separators."""
    return "".join(c for c in text if c not in APOSTROPHES)


def slugify(text: str) -> str:
    """Make a filesystem- and URL-safe ASCII slug.

    NFKD decomposition splits accented characters into a base letter plus a
    combining mark, so the ASCII encode step drops the mark and keeps the
    letter: "Frédéric" survives as "frederic" rather than "frdric". It also
    disposes of the U+2026 ellipsis already present in this discography.
    """
    decomposed: str = unicodedata.normalize("NFKD", _strip_apostrophes(text))
    ascii_only: str = decomposed.encode("ascii", "ignore").decode("ascii")
    slug: str = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")
    return slug or "untitled"


def make_title_key(text: str) -> str:
    """Normalize a track title into a fuzzy join key for sources without MBIDs.

    Genius has never heard of a recording MBID, so matching there falls back to
    the title, which differs across sources in capitalization, punctuation and
    parenthetical suffixes. This strips all three.

    Deliberately lossy: dropping "(alternate lyrics)" is what lets a Genius hit
    match, but it also means two tracks on the same album can collapse to one
    key. build_dataset() reports those collisions rather than hiding them,
    because they are exactly where automated lyric matching will pick wrong.
    """
    decomposed: str = unicodedata.normalize("NFKD", _strip_apostrophes(text))
    ascii_only: str = decomposed.encode("ascii", "ignore").decode("ascii")
    without_parens: str = re.sub(r"[\(\[][^)\]]*[\)\]]", " ", ascii_only)
    cleaned: str = re.sub(r"[^a-z0-9]+", " ", without_parens.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def build_rows(album: dict[str, Any], refresh: bool = False) -> list[dict[str, Any]]:
    """Turn one album's chosen release into tidy per-track rows."""
    tracks: list[dict[str, Any]] = get_release_tracks(album["release_mbid"], refresh=refresh)
    album_slug: str = slugify(album["title"])
    rows: list[dict[str, Any]] = []

    for track in tracks:
        recording: dict[str, Any] = track.get("recording") or {}
        title: str = track.get("title") or recording.get("title") or ""
        disc: int = int(track.get("_disc_position") or 1)
        position: int = int(track.get("position") or 0)

        # The track-level length is the one for this pressing; recording length
        # is the same performance as it appears anywhere. Prefer the pressing's.
        length: Any = track.get("length") or recording.get("length")

        rows.append({
            "track_id": f"{album_slug}-{disc}-{position:02d}",
            "recording_mbid": recording.get("id") or "",
            "album": album["title"],
            "album_mbid": album["release_group_mbid"],
            "release_mbid": album["release_mbid"],
            "release_year": album["year"],
            "disc_no": disc,
            "disc_format": track.get("_disc_format") or "",
            "track_no": position,
            "track_number_printed": track.get("number") or str(position),
            "track_title": title,
            "title_key": make_title_key(title),
            "length_ms": int(length) if length else None,
        })
    return rows


def validate(df: pd.DataFrame, albums: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Check the built table. Returns (errors, warnings).

    Errors mean the data is wrong and nothing should be written. Warnings mean
    something needs a human eye but is not necessarily a defect.
    """
    errors: list[str] = []
    warnings: list[str] = []

    for album in albums:
        rows: pd.DataFrame = df[df["album"] == album["title"]]
        expected: Any = album.get("expected_track_count")
        if expected is None:
            warnings.append(f"{album['title']}: no expected_track_count to check against")
        elif len(rows) != expected:
            errors.append(
                f"{album['title']}: albums.json expects {expected} tracks, "
                f"release {album['release_mbid']} returned {len(rows)}"
            )

    dupe_ids: list[str] = df.loc[df["track_id"].duplicated(), "track_id"].tolist()
    if dupe_ids:
        errors.append(f"duplicate track_id: {sorted(set(dupe_ids))}")

    missing_titles: int = int((df["track_title"].fillna("").str.strip() == "").sum())
    if missing_titles:
        errors.append(f"{missing_titles} track(s) have an empty title")

    bad_years: list[Any] = sorted(
        {y for y in df["release_year"] if not EARLIEST_YEAR <= int(y) <= LATEST_YEAR}
    )
    if bad_years:
        errors.append(f"release_year outside {EARLIEST_YEAR}-{LATEST_YEAR}: {bad_years}")

    # A recording MBID is the join key, so a blank one silently drops that track
    # out of every later join.
    missing_mbid: pd.DataFrame = df[df["recording_mbid"] == ""]
    if len(missing_mbid):
        errors.append(
            f"{len(missing_mbid)} track(s) have no recording_mbid: "
            f"{missing_mbid['track_id'].tolist()[:5]}"
        )

    dupe_recordings: pd.DataFrame = df[df.duplicated("recording_mbid", keep=False)]
    if len(dupe_recordings):
        pairs: list[str] = [
            f"{r.track_id}({r.recording_mbid[:8]})" for r in dupe_recordings.itertuples()
        ]
        warnings.append(
            f"{len(dupe_recordings)} tracks share a recording_mbid with another "
            f"track — the same recording appearing twice, or a data error: {pairs}"
        )

    for album_title, group in df.groupby("album"):
        collisions = group[group.duplicated("title_key", keep=False)]
        # Grouped per colliding key: two separate two-way collisions on one
        # album are a different problem from one four-way collision, and
        # reporting them as a single list of four titles hides which is which.
        for key, matching in collisions.groupby("title_key"):
            titles: list[str] = matching["track_title"].tolist()
            warnings.append(
                f"{album_title}: {len(matching)} tracks normalize to "
                f"title_key {key!r} -> {titles} — lyric matching by title cannot "
                f"tell these apart, so they need a Genius override entry"
            )

    return errors, warnings


def write_flag_skeleton(df: pd.DataFrame) -> None:
    """Create the hand-annotation sheet, pre-filled with keys, if absent.

    Generated rather than hand-built so track_id is never retyped: a typo there
    produces a row that silently joins to nothing.
    """
    if FLAGS_CSV.exists():
        return
    skeleton: pd.DataFrame = df[["track_id", "album", "track_title"]].copy()
    for column in FLAG_COLUMNS:
        skeleton[column] = ""
    skeleton["notes"] = ""
    FLAGS_CSV.parent.mkdir(parents=True, exist_ok=True)
    skeleton.to_csv(FLAGS_CSV, index=False)
    print(f"Created {FLAGS_CSV.relative_to(REPO_ROOT)} "
          f"({len(skeleton)} rows) — fill in the flag columns by hand.")


def merge_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Left-join hand-entered flags, tolerating an absent or empty sheet.

    The join runs whether or not the sheet has been filled in, so annotating is
    only ever data entry — no code change is needed to light these columns up.
    """
    if not FLAGS_CSV.exists():
        for column in FLAG_COLUMNS:
            df[column] = pd.NA
        return df

    flags: pd.DataFrame = pd.read_csv(FLAGS_CSV, dtype=str).fillna("")
    unknown: set[str] = set(flags["track_id"]) - set(df["track_id"])
    if unknown:
        # Hand-typed track_ids that match nothing are the classic silent
        # annotation bug: the row exists, the join drops it, the count looks off
        # by one and nobody knows why.
        raise SystemExit(
            f"ERROR: {FLAGS_CSV.name} has {len(unknown)} track_id(s) not in the "
            f"spine: {sorted(unknown)[:5]}"
        )
    keep: list[str] = ["track_id"] + [c for c in FLAG_COLUMNS if c in flags.columns]
    return df.merge(flags[keep], on="track_id", how="left")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true",
                        help="Re-fetch from the API instead of reading data/raw/ cache.")
    args = parser.parse_args()

    albums: list[dict[str, Any]] = json.loads(ALBUMS_JSON.read_text(encoding="utf-8"))["albums"]

    unpinned: list[str] = [a["title"] for a in albums if not a.get("release_mbid")]
    if unpinned:
        raise SystemExit(
            f"ERROR: no release_mbid chosen for: {unpinned}\n"
            f"Run scripts/explore_releases.py and record a pick in data/albums.json."
        )

    rows: list[dict[str, Any]] = []
    for album in albums:
        album_rows: list[dict[str, Any]] = build_rows(album, refresh=args.refresh)
        print(f"  {album['title']:<24} {len(album_rows):>3} tracks")
        rows.extend(album_rows)

    df: pd.DataFrame = pd.DataFrame(rows).sort_values(
        ["release_year", "album", "disc_no", "track_no"]
    ).reset_index(drop=True)

    errors, warnings = validate(df, albums)
    print()
    for warning in warnings:
        print(f"WARN  {warning}")
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        raise SystemExit(
            f"\n{len(errors)} validation error(s). Nothing written — fix these first."
        )

    write_flag_skeleton(df)
    df = merge_flags(df)

    TRACKS_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(TRACKS_CSV, index=False)
    print(f"\nWrote {len(df)} tracks across {df['album'].nunique()} albums "
          f"to {TRACKS_CSV.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
