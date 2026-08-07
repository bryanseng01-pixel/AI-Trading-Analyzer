from dataclasses import FrozenInstanceError, fields

import pandas as pd
import pytest

from premium_discount_engine import (
    DealingRangeValidity,
    LocationClassification,
    construct_dealing_range,
    evaluate_premium_discount,
)
from timeframe_roles import Direction


def _swings():
    times = pd.date_range("2026-01-05 09:30", periods=8, freq="15min", tz="UTC")
    highs = (
        (times[1], 110.0),
        (times[3], 115.0),
        (times[6], 120.0),
    )
    lows = (
        (times[0], 90.0),
        (times[2], 95.0),
        (times[5], 100.0),
    )
    return times, highs, lows


def test_bullish_uses_latest_completed_low_to_high_leg():
    times, highs, lows = _swings()

    result = construct_dealing_range(
        reversed(highs),
        reversed(lows),
        direction=Direction.BULLISH,
        timeframe="15m",
        evaluated_through=times[-1],
    )

    dealing_range = result.dealing_range
    assert result.validity == DealingRangeValidity.VALID
    assert dealing_range.low == 100.0
    assert dealing_range.high == 120.0
    assert dealing_range.low_time == times[5]
    assert dealing_range.high_time == times[6]
    assert dealing_range.equilibrium == 110.0
    assert dealing_range.formation_start_time == times[5]
    assert dealing_range.formation_end_time == times[6]


def test_bearish_uses_latest_completed_high_to_low_leg():
    times, highs, lows = _swings()
    later_low = (times[7], 92.0)

    result = construct_dealing_range(
        highs,
        lows + (later_low,),
        direction=Direction.BEARISH,
        timeframe="15 Minute",
    )

    dealing_range = result.dealing_range
    assert dealing_range.high == 120.0
    assert dealing_range.low == 92.0
    assert dealing_range.high_time == times[6]
    assert dealing_range.low_time == times[7]
    assert dealing_range.formation_start_time == times[6]
    assert dealing_range.formation_end_time == times[7]


def test_incomplete_newest_leg_does_not_replace_completed_range():
    times, highs, lows = _swings()
    newest_low = (times[7], 105.0)

    result = construct_dealing_range(
        highs,
        lows + (newest_low,),
        direction=Direction.BULLISH,
        timeframe="15m",
    )

    assert result.dealing_range.low == 100.0
    assert result.dealing_range.high == 120.0


def test_later_confirmed_external_swing_invalidates_without_fallback():
    times, highs, lows = _swings()
    bullish = construct_dealing_range(
        highs,
        lows + ((times[7], 99.0),),
        direction=Direction.BULLISH,
        timeframe="15m",
    )
    bearish_times = pd.date_range(
        "2026-01-06 09:30", periods=5, freq="15min", tz="UTC"
    )
    bearish = construct_dealing_range(
        (
            (bearish_times[0], 120.0),
            (bearish_times[3], 121.0),
        ),
        ((bearish_times[2], 100.0),),
        direction=Direction.BEARISH,
        timeframe="15m",
    )

    assert bullish.dealing_range is None
    assert bullish.validity == DealingRangeValidity.INVALIDATED_BY_LATER_SWING
    assert bearish.dealing_range is None
    assert bearish.validity == DealingRangeValidity.INVALIDATED_BY_LATER_SWING


def test_equal_later_boundary_does_not_invalidate():
    times, highs, lows = _swings()

    result = construct_dealing_range(
        highs,
        lows + ((times[7], 100.0),),
        direction=Direction.BULLISH,
        timeframe="15m",
    )

    assert result.validity == DealingRangeValidity.VALID


def test_insufficient_and_unordered_swings_return_explicit_invalidity():
    times, highs, lows = _swings()
    insufficient = construct_dealing_range(
        highs,
        (),
        direction=Direction.BULLISH,
        timeframe="15m",
    )
    unordered = construct_dealing_range(
        ((times[0], 110.0),),
        ((times[1], 90.0),),
        direction=Direction.BULLISH,
        timeframe="15m",
    )

    assert insufficient.validity == DealingRangeValidity.INSUFFICIENT_SWINGS
    assert insufficient.dealing_range is None
    assert unordered.validity == DealingRangeValidity.NO_COMPLETED_DIRECTIONAL_LEG


