"""A day as a person reads it: the American way, everywhere (the artist, 2026-09-30)."""
import re
from pathlib import Path

from songbird import dates

ROOT = Path(__file__).resolve().parents[1]


def test_a_day_reads_the_american_way():
    assert dates.us_date("2026-09-30") == "September 30, 2026"
    assert dates.long_date("2026-09-30") == "Wednesday, September 30, 2026"
    assert dates.long_date("2026-08-01") == "Saturday, August 1, 2026"
    assert dates.us_date("2026-09-30T12:00:00+00:00") == "September 30, 2026"  # a record's timestamp


def test_no_page_asks_the_viewers_locale_for_a_date():
    """A date on a page is en-US, said so: the viewer's own locale would make it 30 September for some."""
    pages = [*sorted((ROOT / "songbird" / "studio").rglob("*.js")), *sorted((ROOT / "web" / "sing" / "page").glob("*.js"))]
    for path in pages:
        text = path.read_text()
        assert not re.search(r"toLocale(Date)?String\((undefined)?\s*[,)]", text), path
        assert "en-GB" not in text, path
