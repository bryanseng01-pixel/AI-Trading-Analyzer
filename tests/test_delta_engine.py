from dataclasses import FrozenInstanceError, replace
import random

import pandas as pd
import pytest

from delta_engine import (
    DEFAULT_DELTA_RULES,
    DeltaLocationState,
    DeltaRules,
    PriceProgressDirection,
    build_execution_location_window,
    evaluate_delta,
)
from order_flow_models import (
    AggressorSide,
    AuthorityExecutionLocation,
    DataGap,
    EntitlementState,
    OrderFlowDataQuality,
    OrderFlowWindow,
    TradeEvent,
)
from test_order_flow_architecture import _provenance
from timeframe_roles import Direction


BASE = pd.Timestamp("2026-08-05 14:30:00", tz="UTC")


def _trade(
    event_id,
    seconds,
    price,
    quantity,
    side,
    *,
    contract="NQU6",
    correction=False,
    sequence=None,
):
    return TradeEvent(
        event_id=event_id,
        contract_code=contract,
        exchange_timestamp=BASE + pd.Timedelta(seconds=seconds),
        received_timestamp=BASE + pd.Timedelta(seconds=seconds, milliseconds=2),
        sequence_number=sequence if sequence is not None else int(seconds * 1000),
        price=price,
        quantity=quantity,
        aggressor_side=side,
        aggressor_source="provider_reported",
        is_correction=correction,
    )


def _location(
    *,
    direction=Direction.BULLISH,
    status="READY",
    location_id="fvg-1",
):
    return AuthorityExecutionLocation(
        playbook="ICT Liquidity Sweep Reversal",
        authority_status=status,
        authority_phase="execution_zone_available",
        direction=direction,
        timeframe="1M",
        zone_kind="original_fvg",
        bottom=100.0,
        top=106.0,
        formation_time=BASE,
        source="authority_filtered_fvg",
        location_id=location_id,
        source_contract="NQU6",
    )


def _flow(trades, *, provenance=None, gaps=()):
    return OrderFlowWindow(
        provenance=provenance or _provenance(),
        trades=tuple(trades),
        quotes=(),
        provider_price_levels=(),
        gaps=tuple(gaps),
    )


def _evaluate(
    trades,
    *,
    location=None,
    observed=BASE,
    through=None,
    provenance=None,
    gaps=(),
    previous=None,
    visible=True,
    active=True,
):
    location = location or _location()
    through = through or BASE + pd.Timedelta(seconds=10)
    window = build_execution_location_window(
        location,
        tuple(trades),
        authority_observed_at=observed,
        evaluated_through=through,
        execution_zone_visible=visible,
        location_active=active,
        previous_window=previous,
    )
    return window, evaluate_delta(
        _flow(trades, provenance=provenance, gaps=gaps),
        window,
    )


def test_delta_rules_have_approved_immutable_defaults():
    assert DEFAULT_DELTA_RULES == DeltaRules(
        bucket_interval=pd.Timedelta(seconds=1),
        minimum_classification_coverage=0.90,
        minimum_classified_volume=1.0,
        minimum_price_progress_ticks=1,
    )
    with pytest.raises(FrozenInstanceError):
        DEFAULT_DELTA_RULES.minimum_classification_coverage = 0.5


@pytest.mark.parametrize(
    ("trades", "ask", "bid", "unknown", "delta"),
    (
        (
            (
                _trade("a", 1, 100, 2, AggressorSide.BUY),
                _trade("b", 2, 101, 3, AggressorSide.BUY),
            ),
            5,
            0,
            0,
            5,
        ),
        (
            (
                _trade("a", 1, 101, 2, AggressorSide.SELL),
                _trade("b", 2, 100, 3, AggressorSide.SELL),
            ),
            0,
            5,
            0,
            -5,
        ),
        (
            (
                _trade("a", 1, 100, 5, AggressorSide.BUY),
                _trade("b", 2, 101, 2, AggressorSide.SELL),
                _trade("c", 3, 101, 3, AggressorSide.UNKNOWN),
            ),
            5,
            2,
            3,
            3,
        ),
    ),
)
def test_exact_buy_sell_mixed_and_unknown_arithmetic(
    trades, ask, bid, unknown, delta
):
    _, assessment = _evaluate(trades)
    result = assessment.delta_result

    assert result.total_ask_volume == ask
    assert result.total_bid_volume == bid
    assert result.total_unknown_volume == unknown
    assert result.net_delta == delta
    assert result.classification_coverage == pytest.approx(
        (ask + bid) / (ask + bid + unknown)
    )
    assert sum(bucket.ask_volume for bucket in result.buckets) == ask
    assert sum(bucket.bid_volume for bucket in result.buckets) == bid
    assert sum(bucket.unknown_volume for bucket in result.buckets) == unknown


