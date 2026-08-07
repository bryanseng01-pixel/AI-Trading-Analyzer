from dataclasses import FrozenInstanceError, fields, replace

import pandas as pd
import pytest

from confluence import evaluate_confluence
from cumulative_delta_engine import (
    DEFAULT_CUMULATIVE_DELTA_RULES,
    CumulativeDeltaAnchor,
    CumulativeDeltaAnchorKind,
    CumulativeDeltaLocationAssessment,
    CumulativeDeltaLocationState,
    CumulativeDeltaRules,
    CumulativeMovement,
    CumulativeResetReason,
    assess_cumulative_delta_location,
    build_current_new_york_anchor,
    evaluate_cumulative_delta,
)
from delta_aggregation import (
    DeltaBucketSeries,
    aggregate_delta_buckets,
    build_delta_bucket_series,
)
from order_flow_engines import DeltaBucket
from order_flow_models import (
    AggressorSide,
    AnalyticalAvailability,
    DataGap,
    EntitlementState,
    ExecutionLocationWindow,
    OrderFlowDataQuality,
)
from setup_overlay import build_setup_overlay
from test_decision_authority import _analyses, _evaluate as _authority_evaluate
from test_delta_engine import _location, _trade
from test_order_flow_architecture import _provenance
from test_setup_overlay import _add_execution_fvg, _sessions


ANCHOR = pd.Timestamp("2026-08-05 08:30", tz="America/New_York")
EVALUATED = pd.Timestamp("2026-08-05 10:30", tz="America/New_York")


def _anchor(*, kind=CumulativeDeltaAnchorKind.CURRENT_NEW_YORK_SESSION_OPEN):
    reason = {
        CumulativeDeltaAnchorKind.CURRENT_NEW_YORK_SESSION_OPEN: "NY session open",
        CumulativeDeltaAnchorKind.CONTRACT_ROLLOVER: "Explicit contract rollover",
        CumulativeDeltaAnchorKind.EXPLICIT: "Explicit anchor change",
    }[kind]
    return CumulativeDeltaAnchor(
        anchor_id=f"NQU6:2026-08-05:{kind.value}",
        kind=kind,
        anchor_time=ANCHOR,
        session_date=ANCHOR.date(),
        timezone="America/New_York",
        contract_code="NQU6",
        provider_id="fake",
        starting_value=0.0,
        reason=reason,
        limitations=("Synthetic calendar fixture.",),
    )


def _bucket(index, delta, *, start=None, end=None):
    start = start or ANCHOR + pd.Timedelta(seconds=index)
    end = end or start + pd.Timedelta(seconds=1)
    ask = max(float(delta), 0.0)
    bid = max(float(-delta), 0.0)
    if delta == 0:
        ask = bid = 1.0
    return DeltaBucket(
        start_time=start,
        end_time=end,
        ask_volume=ask,
        bid_volume=bid,
        unknown_volume=0.0,
        delta=float(delta),
        total_classified_volume=ask + bid,
    )


def _series(
    deltas=(1, -2, 3),
    *,
    buckets=None,
    provenance=None,
    gaps=(),
    coverage=1.0,
    normalized=True,
    duplicates=True,
    corrections=True,
    contract="NQU6",
):
    provenance = provenance or _provenance()
    buckets = tuple(buckets) if buckets is not None else tuple(
        _bucket(index, delta) for index, delta in enumerate(deltas)
    )
    return DeltaBucketSeries(
        provenance=provenance,
        series_id="ny-session-series",
        contract_code=contract,
        start_time=ANCHOR,
        end_time=EVALUATED,
        bucket_interval=pd.Timedelta(seconds=1),
        bucket_anchor_time=ANCHOR,
        buckets=buckets,
        total_ask_volume=sum(bucket.ask_volume for bucket in buckets),
        total_bid_volume=sum(bucket.bid_volume for bucket in buckets),
        total_unknown_volume=sum(bucket.unknown_volume for bucket in buckets),
        classification_coverage=coverage,
        minimum_classification_coverage=0.90,
        normalization_complete=normalized,
        duplicates_resolved=duplicates,
        corrections_resolved=corrections,
        gaps=tuple(gaps),
        limitations=(),
    )


def _evaluate(series=None, *, anchor=None, through=EVALUATED):
    return evaluate_cumulative_delta(
        series or _series(),
        anchor or _anchor(),
        evaluated_through=through,
    )


