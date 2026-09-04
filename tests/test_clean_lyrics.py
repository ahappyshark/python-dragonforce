"""
Tests for the Genius lyric scrubber.

Every fixture below uses INVENTED lyric text. Real lyrics in a public repo
would be redistribution, which is exactly what the project's copyright note
rules out — and a fake song exercises the parser just as well.

The cleaner is the one function where a silent regression corrupts every word
count downstream without changing a single API response, so it gets tests and
the rest of the pipeline gets a validation gate.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.genius_client import clean_lyrics, lyric_stats, strip_section_headers  # noqa: E402

BODY: str = "[Verse 1]\nRiding on a moonbeam\nInto the frozen sun\n\n[Chorus]\nWe ride tonight"


def test_strips_contributor_header() -> None:
    raw = f"37 ContributorsTranslationsEspañolPortuguêsFrozen Sun Lyrics{BODY}537Embed"
    assert clean_lyrics(raw) == BODY


def test_strips_header_without_contributor_count() -> None:
    raw = f"Frozen Sun Lyrics{BODY}Embed"
    assert clean_lyrics(raw) == BODY


def test_strips_view_count_suffixes() -> None:
    for suffix in ("Embed", "12Embed", "537Embed", "1.2KEmbed", "3.4MEmbed"):
        assert clean_lyrics(f"Frozen Sun Lyrics{BODY}{suffix}") == BODY


def test_removes_injected_promo_text() -> None:
    raw = ("12 ContributorsFrozen Sun Lyrics[Verse 1]\nRiding on a moonbeam\n"
           "You might also like\nInto the frozen sun\n1KEmbed")
    cleaned = clean_lyrics(raw)
    assert "You might also like" not in cleaned
    assert "Riding on a moonbeam" in cleaned and "Into the frozen sun" in cleaned


def test_removes_concert_ad() -> None:
    raw = ("5 ContributorsFrozen Sun Lyrics[Verse 1]\nRiding on a moonbeam\n"
           "See DragonForce LiveGet tickets as low as $42\nInto the frozen sun\nEmbed")
    cleaned = clean_lyrics(raw)
    assert "tickets" not in cleaned
    assert "Into the frozen sun" in cleaned


def test_keeps_section_headers_but_strip_removes_them() -> None:
    cleaned = clean_lyrics(f"Frozen Sun Lyrics{BODY}Embed")
    assert "[Chorus]" in cleaned
    stripped = strip_section_headers(cleaned)
    assert "[Chorus]" not in stripped and "We ride tonight" in stripped


def test_does_not_eat_lyric_lines_containing_the_word_lyrics() -> None:
    """The header regex is anchored to the start; a later 'Lyrics' must survive."""
    body = "[Verse 1]\nI scream the lyrics to the sky\nAnd the chorus answers"
    raw = f"9 ContributorsScream Lyrics{body}404Embed"
    cleaned = clean_lyrics(raw)
    assert "I scream the lyrics to the sky" in cleaned
    assert cleaned.startswith("[Verse 1]")


def test_does_not_eat_the_word_embed_mid_song() -> None:
    body = "[Verse 1]\nEmbed the blade within the stone\nAnd raise it high"
    cleaned = clean_lyrics(f"Stone Lyrics{body}88Embed")
    assert "Embed the blade within the stone" in cleaned
    assert not cleaned.endswith("Embed")


@pytest.mark.parametrize("value", ["", None])
def test_handles_empty_input(value: str | None) -> None:
    assert clean_lyrics(value) == ""


def test_lyric_stats_ignores_section_headers_and_counts_words() -> None:
    stats = lyric_stats(clean_lyrics(f"Frozen Sun Lyrics{BODY}Embed"))
    # "Riding on a moonbeam / Into the frozen sun / We ride tonight" = 4+4+3 words,
    # all distinct ("Riding" and "ride" differ). [Verse 1] and [Chorus] must not
    # count, and the digit in "[Verse 1]" must not survive as a word either.
    assert stats["lyric_word_count"] == 11
    assert stats["lyric_unique_words"] == 11
    assert stats["lyric_line_count"] == 3


def test_apostrophes_are_kept_inside_words() -> None:
    stats = lyric_stats("Don't stop believin'")
    assert stats["lyric_word_count"] == 3
