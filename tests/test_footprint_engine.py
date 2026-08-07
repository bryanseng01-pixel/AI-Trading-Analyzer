from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import inspect
import random

import pandas as pd
import pytest

from delta_engine import build_execution_location_window, evaluate_delta
from footprint_engine import (
    DEFAULT_BID_ASK_IMBALANCE_RULES,
    DEFAULT_FOOTPRINT_RULES,
    BidAskImbalanceRules,
    FootprintRules,
    build_footprint,
    build_footprint_confluence_factor,
    evaluate_bid_ask_imbalance,
)
from order_flow_engines import ImbalanceContext
from order_flow_models import (
    AggressorSide,
    AnalyticalAvailability,
    DataGap,
    EntitlementState,
    OrderFlowDataQuality,
    OrderFlowWindow,
    TradeEvent,
)
from test_delta_engine import BASE, _location
from test_decision_authority import (
    _analyses,
    _evaluate as _evaluate_authority,
    _session_sweep,
)
from test_order_flow_architecture import _provenance
from timeframe_roles import Direction


def _trade(event_id, seconds, price, quantity, side, *, sequence=None, **changes):
    timestamp = BASE + pd.Timedelta(seconds=seconds)
    values = dict(
        event_id=event_id,
        contract_code="NQU6",
        exchange_timestamp=timestamp,
        received_timestamp=timestamp + pd.Timedelta(milliseconds=2),
        sequence_number=sequence if sequence is not None else int(seconds * 1000),
        price=price,
        quantity=quantity,
        aggressor_side=side,
        aggressor_source="provider_reported",
        is_correction=False,
    )
    values.update(changes)
    return TradeEvent(**values)


def _flow(trades, *, provenance=None, gaps=()):
    return OrderFlowWindow(
        provenance=provenance or _provenance(),
        trades=tuple(trades),
        quotes=(),
        provider_price_levels=(),
        gaps=tuple(gaps),
    )


def _run(trades, *, location=None, through=None, previous=None, provenance=None, gaps=()):
    location = location or replace(_location(), top=100.5)
    through = through or BASE + pd.Timedelta(seconds=10)
    window = build_execution_location_window(
        location,
        tuple(trades),
        authority_observed_at=BASE,
        evaluated_through=through,
        execution_zone_visible=True,
        location_active=True,
        previous_window=previous,
    )
    flow = _flow(trades, provenance=provenance, gaps=gaps)
    footprint = build_footprint(flow, window)
    return flow, window, footprint, evaluate_bid_ask_imbalance(footprint)


def test_rules_are_centralized_immutable_and_exact():
    assert DEFAULT_FOOTPRINT_RULES == FootprintRules(
        price_alignment_tolerance_ticks=0.000001,
        comparison_halo_ticks=1,
        minimum_classification_coverage=0.90,
    )
    assert DEFAULT_BID_ASK_IMBALANCE_RULES == BidAskImbalanceRules(
        imbalance_ratio=3.0,
        minimum_numerator_volume=10.0,
        minimum_stacked_levels=3,
        stacked_gap_allowance_ticks=0,
        minimum_classification_coverage=0.90,
    )
    with pytest.raises(FrozenInstanceError):
        DEFAULT_FOOTPRINT_RULES.comparison_halo_ticks = 2


def test_tick_level_aggregation_unknown_arithmetic_and_one_tick_halo():
    trades = (
        _trade("touch", 1, 100.0, 12, AggressorSide.BUY),
        _trade("sell", 2, 100.0, 3, AggressorSide.SELL),
        _trade("unknown", 3, 100.0, 1, AggressorSide.UNKNOWN),
        _trade("upper-halo", 4, 100.75, 5, AggressorSide.SELL),
        _trade("outside", 5, 101.0, 50, AggressorSide.BUY),
    )
    _, _, footprint, _ = _run(trades)
    level = next(item for item in footprint.levels if item.price == 100.0)

    assert (level.ask_volume, level.bid_volume, level.unknown_volume) == (12, 3, 1)
    assert level.delta == 9
    assert level.trade_count == 3
    assert footprint.footprint_bottom == 99.75
    assert footprint.footprint_top == 100.75
    assert footprint.total_ask_volume == 12
    assert footprint.total_bid_volume == 8
    assert all(item.price != 101.0 for item in footprint.levels)
    assert next(item for item in footprint.levels if item.price == 100.75).comparison_only


