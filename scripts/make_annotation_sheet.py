"""
Generates the by-ear key-change annotation sheets from the spine.

Run after scripts/build_dataset.py, from the repo root:

    python scripts/make_annotation_sheet.py

Writes two files under data/annotations/ (both committed, both hand-edited
from here on):

  key_changes.csv           the event log — starts empty, one row per key change
  key_change_coverage.csv   one row per track, pre-filled, to tick off as you go

Generated rather than hand-built so track_id is never retyped: a typo there
produces a row that joins to nothing and silently drops out of every count.

Safe to re-run. Existing rows are never rewritten or reordered — a later run
only appends coverage rows for tracks that have appeared in the spine since,
and reports any coverage row whose track has disappeared from it. The event log
is never touched once it exists.

Why the event log starts empty rather than seeded with a blank row per track:
a seeded row cannot be told apart from a real one that has not been filled in,
so "not listened to yet" and "listened, no key changes" would collapse into the
same state. Coverage answers that question instead, which is why it is a
separate file. See src/key_changes.py.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.key_changes import COVERAGE_COLUMNS, EVENT_COLUMNS  # noqa: E402

TRACKS_CSV: Path = REPO_ROOT / "data" / "processed" / "tracks.csv"
EVENTS_CSV: Path = REPO_ROOT / "data" / "annotations" / "key_changes.csv"
COVERAGE_CSV: Path = REPO_ROOT / "data" / "annotations" / "key_change_coverage.csv"


def write_event_log() -> None:
    """Create the empty event log. Never overwrites one that already exists."""
    if EVENTS_CSV.exists():
        existing: int = len(pd.read_csv(EVENTS_CSV, dtype=str))
        print(f"  {EVENTS_CSV.name:<26} exists, {existing} event(s) — left alone")
        return
    EVENTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=EVENT_COLUMNS).to_csv(EVENTS_CSV, index=False)
    print(f"  {EVENTS_CSV.name:<26} created (header only)")


def write_coverage(tracks: pd.DataFrame) -> None:
    """Create or extend the per-track coverage sheet, preserving hand edits."""
    skeleton: pd.DataFrame = tracks[["track_id", "album", "track_title"]].copy()
    skeleton["annotated"] = ""
    skeleton["listened_at"] = ""
    skeleton["notes"] = ""

    if not COVERAGE_CSV.exists():
        COVERAGE_CSV.parent.mkdir(parents=True, exist_ok=True)
        skeleton[COVERAGE_COLUMNS].to_csv(COVERAGE_CSV, index=False)
        print(f"  {COVERAGE_CSV.name:<26} created ({len(skeleton)} rows)")
        return

    existing: pd.DataFrame = pd.read_csv(COVERAGE_CSV, dtype=str).fillna("")
    known: set[str] = set(existing["track_id"])
    added: pd.DataFrame = skeleton[~skeleton["track_id"].isin(known)]
    # Orphans are reported, never deleted. A coverage row whose track vanished
    # usually means the spine changed under the annotation, and throwing away
    # the listening record is not this script's call to make.
    orphaned: list[str] = sorted(known - set(skeleton["track_id"]))

    if len(added):
        combined: pd.DataFrame = pd.concat([existing, added[COVERAGE_COLUMNS]])
        combined.to_csv(COVERAGE_CSV, index=False)
        print(f"  {COVERAGE_CSV.name:<26} +{len(added)} new track(s), "
              f"{len(combined)} rows total")
    else:
        print(f"  {COVERAGE_CSV.name:<26} exists, {len(existing)} rows — up to date")

    if orphaned:
        print(f"WARN  {len(orphaned)} coverage row(s) are no longer in the spine "
              f"(left in place, not deleted): {orphaned[:5]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    if not TRACKS_CSV.exists():
        raise SystemExit(
            f"ERROR: {TRACKS_CSV.relative_to(REPO_ROOT)} not found — "
            f"run scripts/build_dataset.py first."
        )

    tracks: pd.DataFrame = pd.read_csv(TRACKS_CSV, dtype=str)
    print(f"{len(tracks)} tracks in the spine")
    write_event_log()
    write_coverage(tracks)

    print(
        "\nHow to annotate:\n"
        f"  1. Listen to a track. Log every key change as a row in "
        f"{EVENTS_CSV.name}:\n"
        "       track_id, event_no (1,2,3... within that track), timestamp_mm_ss\n"
        "       (3:47), from_key/to_key (C, F#, Bb, Am, C#m), semitones (up is\n"
        "       positive), type (truck_driver|modulation|borrowed|ambiguous),\n"
        "       confidence (1-3), notes\n"
        f"  2. Mark the track in {COVERAGE_CSV.name}: annotated=yes plus the date.\n"
        "     Do this even when there were NO key changes — that is a finding,\n"
        "     and it is the only thing separating it from a track you skipped.\n"
        "  3. Re-run scripts/build_dataset.py. It checks every value, cross-checks\n"
        "     semitones against the two key names, and writes\n"
        "     data/processed/key_change_events.csv."
    )


if __name__ == "__main__":
    main()
