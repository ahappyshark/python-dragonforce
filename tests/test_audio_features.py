"""
Tests for the deferred audio-features schema.

These matter more than they look, because nobody will run this sheet in anger
for months. By the time the first real tempo is typed in, the only thing
standing between a bad value and the analysis is this validator — and nobody
will remember what the rules were supposed to be.

The empty and partially-filled cases get the most attention here: those are the
states the file will actually spend its life in.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.audio_features import validate_audio_features

SPINE: set[str] = {"inhuman-rampage-1-01", "inhuman-rampage-1-02"}


def feature(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "track_id": "inhuman-rampage-1-01",
        "tempo_bpm": "200",
        "key": "E",
        "mode": "minor",
        "time_signature": "4/4",
        "source": "manual_tap",
        "notes": "",
    }
    row.update(overrides)
    return row


# --- the states this file actually lives in -------------------------------

def test_empty_sheet_is_valid():
    assert validate_audio_features([], SPINE) == ([], [])


def test_a_complete_row_passes():
    assert validate_audio_features([feature()], SPINE) == ([], [])


@pytest.mark.parametrize("blank_field", ["tempo_bpm", "key", "mode", "time_signature"])
def test_partially_filled_rows_are_valid(blank_field):
    # Columns get filled a sitting at a time — all the tempos, then keys later.
    # A row mid-way through that is normal, not an error.
    errors, warnings = validate_audio_features([feature(**{blank_field: ""})], SPINE)
    assert errors == []
    assert warnings == []


def test_a_row_with_only_a_track_id_is_valid_and_silent():
    errors, warnings = validate_audio_features(
        [feature(tempo_bpm="", key="", mode="", time_signature="", source="")], SPINE,
    )
    assert errors == []
    assert warnings == []


# --- errors ---------------------------------------------------------------

def test_unknown_track_id_is_an_error():
    errors, _ = validate_audio_features([feature(track_id="nope-9-99")], SPINE)
    assert any("not in the spine" in e for e in errors)


def test_duplicate_track_id_is_an_error():
    errors, _ = validate_audio_features([feature(), feature()], SPINE)
    assert any("duplicate row" in e for e in errors)


@pytest.mark.parametrize("field,value,fragment", [
    ("tempo_bpm", "fast", "not a number"),
    ("tempo_bpm", "2000", "outside"),
    ("tempo_bpm", "3", "outside"),
    ("key", "Am", "tonic only"),        # mode has its own column
    ("key", "H", "tonic only"),
    ("mode", "dorian", "is not one of"),
    ("time_signature", "4-4", "look like 4/4"),
    ("source", "spotify", "is not one of"),
])
def test_bad_values_are_errors(field, value, fragment):
    errors, _ = validate_audio_features([feature(**{field: value})], SPINE)
    assert any(fragment in e for e in errors), errors


def test_mode_is_case_insensitive():
    assert validate_audio_features([feature(mode="Major")], SPINE) == ([], [])


# --- warnings -------------------------------------------------------------

def test_measurements_without_a_source_warn():
    # A tempo whose provenance is unknown cannot be pooled with one that has a
    # known method, so it must not pass silently.
    errors, warnings = validate_audio_features([feature(source="")], SPINE)
    assert errors == []
    assert any("no source" in w for w in warnings)
