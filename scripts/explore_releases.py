"""
Lists every pressing of every DragonForce studio album, so you can pick one
canonical release per album by looking at real options instead of guessing.

MusicBrainz splits albums into two entities: a *release group* (the abstract
album, no tracklist) and a *release* (one specific pressing, which does have a
tracklist). The notebook currently has release groups only, which is why it
can't pull tracks yet. This script closes that gap.

Run it from the repo root:

    python scripts/explore_releases.py

First run makes 9 API calls at ~1/sec, so give it about 10 seconds. Every
response is cached to data/raw/, so later runs are instant and work offline.
Pass --refresh to force fresh fetches.

Output:
  * a compact table per album, printed to the terminal
  * data/processed/release_candidates.csv with every pressing, for sorting
    and filtering in a spreadsheet

Nothing here decides anything for you. The "suggested" marker is a starting
point based on a crude heuristic (official + most common track count +
earliest); the actual choice is a judgement call worth making deliberately,
and it belongs in data/albums.json with a note explaining why.
"""

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.musicbrainz_client import (  # noqa: E402
    get_release_groups,
    get_releases_for_group,
    summarize_release,
)

OUTPUT_CSV: Path = REPO_ROOT / "data" / "processed" / "release_candidates.csv"


def studio_release_groups(refresh: bool = False) -> list[dict[str, Any]]:
    """Return studio albums only, oldest first.

    Live albums, compilations and remix albums all carry a non-empty
    "secondary-types" list, so an empty list is a reliable studio-album test
    for this artist. Verified against all 13 of DragonForce's release groups.
    """
    groups: list[dict[str, Any]] = get_release_groups(refresh=refresh)
    studio: list[dict[str, Any]] = [
        g for g in groups if not g.get("secondary-types")
    ]
    return sorted(studio, key=lambda g: g.get("first-release-date") or "")


def score_release(row: dict[str, Any], modal_tracks: int) -> tuple:
    """Sort key that floats the most plausible canonical pressing to the top.

    Deliberately crude. It prefers an official release, then one whose track
    count matches the most common count across pressings (a proxy for "standard
    edition, no bonus tracks"), then a plain CD, then the earliest date. Ties
    and near-misses are common, which is the whole reason a human picks.
    """
    return (
        0 if row["status"] == "Official" else 1,
        0 if row["tracks"] == modal_tracks else 1,
        0 if row["format"] == "CD" else 1,
        row["date"] or "9999",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-fetch from the API instead of reading data/raw/ cache.",
    )
    args = parser.parse_args()

    albums: list[dict[str, Any]] = studio_release_groups(refresh=args.refresh)
    print(f"{len(albums)} studio albums\n")

    all_rows: list[dict[str, Any]] = []

    for album in albums:
        title: str = album.get("title", "?")
        year: str = (album.get("first-release-date") or "????")[:4]
        releases: list[dict[str, Any]] = get_releases_for_group(
            album["id"], refresh=args.refresh
        )
        rows: list[dict[str, Any]] = [summarize_release(r) for r in releases]

        # The most common track count across pressings is a decent guess at the
        # standard edition. Bonus-track and deluxe editions are the outliers.
        counts: Counter = Counter(r["tracks"] for r in rows if r["tracks"])
        modal_tracks: int = counts.most_common(1)[0][0] if counts else 0

        rows.sort(key=lambda r: score_release(r, modal_tracks))

        plural: str = "pressing" if len(rows) == 1 else "pressings"
        print(f"=== {title} ({year}) — {len(rows)} {plural}, "
              f"most common track count: {modal_tracks}")
        if not rows:
            print("    (none returned — check the release group MBID)\n")
            continue

        spread: list[int] = sorted(counts)
        if len(spread) > 1:
            print(f"    track counts seen: {spread}  <- differing editions, "
                  f"your pick changes the dataset")

        for i, r in enumerate(rows[:6]):
            mark: str = "  suggested >" if i == 0 else "             "
            note: str = f"  [{r['disambiguation']}]" if r["disambiguation"] else ""
            print(f"{mark} {r['date'] or '????-??-??':<10} {r['country'] or '--':<3} "
                  f"{r['status'] or '?':<9} {r['format']:<14} "
                  f"{r['tracks']:>3}tk {r['release_mbid']}{note}")
        if len(rows) > 6:
            print(f"              ... and {len(rows) - 6} more (see the CSV)")
        print()

        for r in rows:
            all_rows.append({"album": title, "album_year": year,
                             "release_group_mbid": album["id"], **r})

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"Wrote {len(all_rows)} rows to {OUTPUT_CSV.relative_to(REPO_ROOT)}")
    print("\nNext: put your chosen release_mbid for each album into "
          "data/albums.json, with a note saying why.")


if __name__ == "__main__":
    main()
