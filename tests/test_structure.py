import pytest

from market_structure import (
    detect_bos,
    detect_choch,
    label_highs,
    label_lows,
)
from structure import find_swing_points


def test_find_swing_points_uses_neighboring_highs_and_lows(ohlc_factory):
    data = ohlc_factory(
        [
            (9, 10, 8, 9, 10),
            (10, 12, 9, 11, 10),
            (9, 11, 7, 10, 10),
            (11, 14, 10, 13, 10),
            (10, 12, 6, 11, 10),
            (11, 13, 9, 12, 10),
            (9, 10, 8, 9, 10),
        ]
    )

    highs, lows = find_swing_points(data, lookback=1)

    assert highs == [
        (data.index[1], 12.0),
        (data.index[3], 14.0),
        (data.index[5], 13.0),
    ]
    assert lows == [
        (data.index[2], 7.0),
        (data.index[4], 6.0),
    ]


def test_high_and_low_labels_characterize_all_four_structure_labels(
    ohlc_factory,
):
    data = ohlc_factory([(1, 2, 0, 1, 1)] * 3)
    times = data.index

    high_labels = label_highs(
        [(times[0], 100.0), (times[1], 105.0), (times[2], 102.0)]
    )
    low_labels = label_lows(
        [(times[0], 90.0), (times[1], 95.0), (times[2], 89.0)]
    )

    assert [label[2] for label in high_labels] == ["HH", "LH"]
    assert [label[2] for label in low_labels] == ["HL", "LL"]


@pytest.mark.parametrize(
    ("structure", "direction", "highs", "lows", "close_break"),
    [
        ("Bullish Structure", "bullish", (105.0, 106.0), (95.0, 97.0), 106.0),
        ("Bearish Structure", "bearish", (105.0, 103.0), (95.0, 94.0), 94.0),
    ],
)
def test_bos_requires_a_candle_close(
    ohlc_factory,
    structure,
    direction,
    highs,
    lows,
    close_break,
):
    if direction == "bullish":
        rows = [
            (100, 104, 99, 103, 10),
            (103, 106, 101, 104, 10),  # Wick through 105; close stays below.
            (104, 107, 103, close_break, 10),
            (106, 108, 105, 107, 10),
        ]
    else:
        rows = [
            (100, 102, 96, 97, 10),
            (97, 99, 94, 96, 10),  # Wick through 95; close stays above.
            (96, 97, 93, close_break, 10),
            (94, 95, 92, 93, 10),
        ]

    data = ohlc_factory(rows)
    high_labels = [
        (data.index[0], highs[0], "HH" if direction == "bullish" else "LH"),
        (data.index[3], highs[1], "HH" if direction == "bullish" else "LH"),
    ]
    low_labels = [
        (data.index[0], lows[0], "HL" if direction == "bullish" else "LL"),
        (data.index[3], lows[1], "HL" if direction == "bullish" else "LL"),
    ]

    result = detect_bos(data, high_labels, low_labels, structure)

    assert result is not None
    assert result["direction"] == direction
    assert result["time"] == data.index[2]


@pytest.mark.parametrize(
    ("structure", "direction"),
    [
        ("Bullish Structure", "bullish"),
        ("Bearish Structure", "bearish"),
    ],
)
def test_wick_only_break_does_not_count_as_bos(
    ohlc_factory,
    structure,
    direction,
):
    if direction == "bullish":
        rows = [(100, 104, 99, 103, 10), (103, 106, 101, 104, 10)]
        high_labels = [
            (None, 105.0, "HH"),
            (None, 106.0, "HH"),
        ]
        low_labels = [(None, 95.0, "HL"), (None, 97.0, "HL")]
    else:
        rows = [(100, 102, 96, 97, 10), (97, 99, 94, 96, 10)]
        high_labels = [(None, 105.0, "LH"), (None, 103.0, "LH")]
        low_labels = [(None, 95.0, "LL"), (None, 94.0, "LL")]

    data = ohlc_factory(rows)
    high_labels = [(data.index[0], price, label) for _, price, label in high_labels]
    low_labels = [(data.index[0], price, label) for _, price, label in low_labels]

    assert detect_bos(data, high_labels, low_labels, structure) is None


@pytest.mark.parametrize(
    ("structure", "expected_direction"),
    [
        ("Bullish Structure", "bearish"),
        ("Bearish Structure", "bullish"),
    ],
)
def test_choch_requires_a_candle_close(
    ohlc_factory,
    structure,
    expected_direction,
):
    if expected_direction == "bearish":
        rows = [
            (100, 103, 97, 101, 10),
            (101, 102, 94, 96, 10),  # Wick through 95; close stays above.
            (96, 97, 93, 94, 10),
        ]
    else:
        rows = [
            (100, 103, 97, 99, 10),
            (99, 106, 98, 104, 10),  # Wick through 105; close stays below.
            (104, 107, 103, 106, 10),
        ]

    data = ohlc_factory(rows)
    high_labels = [(data.index[0], 105.0, "HH" if structure.startswith("Bull") else "LH")]
    low_labels = [(data.index[0], 95.0, "HL" if structure.startswith("Bull") else "LL")]

    result = detect_choch(data, high_labels, low_labels, structure)

    assert result is not None
    assert result["direction"] == expected_direction
    assert result["time"] == data.index[2]


@pytest.mark.parametrize(
    "structure",
    ["Bullish Structure", "Bearish Structure"],
)
def test_wick_only_break_does_not_count_as_choch(ohlc_factory, structure):
    if structure == "Bullish Structure":
        rows = [(100, 103, 97, 101, 10), (101, 102, 94, 96, 10)]
    else:
        rows = [(100, 103, 97, 99, 10), (99, 106, 98, 104, 10)]

    data = ohlc_factory(rows)
    high_labels = [(data.index[0], 105.0, "HH" if structure.startswith("Bull") else "LH")]
    low_labels = [(data.index[0], 95.0, "HL" if structure.startswith("Bull") else "LL")]

    assert detect_choch(data, high_labels, low_labels, structure) is None
