"""A MIDI file changed as a musician would change it in a sequencer, and saved again (tests of notes in)."""

from songbird import midi


def rewrite(data: bytes, change=None, tpq: int | None = None, offs_as_ons: bool = False, retext=None) -> bytes:
    """A MIDI file saved again, as a sequencer might: its tracks' notes changed by change(name, notes) (notes as
    [on, off, channel, key, velocity] in ticks), at another division, its note-offs as note-ons at velocity 0;
    its texts changed by retext(name, texts) (texts as [tick, kind, text], the lyrics kind 0x05)."""
    read, parsed = midi.read(data), midi.parse(data)
    scale = (tpq or midi.TPQ) / midi.TPQ
    tracks = []
    for raw, track in zip(read["tracks"], parsed["tracks"]):
        texts = [[t, e["meta"], bytes(e["data"]).decode("utf-8", "replace")] for t, e in raw if "meta" in e
                 and 0x01 <= e["meta"] <= 0x07]
        if retext is not None:
            texts = retext(track["name"], texts)
        events = [(round(t * scale), 0, midi.meta(e["meta"], bytes(e["data"]))) for t, e in raw if "meta" in e
                  and e["meta"] != 0x2F and not 0x01 <= e["meta"] <= 0x07]
        events += [(round(t * scale), 0, midi.meta(kind, text.encode("utf-8"))) for t, kind, text in texts]
        events += [(round(t * scale), 1, bytes([e["status"] | e["channel"], *e["args"]])) for t, e in raw
                   if e.get("status") == 0xC0]
        notes = [list(n) for n in track["notes"]]
        if change is not None:
            notes = change(track["name"], notes)
        for on, off, channel, key, vel in notes:
            events.append((round(on * scale), 3, bytes([0x90 | channel, key, vel])))
            events.append((round(off * scale), 2, bytes([0x90 | channel, key, 0]) if offs_as_ons
                           else bytes([0x80 | channel, key, 0])))
        tracks.append(events)
    out = midi.write(tracks)
    return out[:12] + (tpq or midi.TPQ).to_bytes(2, "big") + out[14:]