def test_unknown_never_contributes_to_delta():
    trades = (
        _trade("buy", 1, 100, 9, AggressorSide.BUY),
        _trade("unknown", 2, 101, 1, AggressorSide.UNKNOWN),
    )
    _, assessment = _evaluate(trades)

    assert assessment.delta_result.net_delta == 9
    assert assessment.delta_result.total_unknown_volume == 1
    assert assessment.delta_result.classification_coverage == 0.9
    assert assessment.state == DeltaLocationState.SUPPORTIVE_CONTINUATION


def test_below_ninety_percent_coverage_keeps_raw_but_disables_assessment():
    trades = (
        _trade("buy", 1, 100, 8.9, AggressorSide.BUY),
        _trade("unknown", 2, 101, 1.1, AggressorSide.UNKNOWN),
    )
    _, assessment = _evaluate(trades)

    assert assessment.delta_result.net_delta == 8.9
    assert assessment.delta_result.classification_coverage == pytest.approx(0.89)
    assert assessment.state == DeltaLocationState.UNAVAILABLE
    assert assessment.supportive is None


def test_all_unknown_has_zero_coverage_and_no_directional_assessment():
    _, assessment = _evaluate(
        (_trade("unknown", 1, 100, 5, AggressorSide.UNKNOWN),)
    )

    assert assessment.delta_result.total_unknown_volume == 5
    assert assessment.delta_result.net_delta == 0
    assert assessment.delta_result.classification_coverage == 0
    assert assessment.state == DeltaLocationState.UNAVAILABLE


def test_first_touch_excludes_pretouch_and_includes_zone_boundary():
    trades = (
        _trade("before", -1, 101, 10, AggressorSide.SELL),
        _trade("approach", 1, 99.75, 10, AggressorSide.SELL),
        _trade("touch", 2, 100, 2, AggressorSide.BUY),
        _trade("after", 3, 101, 3, AggressorSide.BUY),
    )
    window, assessment = _evaluate(trades)

    assert window.interaction_start_time == BASE + pd.Timedelta(seconds=2)
    assert assessment.delta_result.total_ask_volume == 5
    assert assessment.delta_result.total_bid_volume == 0


def test_fvg_formation_and_evaluated_through_bound_the_window():
    location = replace(
        _location(),
        formation_time=BASE + pd.Timedelta(seconds=2),
    )
    trades = (
        _trade("before-formation", 1, 100, 20, AggressorSide.SELL),
        _trade("touch", 2, 100, 2, AggressorSide.BUY),
        _trade("after-end", 11, 101, 20, AggressorSide.SELL),
    )
    window, assessment = _evaluate(trades, location=location)

    assert window.start_time == BASE + pd.Timedelta(seconds=2)
    assert assessment.delta_result.total_ask_volume == 2
    assert assessment.delta_result.total_bid_volume == 0


def test_out_of_zone_trades_are_excluded_and_reentries_are_included():
    trades = (
        _trade("touch", 1, 100, 1, AggressorSide.BUY),
        _trade("outside", 2, 107, 50, AggressorSide.SELL),
        _trade("reentry", 3, 102, 2, AggressorSide.BUY),
    )
    _, assessment = _evaluate(trades)

    assert assessment.delta_result.total_ask_volume == 3
    assert assessment.delta_result.total_bid_volume == 0


