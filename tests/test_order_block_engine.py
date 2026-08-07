from dataclasses import FrozenInstanceError, fields, replace

import pytest

from order_block_engine import (
    OrderBlockResult,
    OrderBlockRules,
    OrderBlockState,
    StructureBreakRef,
    StructureEventType,
    evaluate_order_blocks,
    select_relevant_order_block,
)
from order_blocks import detect_order_blocks
from timeframe_roles import Direction


def _market(ohlc_factory, direction, post_rows=(), aligned_before_break=()):
    baseline = [
        (100, 102, 99, 101, 10),
        (101, 102, 100, 100, 10),
        (100, 102, 99, 101, 10),
        (101, 102, 100, 100, 10),
        (100, 102, 99, 101, 10),
    ]
    if direction == Direction.BULLISH:
        source = (101, 102, 99, 100, 10)
        break_candle = (100, 107, 99, 106, 10)
        level = 104.0
    else:
        source = (100, 102, 99, 101, 10)
        break_candle = (101, 102, 94, 95, 10)
        level = 97.0
    data = ohlc_factory(
        baseline + [source] + list(aligned_before_break) + [break_candle] + list(post_rows)
    )
    event_time = data.index[6 + len(aligned_before_break)]
    return data, StructureBreakRef(
        direction=direction,
        event_type=StructureEventType.BOS,
        time=event_time,
        level=level,
    )


@pytest.mark.parametrize(
    ("direction", "expected_source_direction"),
    [
        (Direction.BULLISH, "bearish"),
        (Direction.BEARISH, "bullish"),
    ],
)
def test_structural_displacement_forms_directional_full_range_block(
    ohlc_factory,
    direction,
    expected_source_direction,
):
    data, event = _market(ohlc_factory, direction)

    result = evaluate_order_blocks(data, (event,), timeframe="1m")

    assert len(result.order_blocks) == 1
    block = result.order_blocks[0]
    source = data.loc[block.source_candle_time]
    actual_source_direction = (
        "bullish" if source["Close"] > source["Open"] else "bearish"
    )
    assert actual_source_direction == expected_source_direction
    assert block.direction == direction
    assert block.top == float(source["High"])
    assert block.bottom == float(source["Low"])
    assert block.formation_time == event.time
    assert block.displacement_time == event.time
    assert block.structure_event_type == StructureEventType.BOS
    assert block.state == OrderBlockState.UNTOUCHED
    assert block.quality is None
    assert block.still_respected is None


def test_bos_and_choch_are_both_eligible_and_choch_wins_exact_tie(ohlc_factory):
    data, bos = _market(ohlc_factory, Direction.BULLISH)
    choch = replace(bos, event_type=StructureEventType.CHOCH)

    bos_result = evaluate_order_blocks(data, (bos,), timeframe="1m")
    choch_result = evaluate_order_blocks(data, (choch,), timeframe="1m")
    duplicate_result = evaluate_order_blocks(
        data,
        (bos, choch),
        timeframe="1m",
    )

    assert bos_result.order_blocks[0].structure_event_type == StructureEventType.BOS
    assert choch_result.order_blocks[0].structure_event_type == StructureEventType.CHOCH
    assert len(duplicate_result.order_blocks) == 1
    assert (
        duplicate_result.order_blocks[0].structure_event_type
        == StructureEventType.CHOCH
    )


def test_opposite_candle_without_structure_event_forms_nothing(ohlc_factory):
    data, _ = _market(ohlc_factory, Direction.BULLISH)

    assert detect_order_blocks(data)
    assert evaluate_order_blocks(data, (), timeframe="1m").order_blocks == ()


