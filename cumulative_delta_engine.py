from dataclasses import dataclass, replace
from datetime import date, time
from enum import Enum
import math

import pandas as pd

from delta_aggregation import DeltaBucketSeries
from order_flow_engines import (
    CumulativeDeltaPoint,
    CumulativeDeltaResult,
)
from order_flow_models import (
    AnalyticalAvailability,
    EntitlementState,
    ExecutionLocationWindow,
    OrderFlowAnalysisMetadata,
    OrderFlowDataQuality,
    OrderFlowProvenance,
)
from timeframe_roles import Direction


class CumulativeDeltaAnchorKind(str, Enum):
    CURRENT_NEW_YORK_SESSION_OPEN = "current_new_york_session_open"
    CONTRACT_ROLLOVER = "contract_rollover"
    EXPLICIT = "explicit"


class CumulativeGapPolicy(str, Enum):
    FAIL_CLOSED = "fail_closed"


class CumulativeDelayedDataPolicy(str, Enum):
    DIAGNOSTIC_ONLY = "diagnostic_only"


class CumulativeCorrectionPolicy(str, Enum):
    REQUIRE_RESOLVED_BUCKETS = "require_resolved_buckets"


class CumulativeProvenancePolicy(str, Enum):
    REQUIRE_EXACT_MATCH = "require_exact_match"


class CumulativeResetReason(str, Enum):
    SESSION_OPEN = "session_open"
    CONTRACT_ROLLOVER = "contract_rollover"
    EXPLICIT_ANCHOR_CHANGE = "explicit_anchor_change"
    GAP_INVALIDATION = "gap_invalidation"
    ENTITLEMENT_OUTAGE = "entitlement_outage"
    PROVENANCE_CHANGE = "provenance_change"


