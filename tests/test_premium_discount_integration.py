from copy import deepcopy
from dataclasses import replace

import pandas as pd

from confluence import evaluate_confluence
from premium_discount_engine import (
    DealingRangeValidity,
    LocationClassification,
    construct_dealing_range,
)
from premium_discount_integration import (
    build_premium_discount_confluence_factor,
)
from setup_overlay import build_setup_overlay
from test_decision_authority import _analyses, _evaluate
from test_ifvg_integration import _lifecycle
from test_order_block_integration import _result as _order_block_result
from test_setup_overlay import _add_execution_fvg, _sessions
from timeframe_roles import Direction
from tradingview_chart import _serialize_setup_overlay


def _range(direction, *, low=90.0, high=130.0):
    times = pd.date_range("2026-01-05 09:30", periods=3, freq="15min", tz="UTC")
    if direction == Direction.BULLISH:
        highs = ((times[1], high),)
        lows = ((times[0], low),)
    else:
        highs = ((times[0], high),)
        lows = ((times[1], low),)
    return construct_dealing_range(
        highs,
        lows,
        direction=direction,
        timeframe="15m",
        evaluated_through=times[-1],
    )


def _overlay(
    ohlc_factory,
    range_result,
    *,
    context="bullish",
    swept=True,
    lifecycle=None,
    order_blocks=None,
):
    analyses = _analyses(ohlc_factory, context=context)
    analyses["1 Minute"] = _add_execution_fvg(
        analyses["1 Minute"],
        direction=context,
    )
    sessions = _sessions(analyses["5 Minute"], context, swept=swept)
    decision = _evaluate(analyses, sessions)
    overlay = build_setup_overlay(
        decision,
        analyses,
        sessions,
        fvg_lifecycle_result=lifecycle,
        minimum_ifvg_size=1.0 if lifecycle is not None else None,
        order_block_result=order_blocks,
        dealing_range_result=range_result,
    )
    return decision, overlay


def test_bullish_discount_and_bearish_premium_are_optional_support(ohlc_factory):
    bullish_decision, bullish = _overlay(
        ohlc_factory,
        _range(Direction.BULLISH),
    )
    bearish_decision, bearish = _overlay(
        ohlc_factory,
        _range(Direction.BEARISH, low=80.0, high=120.0),
        context="bearish",
    )

    assert bullish_decision.recommendation == "READY"
    assert bullish.premium_discount_support.classification == (
        LocationClassification.DISCOUNT
    )
    assert bullish.premium_discount_support.directionally_aligned is True
    assert bearish_decision.recommendation == "READY"
    assert bearish.premium_discount_support.classification == (
        LocationClassification.PREMIUM
    )
    assert bearish.premium_discount_support.directionally_aligned is True


def test_wrong_side_crossing_and_outside_range_are_evaluable_but_unsatisfied(
    ohlc_factory,
):
    cases = (
        (_range(Direction.BULLISH, low=80.0, high=110.0), LocationClassification.PREMIUM),
        (
            _range(Direction.BULLISH, low=90.0, high=120.0),
            LocationClassification.CROSSES_EQUILIBRIUM,
        ),
        (
            _range(Direction.BULLISH, low=90.0, high=104.0),
            LocationClassification.OUTSIDE_RANGE,
        ),
    )

    for range_result, expected in cases:
        _, overlay = _overlay(ohlc_factory, range_result)
        support = overlay.premium_discount_support
        factor = build_premium_discount_confluence_factor(overlay)
        assert support.applicable is True
        assert support.classification == expected
        assert factor.active is True
        assert factor.satisfied is False


def test_invalid_range_wait_and_avoid_are_inactive(ohlc_factory):
    invalid = construct_dealing_range(
        ((pd.Timestamp("2026-01-05", tz="UTC"), 110.0),),
        (),
        direction=Direction.BULLISH,
        timeframe="15m",
    )
    _, invalid_overlay = _overlay(ohlc_factory, invalid)
    _, waiting = _overlay(
        ohlc_factory,
        _range(Direction.BULLISH),
        swept=False,
    )
    analyses = _analyses(ohlc_factory)
    analyses["1 Hour"] = replace(analyses["1 Hour"], trend="BEARISH 🔴")
    decision = _evaluate(analyses, {})
    avoid = build_setup_overlay(
        decision,
        analyses,
        {},
        dealing_range_result=_range(Direction.BULLISH),
    )

    assert invalid.validity == DealingRangeValidity.INSUFFICIENT_SWINGS
    assert invalid_overlay.premium_discount_support.applicable is False
    assert build_premium_discount_confluence_factor(
        invalid_overlay
    ).satisfied is None
    assert waiting.premium_discount_support.applicable is False
    assert avoid.premium_discount_support.applicable is False
    assert avoid.visibility.show_dealing_range is False


def test_factor_replaces_placeholder_without_becoming_required(ohlc_factory):
    decision, overlay = _overlay(ohlc_factory, _range(Direction.BULLISH))
    factor = build_premium_discount_confluence_factor(overlay)
    result = evaluate_confluence(decision, overlay, (factor,))

    assert factor.key == "premium_discount"
    assert factor.name == "Premium / Discount"
    assert factor.active is True
    assert factor.required is False
    assert factor.satisfied is True
    assert "premium_discount" not in {
        item.key for item in result.pending_future_factors
    }


def test_chart_serializes_one_supplied_range_without_calculating_it(ohlc_factory):
    _, overlay = _overlay(ohlc_factory, _range(Direction.BULLISH))

    serialized = _serialize_setup_overlay(overlay)
    dealing_range = serialized["dealing_range"]

    assert dealing_range["high"] == 130.0
    assert dealing_range["low"] == 90.0
    assert dealing_range["equilibrium"] == 110.0
    assert dealing_range["classification"] == "discount"
    assert serialized["execution_zone"]["purpose"] == "authority_required"


def test_range_evaluation_does_not_change_ifvg_order_block_or_authority(
    ohlc_factory,
):
    lifecycle = _lifecycle(ohlc_factory)
    order_blocks = _order_block_result(ohlc_factory)
    decision, without_range = _overlay(
        ohlc_factory,
        None,
        lifecycle=lifecycle,
        order_blocks=order_blocks,
    )
    original = deepcopy(decision)
    _, with_range = _overlay(
        ohlc_factory,
        _range(Direction.BULLISH),
        lifecycle=lifecycle,
        order_blocks=order_blocks,
    )

    assert with_range.active_execution_zone == without_range.active_execution_zone
    assert with_range.ifvg_support == without_range.ifvg_support
    assert with_range.order_block_support == without_range.order_block_support
    assert decision == original
    assert decision.recommendation == "READY"


def test_chart_selection_cannot_change_range_or_classification(ohlc_factory):
    range_result = _range(Direction.BULLISH)
    analyses = _analyses(ohlc_factory)
    analyses["1 Minute"] = _add_execution_fvg(analyses["1 Minute"])
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=True)
    decision = _evaluate(analyses, sessions)
    snapshots = set()

    for selected in analyses:
        assert analyses[selected] is not None
        overlay = build_setup_overlay(
            decision,
            analyses,
            sessions,
            dealing_range_result=range_result,
        )
        support = overlay.premium_discount_support
        snapshots.add(
            (
                decision.recommendation,
                support.dealing_range.high,
                support.dealing_range.low,
                support.classification,
            )
        )

    assert snapshots == {
        ("READY", 130.0, 90.0, LocationClassification.DISCOUNT)
    }
