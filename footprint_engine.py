from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_HALF_EVEN
from enum import Enum
import math

import pandas as pd

from order_flow_engines import (
    BidAskImbalanceResult,
    FootprintImbalance,
    FootprintLevel,
    FootprintResult,
    ImbalanceContext,
)
from order_flow_models import (
    AggressorSide,
    AnalyticalAvailability,
    EntitlementState,
    ExecutionLocationWindow,
    OrderFlowAnalysisMetadata,
    OrderFlowDataQuality,
    OrderFlowGranularity,
    OrderFlowWindow,
    TradeEvent,
)
from order_flow_integration import (
    CompletedOrderFlowAssessment,
    OrderFlowFactorKey,
    build_order_flow_confluence_factor,
)
from timeframe_roles import Direction


class FootprintGapPolicy(str, Enum):
    FAIL_CLOSED = "fail_closed"


class FootprintDuplicatePolicy(str, Enum):
    DEDUPLICATE_IDENTICAL_EVENT_ID = "deduplicate_identical_event_id"


class FootprintCorrectionPolicy(str, Enum):
    REQUIRE_RESOLVED_EVENTS = "require_resolved_events"


class ImbalanceComparisonMode(str, Enum):
    DIAGONAL_ONLY = "diagonal_only"


class ZeroDenominatorPolicy(str, Enum):
    QUALIFY_WITH_MINIMUM_NUMERATOR = "qualify_with_minimum_numerator"


@dataclass(frozen=True)
class FootprintRules:
    price_alignment_tolerance_ticks: float = 0.000001
    comparison_halo_ticks: int = 1
    minimum_classification_coverage: float = 0.90
    require_trade_level_data: bool = True
    gap_policy: FootprintGapPolicy = FootprintGapPolicy.FAIL_CLOSED
    duplicate_policy: FootprintDuplicatePolicy = (
        FootprintDuplicatePolicy.DEDUPLICATE_IDENTICAL_EVENT_ID
    )
    correction_policy: FootprintCorrectionPolicy = (
        FootprintCorrectionPolicy.REQUIRE_RESOLVED_EVENTS
    )

    def __post_init__(self) -> None:
        if self.price_alignment_tolerance_ticks < 0:
            raise ValueError("price alignment tolerance cannot be negative.")
        if self.comparison_halo_ticks != 1:
            raise ValueError("Version 1 requires exactly one comparison-halo tick.")
        if not 0.0 <= self.minimum_classification_coverage <= 1.0:
            raise ValueError("minimum classification coverage must be in [0, 1].")


@dataclass(frozen=True)
class BidAskImbalanceRules:
    comparison_mode: ImbalanceComparisonMode = ImbalanceComparisonMode.DIAGONAL_ONLY
    imbalance_ratio: float = 3.0
    minimum_numerator_volume: float = 10.0
    zero_denominator_policy: ZeroDenominatorPolicy = (
        ZeroDenominatorPolicy.QUALIFY_WITH_MINIMUM_NUMERATOR
    )
    minimum_stacked_levels: int = 3
    stacked_gap_allowance_ticks: int = 0
    minimum_classification_coverage: float = 0.90

    def __post_init__(self) -> None:
        if self.comparison_mode != ImbalanceComparisonMode.DIAGONAL_ONLY:
            raise ValueError("Version 1 supports diagonal imbalance only.")
        if self.imbalance_ratio != 3.0:
            raise ValueError("Version 1 uses the approved 3.0 imbalance ratio.")
        if self.minimum_numerator_volume != 10.0:
            raise ValueError("Version 1 uses the approved 10-contract minimum.")
        if self.minimum_stacked_levels != 3:
            raise ValueError("Version 1 requires three stacked levels.")
        if self.stacked_gap_allowance_ticks != 0:
            raise ValueError("Version 1 does not allow gaps in a stack.")
        if not 0.0 <= self.minimum_classification_coverage <= 1.0:
            raise ValueError("minimum classification coverage must be in [0, 1].")


DEFAULT_FOOTPRINT_RULES = FootprintRules()
DEFAULT_BID_ASK_IMBALANCE_RULES = BidAskImbalanceRules()


