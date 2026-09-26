import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import align as A  # noqa: E402  (tools/align.py, dev-only)


def line(n: int = 6, step: float = 0.5) -> list:
    """A line of n one-syllable words, a note every step seconds."""
    return [SimpleNamespace(start=10 + i * step, dur=0.9 * step, line_end=i == n - 1, word=f"w{i}", word_len=1,
                            syllable=f"w{i}") for i in range(n)]


def test_without_mfa_the_extractor_goes_on_alone(monkeypatch):
    monkeypatch.setenv("MFA", "off")
    assert A.executable() is None and not A.available() and A.fingerprint() is None
    assert A.aligned(Path("no-such-take.wav"), None) is None


def test_a_collapse_is_not_plausible():
    notes = line()
    vowel = np.array([n.start + 0.02 for n in notes])
    end = vowel + 0.35
    assert A.plausible(notes, vowel, end).all()
    vowel[2:5] = vowel[2] + np.array([0.0, 0.03, 0.06])  # three words squeezed into a few frames
    end[2:5] = vowel[2:5] + 0.03
    ok = A.plausible(notes, vowel, end)
    assert ok[0] and not ok[2:5].any()


def test_mfa_leads_where_it_is_plausible_or_agrees():
    notes = line()
    ours = np.array([n.start for n in notes]) + 0.05
    heard = {"vowel_start": [n.start for n in notes], "vowel_end": [n.start + 0.4 for n in notes]}
    heard["vowel_start"][3] = None  # a vowel MFA didn't find
    heard["vowel_start"][5] = notes[5].start + 1.0  # lost, far from ours, past the guide
    onset, use = A.combine(ours, heard, notes, ["vowel", "stop", "nasal+v", "vowel", "glide+v", "vowel"])
    assert use.tolist() == [True, True, True, False, True, False]
    assert onset[3] == ours[3] and onset[5] == ours[5]
    assert np.isclose(onset[2], notes[2].start - A.MFA_BIAS["nasal+v"])


def test_kept_alignments_follow_the_take_not_the_extractor(tmp_path, monkeypatch):
    monkeypatch.setenv("MFA", "off")
    wav = tmp_path / "take.wav"
    wav.write_bytes(b"RIFF-take")
    notes = line()
    g = SimpleNamespace(notes=notes, lines=[list(range(len(notes)))], digest="abc", lexicon={})
    k = A.key(wav, g, 0.0)
    assert A.key(wav, g, 0.0) == k
    assert A.key(wav, SimpleNamespace(**{**vars(g), "digest": "def"}), 0.0) != k  # another guide
    assert A.key(wav, g, 0.3) != k  # cut elsewhere
    wav.write_bytes(b"RIFF-another-take")
    assert A.key(wav, g, 0.0) != k
    assert set(k) == {"audio", "guide", "words", "lag", *A.settings()}  # nothing of the singer or the extractor


def test_runs_queue_on_one_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("MFA_LOCK", str(tmp_path / "mfa" / ".lock"))
    with A.lock():
        assert (tmp_path / "mfa" / ".lock").exists()
    with A.lock():  # released, so it can be taken again
        pass