def test_watch_to_ready_preserves_first_authority_observation_for_same_location():
    trades = (
        _trade("watch-touch", 2, 100, 2, AggressorSide.BUY),
        _trade("ready-trade", 5, 101, 2, AggressorSide.BUY),
    )
    watch_window, _ = _evaluate(
        trades,
        location=_location(status="WATCH"),
        observed=BASE + pd.Timedelta(seconds=1),
        through=BASE + pd.Timedelta(seconds=3),
    )
    ready_window, ready = _evaluate(
        trades,
        location=_location(status="READY"),
        observed=BASE + pd.Timedelta(seconds=4),
        previous=watch_window,
    )

    assert ready_window.authority_observed_at == BASE + pd.Timedelta(seconds=1)
    assert ready_window.interaction_start_time == BASE + pd.Timedelta(seconds=2)
    assert ready.delta_result.total_ask_volume == 4


def test_new_location_id_resets_authority_observation():
    trades = (
        _trade("old", 2, 100, 5, AggressorSide.BUY),
        _trade("new", 5, 101, 2, AggressorSide.BUY),
    )
    old_window, _ = _evaluate(
        trades,
        location=_location(status="WATCH", location_id="old"),
        observed=BASE + pd.Timedelta(seconds=1),
        through=BASE + pd.Timedelta(seconds=3),
    )
    new_window, result = _evaluate(
        trades,
        location=_location(location_id="new"),
        observed=BASE + pd.Timedelta(seconds=4),
        previous=old_window,
    )

    assert new_window.interaction_start_time == BASE + pd.Timedelta(seconds=5)
    assert result.delta_result.total_ask_volume == 2


def test_one_second_buckets_anchor_to_first_touch_and_omit_empty_buckets():
    trades = (
        _trade("a", 1.25, 100, 1, AggressorSide.BUY, sequence=1),
        _trade("b", 1.75, 100.25, 2, AggressorSide.BUY, sequence=2),
        _trade("c", 3.25, 100.5, 3, AggressorSide.SELL, sequence=3),
    )
    _, assessment = _evaluate(trades)
    buckets = assessment.delta_result.buckets

    assert [bucket.start_time for bucket in buckets] == [
        BASE + pd.Timedelta(seconds=1.25),
        BASE + pd.Timedelta(seconds=3.25),
    ]
    assert [bucket.delta for bucket in buckets] == [3, -3]


def test_shuffled_input_is_deterministic():
    trades = [
        _trade("a", 1, 100, 1, AggressorSide.BUY, sequence=1),
        _trade("b", 2, 101, 2, AggressorSide.SELL, sequence=2),
        _trade("c", 3, 102, 4, AggressorSide.BUY, sequence=3),
    ]
    _, expected = _evaluate(trades)
    random.Random(7).shuffle(trades)
    _, actual = _evaluate(trades)

    assert actual == expected


def test_identical_duplicate_is_counted_once():
    trade = _trade("same", 1, 100, 2, AggressorSide.BUY)
    _, assessment = _evaluate((trade, trade))

    assert assessment.delta_result.total_ask_volume == 2


def test_conflicting_duplicate_and_unresolved_correction_fail_closed():
    original = _trade("same", 1, 100, 2, AggressorSide.BUY)
    conflict = replace(original, quantity=3)
    correction = _trade(
        "correction", 2, 101, 2, AggressorSide.BUY, correction=True
    )

    _, duplicate_result = _evaluate((original, conflict))
    _, correction_result = _evaluate((original, correction))

    assert duplicate_result.state == DeltaLocationState.UNAVAILABLE
    assert "duplicate" in duplicate_result.explanation.lower()
    assert correction_result.state == DeltaLocationState.UNAVAILABLE
    assert "correction" in correction_result.explanation.lower()


def test_sequence_gap_affecting_eligible_window_fails_closed():
    gap = DataGap(
        start_time=BASE + pd.Timedelta(seconds=0.5),
        end_time=BASE + pd.Timedelta(seconds=0.75),
        first_missing_sequence=1,
        last_missing_sequence=2,
        reason="synthetic gap",
    )
    _, assessment = _evaluate(
        (_trade("touch", 1, 100, 2, AggressorSide.BUY),),
        gaps=(gap,),
    )

    assert assessment.state == DeltaLocationState.UNAVAILABLE
    assert assessment.delta_result.buckets == ()