def build_footprint(
    order_flow_window: OrderFlowWindow,
    location_window: ExecutionLocationWindow,
    *,
    rules: FootprintRules = DEFAULT_FOOTPRINT_RULES,
) -> FootprintResult:
    """Aggregate executed TradeEvents by tick around the authority FVG."""

    location = location_window.location
    tick_size = order_flow_window.provenance.contract.instrument.tick_size
    limitations = list(order_flow_window.provenance.limitations)
    fatal = _fatal_quality_reason(order_flow_window, location_window)
    if (
        location.authority_status not in {"WATCH", "READY"}
        or not location.location_id
        or location_window.interaction_start_time is None
    ):
        fatal = fatal or "Footprint requires a touched, visible WATCH/READY authority FVG."

    core_bottom_index, bottom_error = _tick_index(location.bottom, tick_size, rules)
    core_top_index, top_error = _tick_index(location.top, tick_size, rules)
    fatal = fatal or bottom_error or top_error
    core_bottom_index = core_bottom_index or 0
    core_top_index = core_top_index or 0
    footprint_bottom_index = core_bottom_index - rules.comparison_halo_ticks
    footprint_top_index = core_top_index + rules.comparison_halo_ticks

    normalized: tuple[tuple[TradeEvent, int], ...] = ()
    if fatal is None:
        normalized, fatal = _normalize_trades(
            order_flow_window.trades,
            location_window,
            tick_size,
            footprint_bottom_index,
            footprint_top_index,
            rules,
        )
    if fatal is not None:
        limitations.append(fatal)
        return _empty_result(
            order_flow_window,
            location_window,
            tick_size,
            core_bottom_index,
            core_top_index,
            rules,
            tuple(limitations),
        )

    levels = _aggregate_levels(
        normalized,
        tick_size,
        core_bottom_index,
        core_top_index,
        footprint_bottom_index,
        footprint_top_index,
    )
    bid = math.fsum(level.bid_volume for level in levels)
    ask = math.fsum(level.ask_volume for level in levels)
    unknown = math.fsum(level.unknown_volume for level in levels)
    total = bid + ask + unknown
    coverage = (bid + ask) / total if total else 0.0
    quality_failure = None
    provenance = order_flow_window.provenance
    if coverage < rules.minimum_classification_coverage:
        quality_failure = "Aggressor classification coverage is below the 90% minimum."
    if (
        provenance.data_quality == OrderFlowDataQuality.DELAYED
        or provenance.entitlement_state == EntitlementState.DELAYED
    ):
        quality_failure = "Delayed data cannot provide live footprint evidence."
    if provenance.data_quality == OrderFlowDataQuality.DEGRADED:
        quality_failure = quality_failure or "Degraded data cannot provide footprint evidence."
    if quality_failure:
        limitations.append(quality_failure)
    availability = (
        AnalyticalAvailability.DEGRADED
        if quality_failure
        else AnalyticalAvailability.AVAILABLE
    )
    metadata = _metadata(
        order_flow_window,
        location_window,
        availability,
        tuple(limitations),
        (
            f"Aggressor classification coverage is {coverage:.1%}.",
            "Footprint uses normalized executed TradeEvents only.",
        ),
    )
    return FootprintResult(
        metadata=metadata,
        location_id=location.location_id,
        tick_size=tick_size,
        observation_start=location_window.interaction_start_time,
        evaluated_through=location_window.end_time,
        core_bottom=_price(core_bottom_index, tick_size),
        core_top=_price(core_top_index, tick_size),
        footprint_bottom=_price(footprint_bottom_index, tick_size),
        footprint_top=_price(footprint_top_index, tick_size),
        levels=levels,
        total_bid_volume=bid,
        total_ask_volume=ask,
        total_unknown_volume=unknown,
        classification_coverage=coverage,
    )


