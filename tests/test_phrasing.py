from songbird import phrasing as P


def test_gestures_are_rounded_and_bounded():
    g = P.reduce(P.Gesture(early=0.51, level=-3.26, scoop=-231.0, vibrato=33.4))
    assert g == P.Gesture(early=0.25, level=-3.5, scoop=-150.0, vibrato=33.0)


def test_average_skips_what_a_sighting_did_not_measure():
    nan = float("nan")
    g = P.average([P.Gesture(early=0.1, scoop=-40.0), P.Gesture(early=nan, scoop=-20.0)])
    assert abs(g.early - 0.1042) < 1e-3 and g.scoop == -30.0
    assert P.average([P.Gesture(early=nan)]).early == 0.0


def test_json_round_trip():
    ph = {"r1": (P.Gesture(early=0.0625, fall=-60.0), P.Gesture(vibrato=25.0))}
    assert P.from_json(P.to_json(ph, source="test")) == ph


def test_blend_counts_each_singer_once():
    a = {"r1": (P.Gesture(early=0.125, fall=-60.0), P.Gesture(vibrato=30.0))}
    b = {"r1": (P.Gesture(early=0.0625, fall=-20.0), P.Gesture(vibrato=-1.0)), "v1": (P.Gesture(level=2.0),)}
    both = P.blend([a, b])
    assert both["r1"][0] == P.reduce(P.Gesture(early=0.09375, fall=-40.0))
    assert both["r1"][1].vibrato == -1.0  # a tie leaves vibrato to the singer
    assert both["v1"] == (P.Gesture(level=2.0),)


def test_unmeasured_vibrato_does_not_vote():
    nan = float("nan")
    assert P.average([P.Gesture(vibrato=24.0), P.Gesture(vibrato=nan), P.Gesture(vibrato=nan)]).vibrato == 24.0


def test_tune_rounds_and_bounds_like_the_rest():
    assert P.reduce(P.Gesture(tune=-73.0)).tune == -50.0
    assert P.reduce(P.Gesture(tune=13.1)).tune == 14.0
    assert P.from_json({"fields": ["early", "hold"], "phrases": {"r1": [[0.0625, 1.0]]}})["r1"][0].tune == 0.0  # old files