@pytest.mark.parametrize(
    ("quality", "entitlement", "keeps_raw"),
    (
        (OrderFlowDataQuality.DELAYED, EntitlementState.DELAYED, True),
        (OrderFlowDataQuality.COMPLETE, EntitlementState.DENIED, False),
        (OrderFlowDataQuality.COMPLETE, EntitlementState.UNKNOWN, False),
    ),
)
def test_delayed_and_entitlement_failures_disable_directional_confluence(
    quality, entitlement, keeps_raw
):
    provenance = replace(
        _provenance(),
        data_quality=quality,
        entitlement_state=entitlement,
    )
    _, assessment = _evaluate(
        (
            _trade("a", 1, 100, 2, AggressorSide.BUY),
            _trade("b", 2, 101, 2, AggressorSide.BUY),
        ),
        provenance=provenance,
    )

    assert assessment.state == DeltaLocationState.UNAVAILABLE
    assert bool(assessment.delta_result.buckets) is keeps_raw


def test_contract_mismatch_fails_closed():
    _, assessment = _evaluate(
        (
            _trade("touch", 1, 100, 2, AggressorSide.BUY),
            _trade("wrong", 2, 101, 2, AggressorSide.BUY, contract="ESU6"),
        )
    )

    assert assessment.state == DeltaLocationState.UNAVAILABLE
    assert "contract" in assessment.explanation.lower()


@pytest.mark.parametrize(
    ("direction", "trades", "expected"),
    (
        (
            Direction.BULLISH,
            (
                _trade("a", 1, 100, 3, AggressorSide.BUY),
                _trade("b", 2, 101, 1, AggressorSide.SELL),
            ),
            DeltaLocationState.SUPPORTIVE_CONTINUATION,
        ),
        (
            Direction.BEARISH,
            (
                _trade("a", 1, 102, 1, AggressorSide.BUY),
                _trade("b", 2, 101, 3, AggressorSide.SELL),
            ),
            DeltaLocationState.SUPPORTIVE_CONTINUATION,
        ),
        (
            Direction.BULLISH,
            (
                _trade("a", 1, 102, 1, AggressorSide.BUY),
                _trade("b", 2, 101, 3, AggressorSide.SELL),
            ),
            DeltaLocationState.OPPOSING_CONTINUATION,
        ),
        (
            Direction.BULLISH,
            (
                _trade("a", 1, 100, 1, AggressorSide.SELL),
                _trade("b", 2, 101, 3, AggressorSide.SELL),
            ),
            DeltaLocationState.MIXED_OR_DIVERGENT,
        ),
    ),
)
def test_conservative_directional_semantics(direction, trades, expected):
    _, assessment = _evaluate(trades, location=_location(direction=direction))

    assert assessment.state == expected
    assert "does not prove absorption" in assessment.explanation


def test_sub_one_tick_progress_is_mixed():
    trades = (
        _trade("a", 1, 100, 3, AggressorSide.BUY),
        _trade("b", 2, 100.125, 1, AggressorSide.SELL),
    )
    _, assessment = _evaluate(trades)

    assert assessment.price_progress_direction == PriceProgressDirection.FLAT
    assert assessment.state == DeltaLocationState.MIXED_OR_DIVERGENT


@pytest.mark.parametrize("status", ("WAIT", "AVOID"))
def test_wait_and_avoid_are_not_applicable(status):
    _, assessment = _evaluate(
        (_trade("touch", 1, 100, 2, AggressorSide.BUY),),
        location=_location(status=status),
    )

    assert assessment.state == DeltaLocationState.UNAVAILABLE
    assert assessment.supportive is None


@pytest.mark.parametrize(("visible", "active"), ((False, True), (True, False)))
def test_hidden_or_inactive_execution_zone_ends_observation(visible, active):
    _, assessment = _evaluate(
        (_trade("touch", 1, 100, 2, AggressorSide.BUY),),
        visible=visible,
        active=active,
    )

    assert assessment.state == DeltaLocationState.UNAVAILABLE
    assert assessment.delta_result.buckets == ()


def test_replay_and_live_snapshots_with_same_events_are_identical():
    trades = (
        _trade("a", 1, 100, 3, AggressorSide.BUY),
        _trade("b", 2, 101, 1, AggressorSide.SELL),
    )
    _, replay = _evaluate(trades)
    _, live = _evaluate(tuple(trades))

    assert replay == live