def evaluate_bid_ask_imbalance(
    footprint: FootprintResult,
    *,
    rules: BidAskImbalanceRules = DEFAULT_BID_ASK_IMBALANCE_RULES,
) -> BidAskImbalanceResult:
    """Interpret completed footprint facts with approved diagonal rules."""

    location = footprint.metadata.location
    if location is None:
        raise ValueError("Footprint imbalance requires authority-location metadata.")
    limitations = list(footprint.metadata.limitations)
    if (
        footprint.metadata.availability != AnalyticalAvailability.AVAILABLE
        or footprint.classification_coverage < rules.minimum_classification_coverage
    ):
        return _unavailable_imbalance(footprint, tuple(limitations))

    levels = {level.tick_index: level for level in footprint.levels}
    detected: list[FootprintImbalance] = []
    for level in footprint.levels:
        if not level.inside_authority_zone:
            continue
        ask_comparison = levels.get(level.tick_index - 1)
        bid_comparison = levels.get(level.tick_index + 1)
        if ask_comparison is not None:
            item = _compare(
                level,
                ask_comparison,
                AggressorSide.BUY,
                level.ask_volume,
                ask_comparison.bid_volume,
                rules,
            )
            if item is not None:
                detected.append(item)
        if bid_comparison is not None:
            item = _compare(
                level,
                bid_comparison,
                AggressorSide.SELL,
                level.bid_volume,
                bid_comparison.ask_volume,
                rules,
            )
            if item is not None:
                detected.append(item)

    ask_runs = _stacked_runs(detected, AggressorSide.BUY, footprint.location_id, rules)
    bid_runs = _stacked_runs(detected, AggressorSide.SELL, footprint.location_id, rules)
    stack_ids = {
        (item.side, item.subject_tick_index): item.stacked_sequence_id
        for run in (*ask_runs, *bid_runs)
        for item in run
    }
    imbalances = tuple(
        replace(
            item,
            stacked_sequence_id=stack_ids.get((item.side, item.subject_tick_index)),
        )
        for item in sorted(detected, key=lambda value: (value.subject_tick_index, value.side.value))
    )
    ask_stacks = _replace_stack_items(ask_runs, imbalances)
    bid_stacks = _replace_stack_items(bid_runs, imbalances)
    context, supportive = _interpret(location.direction, ask_stacks, bid_stacks)
    explanation = _explanation(context)
    return BidAskImbalanceResult(
        metadata=footprint.metadata,
        location_id=footprint.location_id,
        authority_direction=location.direction,
        imbalances=imbalances,
        ask_stacks=ask_stacks,
        bid_stacks=bid_stacks,
        context=context,
        supportive=supportive,
        explanation=explanation,
        limitations=tuple(limitations),
    )


def build_footprint_confluence_factor(assessment: BidAskImbalanceResult):
    """Adapt only the completed assessment; Confluence never sees raw trades."""

    evaluated = assessment.context != ImbalanceContext.UNAVAILABLE
    return build_order_flow_confluence_factor(CompletedOrderFlowAssessment(
        key=OrderFlowFactorKey.FOOTPRINT_IMBALANCE,
        name="Footprint Imbalance",
        metadata=assessment.metadata,
        evaluated=evaluated,
        supportive=assessment.supportive if evaluated else None,
        explanation=assessment.explanation,
    ))


def _compare(
    subject: FootprintLevel,
    comparison: FootprintLevel,
    side: AggressorSide,
    numerator: float,
    denominator: float,
    rules: BidAskImbalanceRules,
) -> FootprintImbalance | None:
    if (
        subject.classification_coverage < rules.minimum_classification_coverage
        or comparison.classification_coverage < rules.minimum_classification_coverage
        or numerator < rules.minimum_numerator_volume
    ):
        return None
    zero = denominator == 0.0
    ratio = None if zero else numerator / denominator
    if not zero and ratio < rules.imbalance_ratio:
        return None
    return FootprintImbalance(
        subject_tick_index=subject.tick_index,
        subject_price=subject.price,
        comparison_tick_index=comparison.tick_index,
        comparison_price=comparison.price,
        side=side,
        numerator_volume=numerator,
        denominator_volume=denominator,
        ratio=ratio,
        zero_denominator=zero,
        stacked_sequence_id=None,
    )


