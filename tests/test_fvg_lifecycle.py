from dataclasses import FrozenInstanceError, fields, replace

import pytest

from fair_value_gap import detect_fair_value_gaps
from fvg_lifecycle import (
    DetectedFvg,
    FvgLifecycleResult,
    FvgLifecycleState,
    ImbalanceKind,
    evaluate_fvg_lifecycles,
    select_relevant_imbalance,
)
from timeframe_roles import Direction


def _data(ohlc_factory, post_rows):
    formation_rows = [
        (100, 101, 99, 100, 10),
        (100, 103, 99, 102, 10),
        (102, 104, 102, 103, 10),
    ]
    return ohlc_factory(formation_rows + post_rows)


def _formation(data, direction=Direction.BULLISH):
    return DetectedFvg(
        direction=direction,
        top=102.0,
        bottom=100.0,
        formation_start_time=data.index[0],
        formation_time=data.index[2],
    )


def _zone(ohlc_factory, post_rows, direction=Direction.BULLISH):
    data = _data(ohlc_factory, post_rows)
    return evaluate_fvg_lifecycles(
        data,
        (_formation(data, direction),),
        timeframe="1m",
    ).zones[0]


@pytest.mark.parametrize(
    ("row", "state", "fill"),
    [
        ((103, 104, 103, 103, 10), FvgLifecycleState.UNTOUCHED, 0.0),
        ((103, 104, 102, 103, 10), FvgLifecycleState.ENTERED, 0.0),
        (
            (103, 104, 101, 103, 10),
            FvgLifecycleState.PARTIALLY_MITIGATED,
            0.5,
        ),
        ((101, 103, 99, 100, 10), FvgLifecycleState.FULLY_FILLED, 1.0),
    ],
)
def test_bullish_wicks_define_interaction_and_fill(
    ohlc_factory,
    row,
    state,
    fill,
):
    zone = _zone(ohlc_factory, [row])

    assert zone.state == state
    assert zone.fill_percentage == fill
    assert zone.kind == ImbalanceKind.FVG
    assert zone.current_direction == Direction.BULLISH
    assert zone.quality is None


@pytest.mark.parametrize(
    ("row", "state", "fill"),
    [
        ((99, 99, 98, 99, 10), FvgLifecycleState.UNTOUCHED, 0.0),
        ((99, 100, 98, 99, 10), FvgLifecycleState.ENTERED, 0.0),
        (
            (99, 101, 98, 99, 10),
            FvgLifecycleState.PARTIALLY_MITIGATED,
            0.5,
        ),
        ((101, 103, 99, 102, 10), FvgLifecycleState.FULLY_FILLED, 1.0),
    ],
)
def test_bearish_wicks_define_interaction_and_fill(
    ohlc_factory,
    row,
    state,
    fill,
):
    zone = _zone(ohlc_factory, [row], Direction.BEARISH)

    assert zone.state == state
    assert zone.fill_percentage == fill
    assert zone.kind == ImbalanceKind.FVG
    assert zone.current_direction == Direction.BEARISH


def test_bullish_fvg_requires_close_below_bottom_to_invert(ohlc_factory):
    wick_only = _zone(ohlc_factory, [(101, 103, 99, 101, 10)])
    boundary_close = _zone(ohlc_factory, [(101, 103, 99, 100, 10)])
    close_through = _zone(ohlc_factory, [(101, 103, 99, 99.5, 10)])

    assert wick_only.state == FvgLifecycleState.FULLY_FILLED
    assert boundary_close.state == FvgLifecycleState.FULLY_FILLED
    assert close_through.state == FvgLifecycleState.INVERTED
    assert close_through.kind == ImbalanceKind.IFVG
    assert close_through.original_direction == Direction.BULLISH
    assert close_through.current_direction == Direction.BEARISH
    assert close_through.inversion_time is not None


def test_bearish_fvg_requires_close_above_top_to_invert(ohlc_factory):
    wick_only = _zone(
        ohlc_factory,
        [(101, 103, 99, 101, 10)],
        Direction.BEARISH,
    )
    boundary_close = _zone(
        ohlc_factory,
        [(101, 103, 99, 102, 10)],
        Direction.BEARISH,
    )
    close_through = _zone(
        ohlc_factory,
        [(101, 103, 99, 102.5, 10)],
        Direction.BEARISH,
    )

    assert wick_only.state == FvgLifecycleState.FULLY_FILLED
    assert boundary_close.state == FvgLifecycleState.FULLY_FILLED
    assert close_through.state == FvgLifecycleState.INVERTED
    assert close_through.current_direction == Direction.BULLISH


