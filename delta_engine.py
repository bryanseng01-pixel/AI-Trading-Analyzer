from dataclasses import dataclass
from enum import Enum
import math

import pandas as pd

from delta_aggregation import aggregate_delta_buckets
from order_flow_engines import DeltaBucket, DeltaResult
from order_flow_models import (
    AggressorSide,
    AnalyticalAvailability,
    AuthorityExecutionLocation,
    EntitlementState,
    ExecutionLocationWindow,
    OrderFlowAnalysisMetadata,
    OrderFlowDataQuality,
    OrderFlowGranularity,
    OrderFlowWindow,
    TradeEvent,
)
from timeframe_roles import Direction


class DeltaGapPolicy(str, Enum):
    FAIL_CLOSED = "fail_closed"


class DeltaDuplicatePolicy(str, Enum):
    DEDUPLICATE_IDENTICAL_EVENT_ID = "deduplicate_identical_event_id"


class DeltaCorrectionPolicy(str, Enum):
    REQUIRE_RESOLVED_EVENTS = "require_resolved_events"


class DeltaDirection(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    FLAT = "flat"


class PriceProgressDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


class DeltaLocationState(str, Enum):
    SUPPORTIVE_CONTINUATION = "supportive_continuation"
    OPPOSING_CONTINUATION = "opposing_continuation"
    MIXED_OR_DIVERGENT = "mixed_or_divergent"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class DeltaRules:
    bucket_interval: pd.Timedelta = pd.Timedelta(seconds=1)
    minimum_classification_coverage: float = 0.90
    minimum_classified_volume: float = 1.0
    minimum_price_progress_ticks: int = 1
    gap_policy: DeltaGapPolicy = DeltaGapPolicy.FAIL_CLOSED
    duplicate_policy: DeltaDuplicatePolicy = (
        DeltaDuplicatePolicy.DEDUPLICATE_IDENTICAL_EVENT_ID
    )
    correction_policy: DeltaCorrectionPolicy = (
        DeltaCorrectionPolicy.REQUIRE_RESOLVED_EVENTS
    )

    def __post_init__(self) -> None:
        if self.bucket_interval <= pd.Timedelta(0):
            raise ValueError("bucket_interval must be positive.")
        if not 0.0 <= self.minimum_classification_coverage <= 1.0:
            raise ValueError("minimum_classification_coverage must be in [0, 1].")
        if self.minimum_classified_volume <= 0.0:
            raise ValueError("minimum_classified_volume must be positive.")
        if self.minimum_price_progress_ticks <= 0:
            raise ValueError("minimum_price_progress_ticks must be positive.")


DEFAULT_DELTA_RULES = DeltaRules()


@dataclass(frozen=True)
class DeltaLocationAssessment:
    metadata: OrderFlowAnalysisMetadata
    delta_result: DeltaResult
    authority_direction: Direction
    delta_direction: DeltaDirection
    price_progress_direction: PriceProgressDirection
    first_trade_price: float | None
    last_trade_price: float | None
    price_progress_ticks: float | None
    state: DeltaLocationState
    supportive: bool | None
    explanation: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.state == DeltaLocationState.UNAVAILABLE:
            if self.supportive is not None:
                raise ValueError("Unavailable Delta cannot claim directional support.")
        elif self.supportive is None:
            raise ValueError("Completed Delta assessment requires a support result.")


def build_execution_location_window(
    location: AuthorityExecutionLocation,
    trades: tuple[TradeEvent, ...],
    *,
    authority_observed_at: pd.Timestamp,
    evaluated_through: pd.Timestamp,
    execution_zone_visible: bool,
    location_active: bool,
    previous_window: ExecutionLocationWindow | None = None,
) -> ExecutionLocationWindow:
    """Locate first trade interaction after authority recognizes the FVG."""

    observed = _aware(authority_observed_at, "authority_observed_at")
    evaluated = _aware(evaluated_through, "evaluated_through")
    if location.location_id is None or not location.location_id:
        raise ValueError("Delta observation requires a stable location_id.")
    if (
        previous_window is not None
        and previous_window.location.location_id == location.location_id
        and previous_window.authority_observed_at is not None
    ):
        observed = previous_window.authority_observed_at
    eligible_start = max(pd.Timestamp(location.formation_time), observed)
    if evaluated < eligible_start:
        raise ValueError("evaluated_through cannot precede location eligibility.")

    applicable = (
        location.authority_status in {"WATCH", "READY"}
        and execution_zone_visible
        and location_active
    )
    candidates = (
        _sort_trades(trades)
        if applicable
        else ()
    )
    interactions = tuple(
        trade
        for trade in candidates
        if eligible_start <= pd.Timestamp(trade.exchange_timestamp) <= evaluated
        and location.bottom <= trade.price <= location.top
    )
    return ExecutionLocationWindow(
        location=location,
        start_time=eligible_start,
        end_time=evaluated,
        interaction_start_time=(
            pd.Timestamp(interactions[0].exchange_timestamp)
            if interactions
            else None
        ),
        interaction_end_time=(
            pd.Timestamp(interactions[-1].exchange_timestamp)
            if interactions
            else None
        ),
        authority_observed_at=observed,
    )


def evaluate_delta(
    order_flow_window: OrderFlowWindow,
    location_window: ExecutionLocationWindow,
    *,
    rules: DeltaRules = DEFAULT_DELTA_RULES,
) -> DeltaLocationAssessment:
    """Calculate location-only Delta, then assess it conservatively."""

    location = location_window.location
    base_limitations = list(order_flow_window.provenance.limitations)
    fatal = _fatal_quality_reason(order_flow_window, location_window)
    applicable = (
        location.authority_status in {"WATCH", "READY"}
        and location.location_id is not None
        and location_window.interaction_start_time is not None
    )
    if not applicable:
        fatal = fatal or "Delta requires a touched, visible WATCH/READY authority FVG."

    normalized: tuple[TradeEvent, ...] = ()
    if fatal is None:
        normalized, normalization_error = _normalize_eligible_trades(
            order_flow_window.trades,
            location_window,
        )
        fatal = normalization_error
    if fatal is not None:
        base_limitations.append(fatal)
        return _unavailable_assessment(
            order_flow_window,
            location_window,
            tuple(base_limitations),
        )

    buckets = _build_buckets(normalized, location_window, rules)
    ask = math.fsum(bucket.ask_volume for bucket in buckets)
    bid = math.fsum(bucket.bid_volume for bucket in buckets)
    unknown = math.fsum(bucket.unknown_volume for bucket in buckets)
    classified = ask + bid
    total = classified + unknown
    coverage = classified / total if total else 0.0
    net_delta = ask - bid

    quality_reasons = [
        f"Aggressor classification coverage is {coverage:.1%}.",
        "Delta uses normalized in-zone trades only.",
    ]
    quality_failure = None
    if classified < rules.minimum_classified_volume:
        quality_failure = (
            "Classified volume is below the minimum required for assessment."
        )
    elif coverage < rules.minimum_classification_coverage:
        quality_failure = (
            "Aggressor classification coverage is below the 90% minimum."
        )

    delayed = (
        order_flow_window.provenance.data_quality == OrderFlowDataQuality.DELAYED
        or order_flow_window.provenance.entitlement_state == EntitlementState.DELAYED
    )
    if delayed:
        quality_failure = "Delayed data cannot provide live directional confluence."
    availability = (
        AnalyticalAvailability.DEGRADED
        if quality_failure is not None
        or order_flow_window.provenance.data_quality == OrderFlowDataQuality.DEGRADED
        else AnalyticalAvailability.AVAILABLE
    )
    limitations = tuple(base_limitations + ([quality_failure] if quality_failure else []))
    metadata = _metadata(
        order_flow_window,
        location_window,
        availability,
        limitations,
        tuple(quality_reasons),
    )
    delta_result = DeltaResult(
        metadata=metadata,
        buckets=buckets,
        total_ask_volume=ask,
        total_bid_volume=bid,
        total_unknown_volume=unknown,
        net_delta=net_delta,
        classification_coverage=coverage,
    )
    if quality_failure is not None:
        return DeltaLocationAssessment(
            metadata=metadata,
            delta_result=delta_result,
            authority_direction=location.direction,
            delta_direction=_delta_direction(net_delta),
            price_progress_direction=PriceProgressDirection.FLAT,
            first_trade_price=normalized[0].price if normalized else None,
            last_trade_price=normalized[-1].price if normalized else None,
            price_progress_ticks=None,
            state=DeltaLocationState.UNAVAILABLE,
            supportive=None,
            explanation=quality_failure,
            limitations=limitations,
        )

    first_price = normalized[0].price
    last_price = normalized[-1].price
    progress_ticks = (
        last_price - first_price
    ) / order_flow_window.provenance.contract.instrument.tick_size
    progress_direction = _price_progress_direction(progress_ticks, rules)
    delta_direction = _delta_direction(net_delta)
    state = _location_state(
        location.direction,
        delta_direction,
        progress_direction,
    )
    supportive = state == DeltaLocationState.SUPPORTIVE_CONTINUATION
    return DeltaLocationAssessment(
        metadata=metadata,
        delta_result=delta_result,
        authority_direction=location.direction,
        delta_direction=delta_direction,
        price_progress_direction=progress_direction,
        first_trade_price=first_price,
        last_trade_price=last_price,
        price_progress_ticks=progress_ticks,
        state=state,
        supportive=supportive,
        explanation=(
            f"Delta is {delta_direction.value}; in-zone price progress is "
            f"{progress_direction.value}. Raw Delta does not prove absorption, "
            "exhaustion, or divergence."
        ),
        limitations=limitations,
    )


def _normalize_eligible_trades(
    trades: tuple[TradeEvent, ...],
    window: ExecutionLocationWindow,
) -> tuple[tuple[TradeEvent, ...], str | None]:
    location = window.location
    start = window.interaction_start_time
    if start is None:
        return (), "The authority execution FVG has not been touched."
    eligible = [
        trade
        for trade in trades
        if start <= pd.Timestamp(trade.exchange_timestamp) <= window.end_time
    ]
    if any(trade.contract_code != window.location.source_contract for trade in eligible):
        return (), "A contract mismatch or change occurs inside the Delta window."
    by_id: dict[str, TradeEvent] = {}
    for trade in eligible:
        existing = by_id.get(trade.event_id)
        if existing is not None and existing != trade:
            return (), "Conflicting duplicate trade event IDs are present."
        by_id[trade.event_id] = trade
    normalized = _sort_trades(tuple(by_id.values()))
    if any(trade.is_correction for trade in normalized):
        return (), "Unresolved correction events are present."
    return (
        tuple(
            trade
            for trade in normalized
            if location.bottom <= trade.price <= location.top
        ),
        None,
    )


def _build_buckets(
    trades: tuple[TradeEvent, ...],
    window: ExecutionLocationWindow,
    rules: DeltaRules,
) -> tuple[DeltaBucket, ...]:
    start = window.interaction_start_time
    assert start is not None
    return aggregate_delta_buckets(
        trades,
        bucket_anchor_time=start,
        evaluated_through=window.end_time,
        bucket_interval=rules.bucket_interval,
    )


def _fatal_quality_reason(
    flow: OrderFlowWindow,
    location_window: ExecutionLocationWindow,
) -> str | None:
    provenance = flow.provenance
    if OrderFlowGranularity.TRADE not in provenance.granularities:
        return "Trade-level data is unavailable."
    if provenance.entitlement_state in {EntitlementState.DENIED, EntitlementState.UNKNOWN}:
        return "Order-flow entitlement is denied or unknown."
    if provenance.data_quality == OrderFlowDataQuality.UNAVAILABLE:
        return "Order-flow data is unavailable."
    if provenance.contract.contract_code != location_window.location.source_contract:
        return "The authority location contract does not match feed provenance."
    if provenance.data_quality == OrderFlowDataQuality.GAPPED:
        return "Sequence-gapped data fails closed."
    eligible_start = location_window.start_time
    if any(
        gap.start_time <= location_window.end_time
        and gap.end_time >= eligible_start
        for gap in flow.gaps
    ):
        return "A sequence gap affects the eligible Delta window."
    return None


def _metadata(
    flow: OrderFlowWindow,
    window: ExecutionLocationWindow,
    availability: AnalyticalAvailability,
    limitations: tuple[str, ...],
    confidence_reasons: tuple[str, ...],
) -> OrderFlowAnalysisMetadata:
    return OrderFlowAnalysisMetadata(
        engine_name="DeltaEngine",
        engine_version="1",
        provenance=flow.provenance,
        location=window.location,
        evaluated_start_time=window.start_time,
        evaluated_end_time=window.end_time,
        availability=availability,
        limitations=limitations,
        confidence_reasons=confidence_reasons,
    )


def _unavailable_assessment(
    flow: OrderFlowWindow,
    window: ExecutionLocationWindow,
    limitations: tuple[str, ...],
) -> DeltaLocationAssessment:
    metadata = _metadata(
        flow,
        window,
        AnalyticalAvailability.UNAVAILABLE,
        limitations,
        (),
    )
    raw = DeltaResult(metadata, (), 0.0, 0.0, 0.0, 0.0, 0.0)
    return DeltaLocationAssessment(
        metadata=metadata,
        delta_result=raw,
        authority_direction=window.location.direction,
        delta_direction=DeltaDirection.FLAT,
        price_progress_direction=PriceProgressDirection.FLAT,
        first_trade_price=None,
        last_trade_price=None,
        price_progress_ticks=None,
        state=DeltaLocationState.UNAVAILABLE,
        supportive=None,
        explanation=limitations[-1],
        limitations=limitations,
    )


def _sort_trades(trades: tuple[TradeEvent, ...]) -> tuple[TradeEvent, ...]:
    return tuple(
        sorted(
            trades,
            key=lambda trade: (
                pd.Timestamp(trade.exchange_timestamp),
                trade.sequence_number if trade.sequence_number is not None else math.inf,
                trade.event_id,
            ),
        )
    )


def _delta_direction(delta: float) -> DeltaDirection:
    if delta > 0:
        return DeltaDirection.POSITIVE
    if delta < 0:
        return DeltaDirection.NEGATIVE
    return DeltaDirection.FLAT


def _price_progress_direction(
    ticks: float,
    rules: DeltaRules,
) -> PriceProgressDirection:
    if ticks >= rules.minimum_price_progress_ticks:
        return PriceProgressDirection.UP
    if ticks <= -rules.minimum_price_progress_ticks:
        return PriceProgressDirection.DOWN
    return PriceProgressDirection.FLAT


def _location_state(
    authority: Direction,
    delta: DeltaDirection,
    price: PriceProgressDirection,
) -> DeltaLocationState:
    if (
        authority == Direction.BULLISH
        and delta == DeltaDirection.POSITIVE
        and price == PriceProgressDirection.UP
    ) or (
        authority == Direction.BEARISH
        and delta == DeltaDirection.NEGATIVE
        and price == PriceProgressDirection.DOWN
    ):
        return DeltaLocationState.SUPPORTIVE_CONTINUATION
    if (
        authority == Direction.BULLISH
        and delta == DeltaDirection.NEGATIVE
        and price == PriceProgressDirection.DOWN
    ) or (
        authority == Direction.BEARISH
        and delta == DeltaDirection.POSITIVE
        and price == PriceProgressDirection.UP
    ):
        return DeltaLocationState.OPPOSING_CONTINUATION
    return DeltaLocationState.MIXED_OR_DIVERGENT


def _aware(timestamp: pd.Timestamp, name: str) -> pd.Timestamp:
    value = pd.Timestamp(timestamp)
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware.")
    return value