def test_wick_only_break_and_weak_break_do_not_form_block(ohlc_factory):
    data, event = _market(ohlc_factory, Direction.BULLISH)
    wick_only = data.copy()
    wick_only.loc[event.time, "Close"] = event.level
    weak = data.copy()
    weak.loc[event.time, ["Open", "High", "Low", "Close"]] = [
        104.0,
        105.2,
        103.8,
        105.0,
    ]

    wick_result = evaluate_order_blocks(wick_only, (event,), timeframe="1m")
    weak_result = evaluate_order_blocks(weak, (event,), timeframe="1m")

    assert wick_result.order_blocks == ()
    assert any("close-confirmed" in item for item in wick_result.limitations)
    assert weak_result.order_blocks == ()
    assert any("lacks displacement" in item for item in weak_result.limitations)


def test_displacement_requires_baseline_and_body_to_range(ohlc_factory):
    data, event = _market(ohlc_factory, Direction.BULLISH)
    short = data.iloc[3:].copy()
    short_event = replace(event, time=short.index[3])
    wick_heavy = data.copy()
    wick_heavy.loc[event.time, ["Open", "High", "Low", "Close"]] = [
        100.0,
        120.0,
        90.0,
        106.0,
    ]

    short_result = evaluate_order_blocks(short, (short_event,), timeframe="1m")
    wick_result = evaluate_order_blocks(wick_heavy, (event,), timeframe="1m")

    assert short_result.order_blocks == ()
    assert any("Insufficient" in item for item in short_result.limitations)
    assert wick_result.order_blocks == ()
    assert any("lacks displacement" in item for item in wick_result.limitations)


def test_source_is_last_opposing_candle_before_uninterrupted_leg(ohlc_factory):
    aligned = (
        (100, 103, 99, 102, 10),
        (102, 104, 101, 103, 10),
    )
    data, event = _market(
        ohlc_factory,
        Direction.BULLISH,
        aligned_before_break=aligned,
    )

    block = evaluate_order_blocks(data, (event,), timeframe="1m").order_blocks[0]

    assert block.source_candle_time == data.index[5]


def test_doji_or_overly_distant_source_is_rejected(ohlc_factory):
    data, event = _market(ohlc_factory, Direction.BULLISH)
    doji = data.copy()
    doji.loc[data.index[5], "Close"] = doji.loc[data.index[5], "Open"]
    distant_aligned = tuple((100, 103, 99, 102, 10) for _ in range(3))
    distant_data, distant_event = _market(
        ohlc_factory,
        Direction.BULLISH,
        aligned_before_break=distant_aligned,
    )
    rules = replace(OrderBlockRules(), maximum_source_distance=2)

    doji_result = evaluate_order_blocks(doji, (event,), timeframe="1m")
    distant_result = evaluate_order_blocks(
        distant_data,
        (distant_event,),
        timeframe="1m",
        rules=rules,
    )

    assert doji_result.order_blocks == ()
    assert any("strict opposing" in item for item in doji_result.limitations)
    assert distant_result.order_blocks == ()
    assert any("bounded" in item for item in distant_result.limitations)


@pytest.mark.parametrize(
    ("row", "state"),
    [
        ((104, 105, 103, 104, 10), OrderBlockState.UNTOUCHED),
        ((103, 104, 102, 103, 10), OrderBlockState.TOUCHED),
        ((102, 104, 100, 103, 10), OrderBlockState.PARTIALLY_MITIGATED),
        ((101, 104, 98, 99, 10), OrderBlockState.FULLY_MITIGATED),
        ((101, 104, 98, 98.5, 10), OrderBlockState.INVALIDATED),
    ],
)
def test_bullish_lifecycle_uses_wicks_and_close_invalidation(
    ohlc_factory,
    row,
    state,
):
    data, event = _market(ohlc_factory, Direction.BULLISH, (row,))

    block = evaluate_order_blocks(data, (event,), timeframe="1m").order_blocks[0]

    assert block.state == state
    assert block.invalidated is (state == OrderBlockState.INVALIDATED)
    assert block.active is (
        state
        in {
            OrderBlockState.UNTOUCHED,
            OrderBlockState.TOUCHED,
            OrderBlockState.PARTIALLY_MITIGATED,
        }
    )