class CumulativeMovement(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    FLAT = "flat"
    UNAVAILABLE = "unavailable"


class CumulativeDeltaLocationState(str, Enum):
    CONTEXT_AVAILABLE = "context_available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class CumulativeDeltaRules:
    session_timezone: str = "America/New_York"
    session_start_time: time = time(8, 30)
    session_end_time: time = time(17, 0)
    required_bucket_interval: pd.Timedelta = pd.Timedelta(seconds=1)
    gap_policy: CumulativeGapPolicy = CumulativeGapPolicy.FAIL_CLOSED
    delayed_data_policy: CumulativeDelayedDataPolicy = (
        CumulativeDelayedDataPolicy.DIAGNOSTIC_ONLY
    )
    correction_policy: CumulativeCorrectionPolicy = (
        CumulativeCorrectionPolicy.REQUIRE_RESOLVED_BUCKETS
    )
    provenance_policy: CumulativeProvenancePolicy = (
        CumulativeProvenancePolicy.REQUIRE_EXACT_MATCH
    )

    def __post_init__(self) -> None:
        if self.required_bucket_interval <= pd.Timedelta(0):
            raise ValueError("required_bucket_interval must be positive.")


DEFAULT_CUMULATIVE_DELTA_RULES = CumulativeDeltaRules()


@dataclass(frozen=True)
class CumulativeDeltaAnchor:
    anchor_id: str
    kind: CumulativeDeltaAnchorKind
    anchor_time: pd.Timestamp
    session_date: date
    timezone: str
    contract_code: str
    provider_id: str
    starting_value: float
    reason: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.anchor_id or not self.contract_code or not self.provider_id:
            raise ValueError("Cumulative Delta anchor identity is required.")
        if pd.Timestamp(self.anchor_time).tzinfo is None:
            raise ValueError("Cumulative Delta anchor must be timezone-aware.")
        if self.starting_value != 0.0:
            raise ValueError("Version 1 Cumulative Delta must start at zero.")


@dataclass(frozen=True)
class CumulativeDeltaResetEvent:
    timestamp: pd.Timestamp
    reason: CumulativeResetReason
    previous_anchor_id: str | None
    new_anchor_id: str | None
    explanation: str


@dataclass(frozen=True)
class CumulativeDeltaLocationAssessment:
    metadata: OrderFlowAnalysisMetadata
    cumulative_result: CumulativeDeltaResult
    location_id: str
    authority_direction: Direction
    interaction_start_time: pd.Timestamp
    interaction_end_time: pd.Timestamp
    value_before_interaction: float | None
    value_at_interaction_end: float | None
    change_during_interaction: float | None
    pre_location_movement: CumulativeMovement
    interaction_movement: CumulativeMovement
    state: CumulativeDeltaLocationState
    supportive: None
    explanation: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.supportive is not None:
            raise ValueError("Cumulative Delta is descriptive only in Version 1.")


_SESSION_CALENDAR_LIMITATION = (
    "Scheduled New York session boundaries do not account for exchange "
    "holidays or early closes."
)


def build_current_new_york_anchor(
    evaluated_through: pd.Timestamp,
    provenance: OrderFlowProvenance,
    *,
    rules: CumulativeDeltaRules = DEFAULT_CUMULATIVE_DELTA_RULES,
) -> CumulativeDeltaAnchor | None:
    """Build the sole normal Version 1 anchor: today's scheduled 08:30 ET open."""

    evaluated = _aware(evaluated_through, "evaluated_through")
    local = evaluated.tz_convert(rules.session_timezone)
    if local.time() < rules.session_start_time:
        return None
    anchor_time = pd.Timestamp.combine(
        local.date(),
        rules.session_start_time,
    ).tz_localize(rules.session_timezone)
    contract = provenance.contract.contract_code
    provider = provenance.provider.provider_id
    return CumulativeDeltaAnchor(
        anchor_id=f"{contract}:{local.date().isoformat()}:ny-open",
        kind=CumulativeDeltaAnchorKind.CURRENT_NEW_YORK_SESSION_OPEN,
        anchor_time=anchor_time,
        session_date=local.date(),
        timezone=rules.session_timezone,
        contract_code=contract,
        provider_id=provider,
        starting_value=0.0,
        reason="Current scheduled New York session open.",
        limitations=(_SESSION_CALENDAR_LIMITATION,),
    )


def evaluate_cumulative_delta(
    bucket_series: DeltaBucketSeries,
    anchor: CumulativeDeltaAnchor,
    *,
    evaluated_through: pd.Timestamp,
    rules: CumulativeDeltaRules = DEFAULT_CUMULATIVE_DELTA_RULES,
) -> CumulativeDeltaResult:
    """Purely recompute cumulative Delta from an explicit anchor and buckets."""

    evaluated = _aware(evaluated_through, "evaluated_through")
    effective_end = min(evaluated, _session_end(anchor, rules))
    reset_event = _anchor_reset_event(anchor)
    limitations = list(anchor.limitations) + list(bucket_series.limitations)
    fatal, reset_reason = _fatal_series_issue(
        bucket_series,
        anchor,
        effective_end,
        rules,
    )
    if fatal is not None:
        limitations.append(fatal)
        reset_events = (reset_event,)
        if reset_reason is not None:
            reset_events += (
                CumulativeDeltaResetEvent(
                    timestamp=effective_end,
                    reason=reset_reason,
                    previous_anchor_id=anchor.anchor_id,
                    new_anchor_id=None,
                    explanation=fatal,
                ),
            )
        return _unavailable_result(
            bucket_series,
            anchor,
            effective_end,
            tuple(limitations),
            reset_events,
        )

    canonical, canonical_error = _canonical_buckets(
        bucket_series,
        anchor.anchor_time,
        effective_end,
    )
    if canonical_error is not None:
        limitations.append(canonical_error)
        return _unavailable_result(
            bucket_series,
            anchor,
            effective_end,
            tuple(limitations),
            (
                reset_event,
                CumulativeDeltaResetEvent(
                    timestamp=effective_end,
                    reason=CumulativeResetReason.PROVENANCE_CHANGE,
                    previous_anchor_id=anchor.anchor_id,
                    new_anchor_id=None,
                    explanation=canonical_error,
                ),
            ),
        )

    degraded_reasons = []
    if bucket_series.provenance.data_quality in {
        OrderFlowDataQuality.DELAYED,
        OrderFlowDataQuality.DEGRADED,
    } or bucket_series.provenance.entitlement_state == EntitlementState.DELAYED:
        degraded_reasons.append("The cumulative series is delayed or degraded.")
    if (
        bucket_series.classification_coverage
        < bucket_series.minimum_classification_coverage
    ):
        degraded_reasons.append(
            "Aggressor classification coverage is below its Delta-series minimum."
        )
    limitations.extend(degraded_reasons)
    availability = (
        AnalyticalAvailability.DEGRADED
        if degraded_reasons
        else AnalyticalAvailability.AVAILABLE
    )
    metadata = _metadata(
        bucket_series,
        anchor,
        effective_end,
        availability,
        tuple(limitations),
        (
            "The series uses completed deterministic Delta buckets.",
            "Cumulative Delta was recomputed from the explicit zero-based anchor.",
        ),
    )
    running = anchor.starting_value
    points = []
    for bucket in canonical:
        running = math.fsum((running, bucket.delta))
        points.append(
            CumulativeDeltaPoint(
                timestamp=bucket.end_time,
                bucket_delta=bucket.delta,
                cumulative_delta=running,
            )
        )
    return CumulativeDeltaResult(
        metadata=metadata,
        anchor=anchor,
        anchor_time=anchor.anchor_time,
        anchor_reason=anchor.reason,
        starting_value=anchor.starting_value,
        ending_value=running,
        points=tuple(points),
        reset_events=(reset_event,),
        valid_through=points[-1].timestamp if points else anchor.anchor_time,
    )


def assess_cumulative_delta_location(
    result: CumulativeDeltaResult,
    location_window: ExecutionLocationWindow,
    *,
    rules: CumulativeDeltaRules = DEFAULT_CUMULATIVE_DELTA_RULES,
) -> CumulativeDeltaLocationAssessment:
    """Describe cumulative movement without issuing directional support."""

    location = location_window.location
    limitations = list(result.metadata.limitations)
    start = location_window.interaction_start_time
    end = location_window.interaction_end_time
    if (
        result.metadata.availability == AnalyticalAvailability.UNAVAILABLE
        or start is None
        or end is None
        or location.location_id is None
    ):
        limitations.append(
            "A valid cumulative series and touched authority location are required."
        )
        return _unavailable_location_assessment(
            result,
            location_window,
            tuple(limitations),
        )

    before_points = [point for point in result.points if point.timestamp <= start]
    value_before = (
        before_points[-1].cumulative_delta
        if before_points
        else result.starting_value
    )
    complete_points = [
        point
        for point in result.points
        if point.timestamp - rules.required_bucket_interval >= start
        and point.timestamp <= end
    ]
    change = math.fsum(point.bucket_delta for point in complete_points)
    value_at_end = value_before + change
    partial = any(
        point.timestamp > start
        and point.timestamp - rules.required_bucket_interval < start
        or point.timestamp > end
        and point.timestamp - rules.required_bucket_interval < end
        for point in result.points
    )
    if partial:
        limitations.append(
            "Partial interaction-boundary buckets were excluded without estimation."
        )
    if not complete_points:
        limitations.append(
            "No complete one-second buckets fall inside the interaction window."
        )
    state = (
        CumulativeDeltaLocationState.DEGRADED
        if result.metadata.availability == AnalyticalAvailability.DEGRADED
        or partial
        else CumulativeDeltaLocationState.CONTEXT_AVAILABLE
    )
    metadata = replace(
        result.metadata,
        location=location,
        limitations=tuple(limitations),
    )
    return CumulativeDeltaLocationAssessment(
        metadata=metadata,
        cumulative_result=result,
        location_id=location.location_id,
        authority_direction=location.direction,
        interaction_start_time=start,
        interaction_end_time=end,
        value_before_interaction=value_before,
        value_at_interaction_end=value_at_end,
        change_during_interaction=change,
        pre_location_movement=_movement(value_before - result.starting_value),
        interaction_movement=_movement(change),
        state=state,
        supportive=None,
        explanation=(
            "Cumulative Delta movement is descriptive only; no price alignment "
            "or divergence rule is applied."
        ),
        limitations=tuple(limitations),
    )


def _fatal_series_issue(
    series: DeltaBucketSeries,
    anchor: CumulativeDeltaAnchor,
    effective_end: pd.Timestamp,
    rules: CumulativeDeltaRules,
) -> tuple[str | None, CumulativeResetReason | None]:
    provenance = series.provenance
    if anchor.anchor_time > effective_end:
        return "The evaluation time precedes the cumulative anchor.", None
    if series.contract_code != anchor.contract_code or (
        provenance.contract.contract_code != anchor.contract_code
    ):
        return (
            "Contract rollover or mismatch invalidates the anchored series.",
            CumulativeResetReason.CONTRACT_ROLLOVER,
        )
    if provenance.provider.provider_id != anchor.provider_id:
        return (
            "Unexpected provider provenance invalidates the anchored series.",
            CumulativeResetReason.PROVENANCE_CHANGE,
        )
    if series.start_time != anchor.anchor_time or (
        series.bucket_anchor_time != anchor.anchor_time
    ):
        return (
            "The bucket series does not provide exact coverage from its anchor.",
            CumulativeResetReason.PROVENANCE_CHANGE,
        )
    if series.end_time < effective_end:
        return (
            "The bucket series does not cover the complete evaluation range.",
            CumulativeResetReason.GAP_INVALIDATION,
        )
    if series.bucket_interval != rules.required_bucket_interval:
        return "The bucket interval does not match Cumulative Delta rules.", None
    if not series.normalization_complete or not series.duplicates_resolved:
        return "Delta bucket normalization or duplicate resolution is incomplete.", None
    if not series.corrections_resolved:
        return "Unresolved corrections invalidate the cumulative series.", None
    if provenance.entitlement_state in {
        EntitlementState.DENIED,
        EntitlementState.UNKNOWN,
    }:
        return (
            "Order-flow entitlement is denied or unknown.",
            CumulativeResetReason.ENTITLEMENT_OUTAGE,
        )
    if provenance.data_quality in {
        OrderFlowDataQuality.GAPPED,
        OrderFlowDataQuality.UNAVAILABLE,
    }:
        return (
            "Gapped or unavailable data invalidates the cumulative series.",
            CumulativeResetReason.GAP_INVALIDATION,
        )
    if any(
        gap.start_time <= effective_end and gap.end_time >= anchor.anchor_time
        for gap in series.gaps
    ):
        return (
            "A sequence gap affects the anchored cumulative series.",
            CumulativeResetReason.GAP_INVALIDATION,
        )
    return None, None


def _canonical_buckets(
    series: DeltaBucketSeries,
    anchor_time: pd.Timestamp,
    evaluated_through: pd.Timestamp,
) -> tuple[tuple, str | None]:
    by_interval = {}
    for bucket in series.buckets:
        if bucket.start_time < anchor_time or bucket.end_time > evaluated_through:
            continue
        key = (bucket.start_time, bucket.end_time)
        existing = by_interval.get(key)
        if existing is not None and existing != bucket:
            return (), "Conflicting duplicate Delta bucket intervals are present."
        by_interval[key] = bucket
    ordered = tuple(
        sorted(by_interval.values(), key=lambda item: (item.start_time, item.end_time))
    )
    for previous, current in zip(ordered, ordered[1:]):
        if current.start_time < previous.end_time:
            return (), "Overlapping Delta bucket intervals are present."
    return ordered, None


def _metadata(
    series: DeltaBucketSeries,
    anchor: CumulativeDeltaAnchor,
    evaluated_through: pd.Timestamp,
    availability: AnalyticalAvailability,
    limitations: tuple[str, ...],
    confidence_reasons: tuple[str, ...],
) -> OrderFlowAnalysisMetadata:
    return OrderFlowAnalysisMetadata(
        engine_name="CumulativeDeltaEngine",
        engine_version="1",
        provenance=series.provenance,
        location=None,
        evaluated_start_time=anchor.anchor_time,
        evaluated_end_time=evaluated_through,
        availability=availability,
        limitations=limitations,
        confidence_reasons=confidence_reasons,
    )


def _unavailable_result(
    series: DeltaBucketSeries,
    anchor: CumulativeDeltaAnchor,
    evaluated_through: pd.Timestamp,
    limitations: tuple[str, ...],
    reset_events: tuple[CumulativeDeltaResetEvent, ...],
) -> CumulativeDeltaResult:
    metadata = _metadata(
        series,
        anchor,
        evaluated_through,
        AnalyticalAvailability.UNAVAILABLE,
        limitations,
        (),
    )
    return CumulativeDeltaResult(
        metadata=metadata,
        anchor=anchor,
        anchor_time=anchor.anchor_time,
        anchor_reason=anchor.reason,
        starting_value=0.0,
        ending_value=0.0,
        points=(),
        reset_events=reset_events,
        valid_through=None,
    )


def _unavailable_location_assessment(
    result: CumulativeDeltaResult,
    window: ExecutionLocationWindow,
    limitations: tuple[str, ...],
) -> CumulativeDeltaLocationAssessment:
    location = window.location
    timestamp = window.interaction_start_time or window.start_time
    end = window.interaction_end_time or window.end_time
    return CumulativeDeltaLocationAssessment(
        metadata=replace(
            result.metadata,
            location=location,
            availability=AnalyticalAvailability.UNAVAILABLE,
            limitations=limitations,
        ),
        cumulative_result=result,
        location_id=location.location_id or "unavailable",
        authority_direction=location.direction,
        interaction_start_time=timestamp,
        interaction_end_time=end,
        value_before_interaction=None,
        value_at_interaction_end=None,
        change_during_interaction=None,
        pre_location_movement=CumulativeMovement.UNAVAILABLE,
        interaction_movement=CumulativeMovement.UNAVAILABLE,
        state=CumulativeDeltaLocationState.UNAVAILABLE,
        supportive=None,
        explanation=limitations[-1],
        limitations=limitations,
    )


def _anchor_reset_event(anchor: CumulativeDeltaAnchor) -> CumulativeDeltaResetEvent:
    reason = {
        CumulativeDeltaAnchorKind.CURRENT_NEW_YORK_SESSION_OPEN: (
            CumulativeResetReason.SESSION_OPEN
        ),
        CumulativeDeltaAnchorKind.CONTRACT_ROLLOVER: (
            CumulativeResetReason.CONTRACT_ROLLOVER
        ),
        CumulativeDeltaAnchorKind.EXPLICIT: (
            CumulativeResetReason.EXPLICIT_ANCHOR_CHANGE
        ),
    }[anchor.kind]
    return CumulativeDeltaResetEvent(
        timestamp=anchor.anchor_time,
        reason=reason,
        previous_anchor_id=None,
        new_anchor_id=anchor.anchor_id,
        explanation=anchor.reason,
    )


def _session_end(
    anchor: CumulativeDeltaAnchor,
    rules: CumulativeDeltaRules,
) -> pd.Timestamp:
    return pd.Timestamp.combine(
        anchor.session_date,
        rules.session_end_time,
    ).tz_localize(rules.session_timezone)


def _movement(value: float) -> CumulativeMovement:
    if value > 0:
        return CumulativeMovement.POSITIVE
    if value < 0:
        return CumulativeMovement.NEGATIVE
    return CumulativeMovement.FLAT


def _aware(timestamp: pd.Timestamp, name: str) -> pd.Timestamp:
    value = pd.Timestamp(timestamp)
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware.")
    return value
