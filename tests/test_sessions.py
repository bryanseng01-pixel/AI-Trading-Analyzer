import pandas as pd

from sessions import detect_session_levels


def test_london_session_high_and_low_are_calculated_from_session_wicks():
    index = pd.DatetimeIndex(
        [
            "2026-08-05 03:00",
            "2026-08-05 05:00",
            "2026-08-05 08:25",
            "2026-08-05 08:35",
            "2026-08-05 08:40",
            "2026-08-05 10:00",
        ],
        tz="America/New_York",
    )
    data = pd.DataFrame(
        [
            (100, 102, 99, 101, 10),
            (101, 105, 98, 103, 10),
            (103, 104, 100, 102, 10),
            (102, 106, 100, 104, 10),
            (104, 104, 97, 100, 10),
            (100, 103, 99, 102, 10),
        ],
        columns=["Open", "High", "Low", "Close", "Volume"],
        index=index,
        dtype=float,
    )

    london = detect_session_levels(data)["London"]

    assert london["high"] == 105.0
    assert london["low"] == 98.0


def test_session_liquidity_sweeps_use_wicks_not_closes():
    index = pd.DatetimeIndex(
        [
            "2026-08-05 03:00",
            "2026-08-05 05:00",
            "2026-08-05 08:25",
            "2026-08-05 08:35",
            "2026-08-05 08:40",
            "2026-08-05 10:00",
        ],
        tz="America/New_York",
    )
    data = pd.DataFrame(
        [
            (100, 102, 99, 101, 10),
            (101, 105, 98, 103, 10),
            (103, 104, 100, 102, 10),
            (102, 106, 100, 104, 10),  # High wick sweeps 105; close does not.
            (104, 104, 97, 100, 10),   # Low wick sweeps 98; close does not.
            (100, 103, 99, 102, 10),
        ],
        columns=["Open", "High", "Low", "Close", "Volume"],
        index=index,
        dtype=float,
    )

    london = detect_session_levels(data)["London"]

    assert london["high_swept"] is True
    assert london["high_sweep_time"] == index[3]
    assert london["low_swept"] is True
    assert london["low_sweep_time"] == index[4]