@pytest.mark.parametrize(
    ("row", "state"),
    [
        ((97, 98, 96, 97, 10), OrderBlockState.UNTOUCHED),
        ((98, 99, 97, 98, 10), OrderBlockState.TOUCHED),
        ((98, 100, 97, 98, 10), OrderBlockState.PARTIALLY_MITIGATED),
        ((100, 103, 97, 102, 10), OrderBlockState.FULLY_MITIGATED),
        ((100, 103, 97, 102.5, 10), OrderBlockState.INVALIDATED),
    ],
)
def test_bearish_lifecycle_is_symmetric(ohlc_factory, row, state):
    data, event = _market(ohlc_factory, Direction.BEARISH, (row,))

    block = evaluate_order_blocks(data, (event,), timeframe="1m").order_blocks[0]

    assert block.state == state


def test_fully_mitigated_can_later_be_invalidated_and_direct_break_records_times(
    ohlc_factory,
):
    data, event = _market(
        ohlc_factory,
        Direction.BULLISH,
        (
            (101, 104, 98, 99, 10),
            (101, 104, 98, 98.5, 10),
        ),
    )
    direct_data, direct_event = _market(
        ohlc_factory,
        Direction.BULLISH,
        ((101, 104, 98, 98.5, 10),),
    )

    block = evaluate_order_blocks(data, (event,), timeframe="1m").order_blocks[0]
    direct = evaluate_order_blocks(
        direct_data,
        (direct_event,),
        timeframe="1m",
    ).order_blocks[0]

    assert block.state == OrderBlockState.INVALIDATED
    assert block.mitigation_time == data.index[-2]
    assert block.invalidation_time == data.index[-1]
    assert direct.first_touch_time == direct_data.index[-1]
    assert direct.mitigation_time == direct_data.index[-1]
    assert direct.invalidation_time == direct_data.index[-1]


def test_selection_requires_direction_and_strict_overlap(ohlc_factory):
    data, event = _market(ohlc_factory, Direction.BULLISH)
    block = evaluate_order_blocks(data, (event,), timeframe="1m").order_blocks[0]
    touching = replace(block, top=100.0, bottom=97.0)
    overlapping = replace(block, top=103.0, bottom=100.0)
    opposing = replace(overlapping, direction=Direction.BEARISH)
    result = OrderBlockResult(
        timeframe="1m",
        evaluated_through=data.index[-1],
        order_blocks=(touching, opposing, overlapping),
        active_order_blocks=(touching, opposing, overlapping),
        limitations=(),
    )

    selected = select_relevant_order_block(
        result,
        direction=Direction.BULLISH,
        authority_zone_bottom=100.0,
        authority_zone_top=106.0,
    )

    assert selected == overlapping


def test_one_zone_selection_is_deterministic(ohlc_factory):
    data, event = _market(ohlc_factory, Direction.BULLISH)
    block = evaluate_order_blocks(data, (event,), timeframe="1m").order_blocks[0]
    smaller = replace(block, top=103.0, bottom=101.0)
    larger = replace(block, top=105.0, bottom=100.0)

    selected = []
    for blocks in ((smaller, larger), (larger, smaller)):
        result = OrderBlockResult(
            timeframe="1m",
            evaluated_through=data.index[-1],
            order_blocks=blocks,
            active_order_blocks=blocks,
            limitations=(),
        )
        selected.append(
            select_relevant_order_block(
                result,
                direction=Direction.BULLISH,
                authority_zone_bottom=100.0,
                authority_zone_top=106.0,
            )
        )

    assert selected == [larger, larger]


def test_models_are_immutable_and_have_no_trade_or_recommendation_outputs(
    ohlc_factory,
):
    data, event = _market(ohlc_factory, Direction.BULLISH)
    block = evaluate_order_blocks(data, (event,), timeframe="1m").order_blocks[0]

    with pytest.raises(FrozenInstanceError):
        block.still_respected = True

    names = {field.name for field in fields(block)}
    assert {"recommendation", "entry", "stop", "target", "score"}.isdisjoint(names)