def test_wrong_timeframe_and_conflicting_swings_are_rejected():
    times, highs, lows = _swings()
    with pytest.raises(ValueError, match="15M"):
        construct_dealing_range(
            highs,
            lows,
            direction=Direction.BULLISH,
            timeframe="5m",
        )
    with pytest.raises(ValueError, match="Conflicting"):
        construct_dealing_range(
            highs + ((times[1], 111.0),),
            lows,
            direction=Direction.BULLISH,
            timeframe="15m",
        )


@pytest.mark.parametrize(
    ("bottom", "top", "classification"),
    [
        (101.0, 105.0, LocationClassification.DISCOUNT),
        (115.0, 119.0, LocationClassification.PREMIUM),
        (110.0, 110.0, LocationClassification.EQUILIBRIUM),
        (105.0, 115.0, LocationClassification.CROSSES_EQUILIBRIUM),
        (110.0, 115.0, LocationClassification.PREMIUM),
        (105.0, 110.0, LocationClassification.DISCOUNT),
        (95.0, 105.0, LocationClassification.OUTSIDE_RANGE),
        (105.0, 125.0, LocationClassification.OUTSIDE_RANGE),
        (105.0, 105.0, LocationClassification.DISCOUNT),
        (115.0, 115.0, LocationClassification.PREMIUM),
    ],
)
def test_execution_location_classification(bottom, top, classification):
    _, highs, lows = _swings()
    result = construct_dealing_range(
        highs,
        lows,
        direction=Direction.BULLISH,
        timeframe="15m",
    )

    assessment = evaluate_premium_discount(
        result,
        execution_zone_top=top,
        execution_zone_bottom=bottom,
    )

    assert assessment.classification == classification


def test_directional_alignment_is_bullish_discount_and_bearish_premium():
    _, highs, lows = _swings()
    bullish_range = construct_dealing_range(
        highs,
        lows,
        direction=Direction.BULLISH,
        timeframe="15m",
    )
    bearish_times = pd.date_range(
        "2026-01-06 09:30", periods=3, freq="15min", tz="UTC"
    )
    bearish_range = construct_dealing_range(
        ((bearish_times[0], 120.0),),
        ((bearish_times[1], 100.0),),
        direction=Direction.BEARISH,
        timeframe="15m",
    )

    bullish = evaluate_premium_discount(
        bullish_range,
        execution_zone_bottom=101.0,
        execution_zone_top=105.0,
    )
    bearish = evaluate_premium_discount(
        bearish_range,
        execution_zone_bottom=115.0,
        execution_zone_top=119.0,
    )
    wrong_side = evaluate_premium_discount(
        bullish_range,
        execution_zone_bottom=115.0,
        execution_zone_top=119.0,
    )

    assert bullish.directionally_aligned is True
    assert bearish.directionally_aligned is True
    assert wrong_side.directionally_aligned is False


def test_invalid_range_cannot_classify_and_unknown_is_reserved():
    _, highs, _ = _swings()
    invalid = construct_dealing_range(
        highs,
        (),
        direction=Direction.BULLISH,
        timeframe="15m",
    )

    assert evaluate_premium_discount(
        invalid,
        execution_zone_bottom=100.0,
        execution_zone_top=105.0,
    ) is None
    assert LocationClassification.UNKNOWN.value == "unknown"


def test_models_are_immutable_and_have_no_trade_outputs():
    _, highs, lows = _swings()
    result = construct_dealing_range(
        highs,
        lows,
        direction=Direction.BULLISH,
        timeframe="15m",
    )
    dealing_range = result.dealing_range

    with pytest.raises(FrozenInstanceError):
        dealing_range.high = 999.0
    names = {field.name for field in fields(dealing_range)}
    assert {"recommendation", "entry", "stop", "target", "score"}.isdisjoint(names)
