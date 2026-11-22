"""A version's own title (the edit `name`) names what the studio makes of it: the whole song's render is made again
under it, so its record and tags carry it, and the files are called by it."""
from pathlib import Path

from songbird import studio as S

ROOT = Path(__file__).resolve().parents[1]


def test_a_title_names_the_whole_songs_render_and_its_files(tmp_path):
    st = S.Studio(None, str(ROOT / "songs" / "h-now-its-by-you.json"), "none", home=tmp_path)
    plain, named = st.version({}), st.version({"name": "By Everyone"})
    assert st.key(plain, None) != st.key(named, None)  # (a render made before renaming isn't the renamed one)
    assert st.key(plain, 0) == st.key(named, 0)  # a section sounds the same under any title
    assert st.export_name(named, ".mid").startswith("by-everyone.")
    assert st.export_name(plain, ".mid").startswith("now-its-by-you.")
    record = {"id": "abcdef123456", "rendered_at": "2026-11-21T12:00:00Z"}
    assert st.recording_name(record | {"name": "By Everyone"}) == "by-everyone.2026-11-21.abcdef"
    assert st.recording_name(record) == "now-its-by-you.2026-11-21.abcdef"