def test_decimal_tick_tolerance_normalizes_noise_and_rejects_off_tick():
    _, _, accepted, _ = _run(
        (_trade("touch", 1, 100.0000001, 10, AggressorSide.BUY),)
    )
    _, _, rejected, assessment = _run(
        (_trade("touch", 1, 100.000001, 10, AggressorSide.BUY),)
    )

    assert accepted.levels[1].price == 100.0
    assert rejected.metadata.availability == AnalyticalAvailability.UNAVAILABLE
    assert assessment.context == ImbalanceContext.UNAVAILABLE
    assert "off-tick" in assessment.explanation.lower()


def test_diagonal_ratio_minimum_and_zero_denominator_boundaries():
    trades = (
        _trade("touch", 1, 100.0, 10, AggressorSide.BUY),
        _trade("denominator", 2, 99.75, 10 / 3, AggressorSide.SELL),
        _trade("zero-denominator", 3, 100.25, 10, AggressorSide.BUY),
        _trade("below-minimum", 4, 100.5, 9.99, AggressorSide.BUY),
    )
    _, _, _, assessment = _run(trades)
    by_price = {item.subject_price: item for item in assessment.imbalances}

    assert by_price[100.0].ratio == pytest.approx(3.0)
    assert by_price[100.25].zero_denominator is True
    assert by_price[100.25].ratio is None
    assert 100.5 not in by_price


def test_three_adjacent_ask_levels_form_one_supportive_maximal_stack():
    trades = tuple(
        _trade(f"ask-{index}", index + 1, 100 + index * 0.25, 10, AggressorSide.BUY)
        for index in range(3)
    )
    _, _, _, assessment = _run(trades)

    assert assessment.context == ImbalanceContext.SUPPORTIVE_AGGRESSION
    assert assessment.supportive is True
    assert len(assessment.ask_stacks) == 1
    assert len(assessment.ask_stacks[0]) == 3
    assert len({item.stacked_sequence_id for item in assessment.ask_stacks[0]}) == 1


def test_two_levels_or_a_gap_do_not_form_a_stack_and_same_level_is_disabled():
    two = (
        _trade("ask-0", 1, 100, 30, AggressorSide.BUY),
        _trade("sell-same", 2, 100, 1, AggressorSide.SELL),
        _trade("ask-1", 3, 100.25, 30, AggressorSide.BUY),
    )
    _, _, _, two_result = _run(two)
    gap = two + (_trade("ask-2", 4, 100.75, 30, AggressorSide.BUY),)
    _, _, _, gap_result = _run(gap, location=replace(_location(), top=100.75))

    assert two_result.context == ImbalanceContext.NO_STACKED_IMBALANCE
    assert gap_result.ask_stacks == ()


@pytest.mark.parametrize(
    ("direction", "side", "expected"),
    (
        (Direction.BULLISH, AggressorSide.BUY, ImbalanceContext.SUPPORTIVE_AGGRESSION),
        (Direction.BULLISH, AggressorSide.SELL, ImbalanceContext.OPPOSING_AGGRESSION),
        (Direction.BEARISH, AggressorSide.SELL, ImbalanceContext.SUPPORTIVE_AGGRESSION),
        (Direction.BEARISH, AggressorSide.BUY, ImbalanceContext.OPPOSING_AGGRESSION),
    ),
)
def test_directional_interpretation_requires_location_context(direction, side, expected):
    trades = tuple(
        _trade(f"trade-{index}", index + 1, 100 + index * 0.25, 10, side)
        for index in range(3)
    )
    _, _, _, result = _run(trades, location=replace(_location(direction=direction), top=100.5))
    assert result.context == expected
    assert result.supportive is (expected == ImbalanceContext.SUPPORTIVE_AGGRESSION)


def test_low_coverage_keeps_facts_but_disables_interpretation():
    trades = (
        _trade("touch", 1, 100, 8.9, AggressorSide.BUY),
        _trade("unknown", 2, 100, 1.1, AggressorSide.UNKNOWN),
    )
    _, _, footprint, result = _run(trades)
    assert footprint.classification_coverage == pytest.approx(0.89)
    assert footprint.levels
    assert result.context == ImbalanceContext.UNAVAILABLE
    assert result.supportive is None