def test_rules_are_immutable_and_hold_only_approved_parameters():
    assert DEFAULT_CUMULATIVE_DELTA_RULES == CumulativeDeltaRules()
    assert DEFAULT_CUMULATIVE_DELTA_RULES.session_start_time.hour == 8
    assert DEFAULT_CUMULATIVE_DELTA_RULES.session_start_time.minute == 30
    assert DEFAULT_CUMULATIVE_DELTA_RULES.required_bucket_interval == (
        pd.Timedelta(seconds=1)
    )
    with pytest.raises(FrozenInstanceError):
        DEFAULT_CUMULATIVE_DELTA_RULES.session_timezone = "UTC"


def test_current_new_york_anchor_is_exactly_0830_and_zero_based():
    anchor = build_current_new_york_anchor(EVALUATED, _provenance())

    assert anchor.anchor_time == ANCHOR
    assert anchor.starting_value == 0.0
    assert anchor.kind == CumulativeDeltaAnchorKind.CURRENT_NEW_YORK_SESSION_OPEN
    assert anchor.contract_code == "NQU6"


def test_no_fallback_anchor_before_0830():
    evaluated = pd.Timestamp("2026-08-05 08:29:59", tz="America/New_York")

    assert build_current_new_york_anchor(evaluated, _provenance()) is None


def test_new_session_creates_a_distinct_zero_based_anchor():
    next_day = pd.Timestamp("2026-08-06 10:00", tz="America/New_York")
    next_anchor = build_current_new_york_anchor(next_day, _provenance())

    assert next_anchor.anchor_time == pd.Timestamp(
        "2026-08-06 08:30", tz="America/New_York"
    )
    assert next_anchor.anchor_id != _anchor().anchor_id
    assert next_anchor.starting_value == 0.0


@pytest.mark.parametrize(
    ("deltas", "expected_points", "ending"),
    (
        ((1, 2, 3), (1, 3, 6), 6),
        ((-1, -2, -3), (-1, -3, -6), -6),
        ((3, -3, 0), (3, 0, 0), 0),
    ),
)
def test_running_accumulation_is_exact_for_positive_negative_and_flat_sequences(
    deltas, expected_points, ending
):
    result = _evaluate(_series(deltas))

    assert tuple(point.cumulative_delta for point in result.points) == expected_points
    assert tuple(point.timestamp for point in result.points) == tuple(
        ANCHOR + pd.Timedelta(seconds=index + 1)
        for index in range(len(deltas))
    )
    assert result.starting_value == 0.0
    assert result.ending_value == ending
    assert result.ending_value == sum(point.bucket_delta for point in result.points)


def test_shared_aggregation_excludes_unknown_from_delta_without_redistribution():
    trades = (
        _trade("buy", -7199, 100, 3, AggressorSide.BUY, sequence=1),
        _trade("sell", -7198, 100, 1, AggressorSide.SELL, sequence=2),
        _trade("unknown", -7198, 100, 5, AggressorSide.UNKNOWN, sequence=3),
    )
    buckets = aggregate_delta_buckets(
        trades,
        bucket_anchor_time=ANCHOR,
        evaluated_through=ANCHOR + pd.Timedelta(seconds=3),
        bucket_interval=pd.Timedelta(seconds=1),
    )

    assert sum(bucket.ask_volume for bucket in buckets) == 3
    assert sum(bucket.bid_volume for bucket in buckets) == 1
    assert sum(bucket.unknown_volume for bucket in buckets) == 5
    assert sum(bucket.delta for bucket in buckets) == 2


def test_bucket_series_builder_uses_shared_arithmetic():
    trades = (
        _trade("buy", -7199, 100, 3, AggressorSide.BUY, sequence=1),
        _trade("sell", -7198, 100, 1, AggressorSide.SELL, sequence=2),
    )
    series = build_delta_bucket_series(
        trades,
        provenance=_provenance(),
        series_id="session",
        start_time=ANCHOR,
        evaluated_through=ANCHOR + pd.Timedelta(seconds=3),
        bucket_interval=pd.Timedelta(seconds=1),
        minimum_classification_coverage=0.90,
        normalization_complete=True,
        duplicates_resolved=True,
        corrections_resolved=True,
    )
    result = _evaluate(
        replace(series, end_time=EVALUATED),
        through=ANCHOR + pd.Timedelta(seconds=3),
    )

    assert result.ending_value == 2


def test_out_of_order_and_identical_duplicate_buckets_are_deterministic():
    first = _bucket(0, 1)
    second = _bucket(1, 2)
    expected = _evaluate(_series(buckets=(first, second)))
    actual = _evaluate(_series(buckets=(second, first, first)))

    assert actual == expected