def _stacked_runs(items, side, location_id, rules):
    selected = sorted(
        (item for item in items if item.side == side),
        key=lambda item: item.subject_tick_index,
    )
    groups: list[list[FootprintImbalance]] = []
    for item in selected:
        if not groups or item.subject_tick_index != groups[-1][-1].subject_tick_index + 1:
            groups.append([item])
        else:
            groups[-1].append(item)
    stacks = []
    for group in groups:
        if len(group) < rules.minimum_stacked_levels:
            continue
        stack_id = (
            f"{location_id}:{side.value}:"
            f"{group[0].subject_tick_index}:{group[-1].subject_tick_index}"
        )
        stacks.append(tuple(replace(item, stacked_sequence_id=stack_id) for item in group))
    return tuple(stacks)


def _replace_stack_items(stacks, imbalances):
    by_key = {(item.side, item.subject_tick_index): item for item in imbalances}
    return tuple(
        tuple(by_key[(item.side, item.subject_tick_index)] for item in stack)
        for stack in stacks
    )


def _interpret(direction, ask_stacks, bid_stacks):
    if ask_stacks and bid_stacks:
        return ImbalanceContext.MIXED, False
    aligned = ask_stacks if direction == Direction.BULLISH else bid_stacks
    opposing = bid_stacks if direction == Direction.BULLISH else ask_stacks
    if aligned:
        return ImbalanceContext.SUPPORTIVE_AGGRESSION, True
    if opposing:
        return ImbalanceContext.OPPOSING_AGGRESSION, False
    return ImbalanceContext.NO_STACKED_IMBALANCE, False


def _explanation(context):
    if context == ImbalanceContext.SUPPORTIVE_AGGRESSION:
        return "A directionally aligned stacked diagonal imbalance is present inside the authority FVG."
    if context == ImbalanceContext.OPPOSING_AGGRESSION:
        return "Only opposing stacked diagonal aggression is present inside the authority FVG."
    if context == ImbalanceContext.MIXED:
        return "Both ask- and bid-side stacked diagonal imbalances are present."
    return "No three-level stacked diagonal imbalance is present inside the authority FVG."


def _normalize_trades(trades, window, tick_size, lower, upper, rules):
    start = window.interaction_start_time
    assert start is not None
    eligible = [
        trade for trade in trades
        if start <= pd.Timestamp(trade.exchange_timestamp) <= window.end_time
    ]
    if any(trade.contract_code != window.location.source_contract for trade in eligible):
        return (), "A contract mismatch or change occurs inside the footprint window."
    by_id: dict[str, TradeEvent] = {}
    for trade in eligible:
        existing = by_id.get(trade.event_id)
        if existing is not None and existing != trade:
            return (), "Conflicting duplicate trade event IDs are present."
        by_id[trade.event_id] = trade
    ordered = sorted(
        by_id.values(),
        key=lambda trade: (
            pd.Timestamp(trade.exchange_timestamp),
            trade.sequence_number if trade.sequence_number is not None else math.inf,
            trade.event_id,
        ),
    )
    if any(trade.is_correction for trade in ordered):
        return (), "Unresolved correction events are present."
    normalized = []
    for trade in ordered:
        tick_index, error = _tick_index(trade.price, tick_size, rules)
        if error:
            return (), error
        assert tick_index is not None
        if lower <= tick_index <= upper:
            normalized.append((trade, tick_index))
    return tuple(normalized), None


def _aggregate_levels(trades, tick_size, core_bottom, core_top, lower, upper):
    totals: dict[int, list[float]] = {}
    counts: dict[int, int] = {}
    for trade, tick_index in trades:
        values = totals.setdefault(tick_index, [0.0, 0.0, 0.0])
        if trade.aggressor_side == AggressorSide.BUY:
            values[1] += trade.quantity
        elif trade.aggressor_side == AggressorSide.SELL:
            values[0] += trade.quantity
        else:
            values[2] += trade.quantity
        counts[tick_index] = counts.get(tick_index, 0) + 1
    result = []
    for tick_index in range(lower, upper + 1):
        bid, ask, unknown = totals.get(tick_index, [0.0, 0.0, 0.0])
        total = bid + ask + unknown
        result.append(FootprintLevel(
            tick_index=tick_index,
            price=_price(tick_index, tick_size),
            bid_volume=bid,
            ask_volume=ask,
            unknown_volume=unknown,
            delta=ask - bid,
            trade_count=counts.get(tick_index, 0),
            classification_coverage=(bid + ask) / total if total else 1.0,
            inside_authority_zone=core_bottom <= tick_index <= core_top,
            comparison_only=not core_bottom <= tick_index <= core_top,
        ))
    return tuple(result)