def test_gap_duplicate_correction_contract_and_delay_fail_closed():
    touch = _trade("touch", 1, 100, 10, AggressorSide.BUY)
    gap = DataGap(BASE, BASE + pd.Timedelta(milliseconds=1), 1, 2, "gap")
    _, _, gapped, _ = _run((touch,), gaps=(gap,))
    _, _, duplicate, _ = _run((touch, replace(touch, quantity=11)))
    _, _, correction, _ = _run((touch, replace(touch, event_id="fix", is_correction=True)))
    _, _, contract, _ = _run((touch, replace(touch, event_id="other", contract_code="ESU6")))
    delayed_provenance = replace(
        _provenance(),
        data_quality=OrderFlowDataQuality.DELAYED,
        entitlement_state=EntitlementState.DELAYED,
    )
    _, _, delayed, delayed_assessment = _run((touch,), provenance=delayed_provenance)

    assert all(
        item.metadata.availability == AnalyticalAvailability.UNAVAILABLE
        for item in (gapped, duplicate, correction, contract)
    )
    assert delayed.levels
    assert delayed.metadata.availability == AnalyticalAvailability.DEGRADED
    assert delayed_assessment.context == ImbalanceContext.UNAVAILABLE


def test_first_touch_watch_ready_continuity_and_replay_order_determinism():
    trades = [
        _trade("pre", -1, 100, 50, AggressorSide.SELL),
        _trade("touch", 1, 100, 10, AggressorSide.BUY),
        _trade("next", 2, 100.25, 10, AggressorSide.BUY),
        _trade("last", 3, 100.5, 10, AggressorSide.BUY),
    ]
    _, watch_window, watch, _ = _run(
        trades,
        location=replace(_location(status="WATCH"), top=100.5),
        through=BASE + pd.Timedelta(seconds=2),
    )
    _, _, ready, expected = _run(
        trades,
        location=replace(_location(status="READY"), top=100.5),
        previous=watch_window,
    )
    shuffled = list(trades)
    random.Random(42).shuffle(shuffled)
    _, _, replay, actual = _run(shuffled)

    assert watch.observation_start == ready.observation_start == BASE + pd.Timedelta(seconds=1)
    assert expected == actual
    assert ready == replay


def test_footprint_does_not_change_authority_delta_or_accept_chart_selection():
    trades = tuple(
        _trade(f"ask-{index}", index + 1, 100 + index * 0.25, 10, AggressorSide.BUY)
        for index in range(3)
    )
    flow, window, _, _ = _run(trades)
    location_before = deepcopy(window.location)
    delta_before = evaluate_delta(flow, window)
    footprint = build_footprint(flow, window)
    evaluate_bid_ask_imbalance(footprint)
    delta_after = evaluate_delta(flow, window)

    assert window.location == location_before
    assert delta_before == delta_after
    assert "chart" not in inspect.signature(build_footprint).parameters
    assert not any(
        hasattr(footprint, name)
        for name in ("recommendation", "confidence", "entry", "stop", "target")
    )


def test_one_optional_confluence_factor_replaces_the_placeholder():
    trades = tuple(
        _trade(f"ask-{index}", index + 1, 100 + index * 0.25, 10, AggressorSide.BUY)
        for index in range(3)
    )
    _, _, _, assessment = _run(trades)
    factor = build_footprint_confluence_factor(assessment)

    assert factor.key == "footprint_imbalance"
    assert factor.required is False
    assert factor.satisfied is True


def test_unavailable_footprint_factor_is_inactive():
    _, _, _, assessment = _run(())
    factor = build_footprint_confluence_factor(assessment)

    assert factor.key == "footprint_imbalance"
    assert factor.active is False
    assert factor.satisfied is None


def test_decision_authority_is_immutable_across_footprint_evaluation(
    ohlc_factory,
):
    analyses = _analyses(ohlc_factory)
    decision = _evaluate_authority(analyses, _session_sweep("bullish"))
    before = deepcopy(decision)
    trades = tuple(
        _trade(f"ask-{index}", index + 1, 100 + index * 0.25, 10, AggressorSide.BUY)
        for index in range(3)
    )

    _run(trades)

    assert decision == before