def test_conflicting_duplicate_and_overlapping_buckets_fail_closed():
    original = _bucket(0, 1)
    conflict = replace(original, delta=2)
    overlap = _bucket(
        1,
        1,
        start=ANCHOR + pd.Timedelta(milliseconds=500),
        end=ANCHOR + pd.Timedelta(seconds=1, milliseconds=500),
    )

    duplicate_result = _evaluate(_series(buckets=(original, conflict)))
    overlap_result = _evaluate(_series(buckets=(original, overlap)))

    assert duplicate_result.metadata.availability == AnalyticalAvailability.UNAVAILABLE
    assert overlap_result.metadata.availability == AnalyticalAvailability.UNAVAILABLE


def test_buckets_before_anchor_and_after_evaluation_are_excluded():
    buckets = (
        _bucket(-1, 100),
        _bucket(0, 1),
        _bucket(10, 100),
    )
    result = _evaluate(
        _series(buckets=buckets),
        through=ANCHOR + pd.Timedelta(seconds=2),
    )

    assert result.ending_value == 1


def test_new_session_and_explicit_anchor_reset_to_zero():
    session_result = _evaluate(_series((5,)))
    explicit_result = _evaluate(
        _series((2,)),
        anchor=_anchor(kind=CumulativeDeltaAnchorKind.EXPLICIT),
    )

    assert session_result.reset_events[0].reason == CumulativeResetReason.SESSION_OPEN
    assert explicit_result.reset_events[0].reason == (
        CumulativeResetReason.EXPLICIT_ANCHOR_CHANGE
    )
    assert session_result.starting_value == explicit_result.starting_value == 0
    assert session_result.ending_value == 5
    assert explicit_result.ending_value == 2


def test_sequence_gap_invalidates_whole_series_instead_of_midseries_reset():
    gap = DataGap(
        start_time=ANCHOR + pd.Timedelta(seconds=1),
        end_time=ANCHOR + pd.Timedelta(seconds=2),
        first_missing_sequence=10,
        last_missing_sequence=20,
        reason="synthetic gap",
    )
    result = _evaluate(_series(gaps=(gap,)))

    assert result.metadata.availability == AnalyticalAvailability.UNAVAILABLE
    assert result.points == ()
    assert result.ending_value == 0
    assert result.reset_events[-1].reason == CumulativeResetReason.GAP_INVALIDATION


def test_contract_rollover_never_carries_prior_value():
    result = _evaluate(_series(contract="NQZ6"))

    assert result.metadata.availability == AnalyticalAvailability.UNAVAILABLE
    assert result.ending_value == 0
    assert result.reset_events[-1].reason == CumulativeResetReason.CONTRACT_ROLLOVER


def test_new_rollover_contract_starts_a_fresh_zero_based_series():
    provenance = _provenance()
    contract = replace(provenance.contract, contract_code="NQZ6")
    provenance = replace(provenance, contract=contract)
    series = _series((4,), provenance=provenance, contract="NQZ6")
    anchor = replace(
        _anchor(kind=CumulativeDeltaAnchorKind.CONTRACT_ROLLOVER),
        anchor_id="NQZ6:rollover",
        contract_code="NQZ6",
    )
    result = _evaluate(series, anchor=anchor)

    assert result.metadata.availability == AnalyticalAvailability.AVAILABLE
    assert result.starting_value == 0.0
    assert result.ending_value == 4
    assert result.reset_events[0].reason == CumulativeResetReason.CONTRACT_ROLLOVER


@pytest.mark.parametrize("entitlement", (EntitlementState.DENIED, EntitlementState.UNKNOWN))
def test_entitlement_failure_invalidates_series(entitlement):
    provenance = replace(_provenance(), entitlement_state=entitlement)
    result = _evaluate(_series(provenance=provenance))

    assert result.metadata.availability == AnalyticalAvailability.UNAVAILABLE
    assert result.reset_events[-1].reason == CumulativeResetReason.ENTITLEMENT_OUTAGE


def test_delayed_or_low_coverage_series_remains_degraded_diagnostic():
    delayed = replace(
        _provenance(),
        data_quality=OrderFlowDataQuality.DELAYED,
        entitlement_state=EntitlementState.DELAYED,
    )
    delayed_result = _evaluate(_series(provenance=delayed))
    coverage_result = _evaluate(_series(coverage=0.89))

    assert delayed_result.ending_value == 2
    assert coverage_result.ending_value == 2
    assert delayed_result.metadata.availability == AnalyticalAvailability.DEGRADED
    assert coverage_result.metadata.availability == AnalyticalAvailability.DEGRADED


@pytest.mark.parametrize(
    "series",
    (
        _series(normalized=False),
        _series(duplicates=False),
        _series(corrections=False),
    ),
)
def test_unresolved_normalization_duplicate_or_correction_state_fails(series):
    result = _evaluate(series)

    assert result.metadata.availability == AnalyticalAvailability.UNAVAILABLE
    assert result.points == ()