def _tick_index(price, tick_size, rules):
    raw = Decimal(str(price)) / Decimal(str(tick_size))
    nearest = raw.to_integral_value(rounding=ROUND_HALF_EVEN)
    if abs(raw - nearest) > Decimal(str(rules.price_alignment_tolerance_ticks)):
        return None, f"Off-tick price {price} exceeds the approved normalization tolerance."
    return int(nearest), None


def _price(tick_index, tick_size):
    return float(Decimal(tick_index) * Decimal(str(tick_size)))


def _fatal_quality_reason(flow, window):
    provenance = flow.provenance
    if OrderFlowGranularity.TRADE not in provenance.granularities:
        return "Trade-level data is unavailable."
    if not provenance.tick_or_trade_level:
        return "Tick/trade-level provenance is required."
    if provenance.provider_aggregated:
        return "Version 1 footprint accepts TradeEvents only, not provider aggregates."
    if provenance.entitlement_state in {EntitlementState.DENIED, EntitlementState.UNKNOWN}:
        return "Order-flow entitlement is denied or unknown."
    if provenance.data_quality == OrderFlowDataQuality.UNAVAILABLE:
        return "Order-flow data is unavailable."
    if provenance.contract.contract_code != window.location.source_contract:
        return "The authority location contract does not match feed provenance."
    if provenance.data_quality == OrderFlowDataQuality.GAPPED:
        return "Sequence-gapped data fails closed."
    if (
        provenance.start_time > window.start_time
        or provenance.end_time < window.end_time
    ):
        return "Feed provenance does not cover the complete footprint window."
    if any(
        gap.start_time <= window.end_time and gap.end_time >= window.start_time
        for gap in flow.gaps
    ):
        return "A sequence gap affects the eligible footprint window."
    return None


def _metadata(flow, window, availability, limitations, confidence_reasons):
    return OrderFlowAnalysisMetadata(
        engine_name="FootprintEngine",
        engine_version="1",
        provenance=flow.provenance,
        location=window.location,
        evaluated_start_time=window.start_time,
        evaluated_end_time=window.end_time,
        availability=availability,
        limitations=limitations,
        confidence_reasons=confidence_reasons,
    )


def _empty_result(flow, window, tick_size, core_bottom, core_top, rules, limitations):
    metadata = _metadata(
        flow, window, AnalyticalAvailability.UNAVAILABLE, limitations, ()
    )
    location_id = window.location.location_id or ""
    return FootprintResult(
        metadata=metadata,
        location_id=location_id,
        tick_size=tick_size,
        observation_start=window.interaction_start_time,
        evaluated_through=window.end_time,
        core_bottom=_price(core_bottom, tick_size),
        core_top=_price(core_top, tick_size),
        footprint_bottom=_price(core_bottom - rules.comparison_halo_ticks, tick_size),
        footprint_top=_price(core_top + rules.comparison_halo_ticks, tick_size),
        levels=(),
        total_bid_volume=0.0,
        total_ask_volume=0.0,
        total_unknown_volume=0.0,
        classification_coverage=0.0,
    )


def _unavailable_imbalance(footprint, limitations):
    explanation = limitations[-1] if limitations else "Footprint evidence is unavailable."
    return BidAskImbalanceResult(
        metadata=footprint.metadata,
        location_id=footprint.location_id,
        authority_direction=footprint.metadata.location.direction,
        imbalances=(),
        ask_stacks=(),
        bid_stacks=(),
        context=ImbalanceContext.UNAVAILABLE,
        supportive=None,
        explanation=explanation,
        limitations=limitations,
    )
