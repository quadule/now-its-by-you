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