def test_unexpected_provider_provenance_fails_closed():
    anchor = replace(_anchor(), provider_id="another-provider")
    result = _evaluate(anchor=anchor)

    assert result.metadata.availability == AnalyticalAvailability.UNAVAILABLE
    assert result.reset_events[-1].reason == CumulativeResetReason.PROVENANCE_CHANGE


def test_historical_live_and_replay_chunk_assembly_have_identical_output():
    buckets = tuple(_bucket(index, delta) for index, delta in enumerate((1, -2, 4)))
    historical = _evaluate(_series(buckets=buckets))
    live = _evaluate(_series(buckets=buckets[:1] + buckets[1:]))
    replay = _evaluate(_series(buckets=tuple(reversed(buckets))))

    assert historical == live == replay


def _location_window(*, status="READY", location_id="fvg-1", start=1, end=4):
    location = replace(
        _location(status=status, location_id=location_id),
        formation_time=ANCHOR,
    )
    return ExecutionLocationWindow(
        location=location,
        start_time=ANCHOR,
        end_time=EVALUATED,
        interaction_start_time=ANCHOR + pd.Timedelta(seconds=start),
        interaction_end_time=ANCHOR + pd.Timedelta(seconds=end),
        authority_observed_at=ANCHOR,
    )


def test_location_assessment_is_descriptive_only():
    result = _evaluate(_series((1, 2, -1, 3, -5)))
    assessment = assess_cumulative_delta_location(
        result,
        _location_window(),
    )

    assert assessment.value_before_interaction == 1
    assert assessment.change_during_interaction == 4
    assert assessment.value_at_interaction_end == 5
    assert assessment.pre_location_movement == CumulativeMovement.POSITIVE
    assert assessment.interaction_movement == CumulativeMovement.POSITIVE
    assert assessment.supportive is None
    assert "descriptive only" in assessment.explanation


def test_partial_interaction_buckets_are_excluded_without_estimation():
    result = _evaluate(_series((1, 2, 3, 4)))
    window = _location_window(start=1, end=3)
    window = replace(
        window,
        interaction_start_time=ANCHOR + pd.Timedelta(seconds=1, milliseconds=500),
        interaction_end_time=ANCHOR + pd.Timedelta(seconds=3, milliseconds=500),
    )
    assessment = assess_cumulative_delta_location(result, window)

    assert assessment.change_during_interaction == 3
    assert assessment.state == CumulativeDeltaLocationState.DEGRADED
    assert "Partial" in " ".join(assessment.limitations)


def test_watch_to_ready_same_location_preserves_descriptive_assessment():
    result = _evaluate(_series((1, 2, 3, 4)))
    watch = assess_cumulative_delta_location(
        result,
        _location_window(status="WATCH"),
    )
    ready = assess_cumulative_delta_location(
        result,
        _location_window(status="READY"),
    )

    assert watch.location_id == ready.location_id
    assert watch.change_during_interaction == ready.change_during_interaction
    assert watch.supportive is ready.supportive is None


def test_untouched_location_is_unavailable():
    window = replace(
        _location_window(),
        interaction_start_time=None,
        interaction_end_time=None,
    )
    assessment = assess_cumulative_delta_location(_evaluate(), window)

    assert assessment.state == CumulativeDeltaLocationState.UNAVAILABLE
    assert assessment.supportive is None


def test_placeholder_remains_inactive_and_authority_is_unchanged(ohlc_factory):
    analyses = _analyses(ohlc_factory)
    analyses["1 Minute"] = _add_execution_fvg(analyses["1 Minute"])
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=True)
    decision = _authority_evaluate(analyses, sessions)
    original = decision
    overlay = build_setup_overlay(decision, analyses, sessions)
    result = evaluate_confluence(decision, overlay)

    placeholder = next(
        item
        for item in result.pending_future_factors
        if item.key == "cumulative_delta_context"
    )
    assert placeholder.implemented is False
    assert placeholder.active is False
    assert placeholder.satisfied is None
    assert decision == original


def test_chart_selector_is_not_an_input_to_cumulative_engine(ohlc_factory):
    analyses = _analyses(ohlc_factory)
    snapshots = set()
    for selected in analyses:
        assert analyses[selected] is not None
        result = _evaluate(_series((1, -2, 4)))
        snapshots.add((result.ending_value, result.anchor.anchor_id))

    assert snapshots == {(3.0, _anchor().anchor_id)}


def test_models_have_no_recommendation_or_trade_projection_outputs():
    forbidden = {
        "recommendation",
        "confidence_score",
        "probability",
        "score",
        "entry",
        "stop",
        "target",
        "divergence",
    }

    assert forbidden.isdisjoint(
        field.name for field in fields(CumulativeDeltaLocationAssessment)
    )