def test_ifvg_invalidation_requires_close_through_opposite_boundary(
    ohlc_factory,
):
    still_active = _zone(
        ohlc_factory,
        [
            (101, 103, 99, 99.5, 10),
            (101, 103, 99, 101, 10),
        ],
    )
    invalidated = _zone(
        ohlc_factory,
        [
            (101, 103, 99, 99.5, 10),
            (101, 103, 99, 102.5, 10),
        ],
    )

    assert still_active.state == FvgLifecycleState.INVERTED
    assert still_active.current_direction == Direction.BEARISH
    assert invalidated.state == FvgLifecycleState.INVALIDATED
    assert invalidated.current_direction is None
    assert invalidated.invalidation_time is not None
    assert invalidated.active is False


def test_bullish_ifvg_invalidation_is_directionally_symmetric(ohlc_factory):
    zone = _zone(
        ohlc_factory,
        [
            (101, 103, 99, 102.5, 10),
            (101, 103, 99, 99.5, 10),
        ],
        Direction.BEARISH,
    )

    assert zone.state == FvgLifecycleState.INVALIDATED
    assert zone.current_direction is None


def test_fill_percentage_tracks_deepest_interaction(ohlc_factory):
    zone = _zone(
        ohlc_factory,
        [
            (103, 104, 101.5, 103, 10),
            (103, 104, 101.8, 103, 10),
        ],
    )

    assert zone.state == FvgLifecycleState.PARTIALLY_MITIGATED
    assert zone.fill_percentage == 0.25
    assert zone.partial_mitigation_time == zone.first_entry_time


def test_existing_mitigation_semantics_are_preserved_by_compatibility_flag(
    ohlc_factory,
):
    data = _data(ohlc_factory, [(101, 103, 99, 101, 10)])
    detected = detect_fair_value_gaps(data)[0]
    result = evaluate_fvg_lifecycles(data, (detected,), timeframe="1m")

    assert detected["mitigated"] is True
    assert result.zones[0].legacy_mitigated is True
    assert result.zones[0].state == FvgLifecycleState.FULLY_FILLED


def test_formation_candle_is_not_evaluated_as_mitigation(ohlc_factory):
    data = _data(ohlc_factory, [])
    formation = _formation(data)

    zone = evaluate_fvg_lifecycles(
        data,
        (formation,),
        timeframe="1m",
    ).zones[0]

    assert zone.state == FvgLifecycleState.UNTOUCHED
    assert zone.last_evaluated_time is None


def test_selection_is_directional_kind_explicit_and_deterministic(ohlc_factory):
    near = _zone(ohlc_factory, [(103, 104, 103, 103, 10)])
    older_far = replace(
        near,
        top=96.0,
        bottom=94.0,
        inversion_boundary=94.0,
    )
    result = FvgLifecycleResult(
        timeframe="1m",
        evaluated_through=near.last_evaluated_time,
        zones=(older_far, near),
        active_fvgs=(older_far, near),
        active_ifvgs=(),
        limitations=(),
    )

    selected = select_relevant_imbalance(
        result,
        direction=Direction.BULLISH,
        current_price=103.0,
        minimum_size=1.0,
        allowed_kinds=frozenset({ImbalanceKind.FVG}),
    )
    reversed_selected = select_relevant_imbalance(
        replace(result, zones=tuple(reversed(result.zones))),
        direction=Direction.BULLISH,
        current_price=103.0,
        minimum_size=1.0,
        allowed_kinds=frozenset({ImbalanceKind.FVG}),
    )

    assert selected == near
    assert reversed_selected == near
    assert select_relevant_imbalance(
        result,
        direction=Direction.BULLISH,
        current_price=103.0,
        minimum_size=1.0,
        allowed_kinds=frozenset({ImbalanceKind.IFVG}),
    ) is None


def test_models_are_immutable_and_generate_no_trade_outputs(ohlc_factory):
    zone = _zone(ohlc_factory, [(103, 104, 103, 103, 10)])

    with pytest.raises(FrozenInstanceError):
        zone.fill_percentage = 1.0

    names = {field.name for field in fields(zone)}
    assert {"recommendation", "entry", "stop", "targets"}.isdisjoint(names)


def test_invalid_bounds_and_fill_are_rejected(ohlc_factory):
    data = _data(ohlc_factory, [])
    with pytest.raises(ValueError, match="top"):
        replace(_formation(data), top=100.0)

    zone = _zone(ohlc_factory, [(103, 104, 103, 103, 10)])
    with pytest.raises(ValueError, match="fill_percentage"):
        replace(zone, fill_percentage=1.1)
