from dataclasses import dataclass
from enum import Enum

import pandas as pd

from authority_market_story import build_authority_market_story
from decision_authority import AuthorityGateKey
from instrument_pipeline import InstrumentAnalysisBundle
from setup_overlay import OverlayLevelState


class TimelineState(str, Enum):
    COMPLETE = "complete"
    CURRENT = "current"
    FUTURE = "future"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class TopBarView:
    instrument_key: str
    chart_timeframe: str
    authority_status: str
    direction: str
    refreshed_at: pd.Timestamp
    data_state: str


@dataclass(frozen=True)
class AuthoritySummaryView:
    status: str
    direction: str
    playbook: str
    phase: str
    next_event: str
    next_action: str
    confirmed_gates: tuple[str, ...]
    missing_gates: tuple[str, ...]
    market_story: tuple[str, ...]


@dataclass(frozen=True)
class CurrentSetupView:
    stage: str
    waiting_event: str
    next_milestone: str
    pending_optional_evidence: tuple[str, ...]


@dataclass(frozen=True)
class TimelineItemView:
    key: str
    label: str
    state: TimelineState
    timestamp: pd.Timestamp | None
    explanation: str


@dataclass(frozen=True)
class EvidenceItemView:
    key: str
    name: str
    satisfied: bool | None
    active: bool
    explanation: str


@dataclass(frozen=True)
class ExecutionInspectorView:
    available: bool
    instrument_key: str
    zone_type: str | None
    direction: str | None
    formation_time: pd.Timestamp | None
    formation_end_time: pd.Timestamp | None
    top: float | None
    bottom: float | None
    lifecycle: str | None
    authority_purpose: str | None
    location_id: str | None
    ifvg_summary: str
    order_block_summary: str
    premium_discount_summary: str
    volume_profile_summary: str
    evidence: tuple[EvidenceItemView, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class TradingWorkstationView:
    """Completed presentation data; contains no analytical authority."""

    top_bar: TopBarView
    authority: AuthoritySummaryView
    current_setup: CurrentSetupView
    timeline: tuple[TimelineItemView, ...]
    required_gates: tuple[EvidenceItemView, ...]
    optional_evidence: tuple[EvidenceItemView, ...]
    unavailable_evidence: tuple[str, ...]
    execution_inspector: ExecutionInspectorView


_GATE_LABELS = {
    AuthorityGateKey.HTF_CONTEXT: "HTF Context",
    AuthorityGateKey.SETUP_15M: "15M Setup",
    AuthorityGateKey.LIQUIDITY_SWEEP: "Liquidity Sweep",
    AuthorityGateKey.CONFIRMATION_5M: "5M Confirmation",
    AuthorityGateKey.TRIGGER_1M: "1M Trigger",
    AuthorityGateKey.DIRECTIONAL_FVG_1M: "Execution Zone",
}


def build_trading_workstation_view(
    bundle: InstrumentAnalysisBundle,
    *,
    selected_chart_timeframe: str,
    refreshed_at: pd.Timestamp,
) -> TradingWorkstationView:
    """Project one completed instrument bundle into immutable UI data."""

    if selected_chart_timeframe not in bundle.timeframe_analyses:
        raise ValueError("The displayed chart timeframe is not in the bundle.")
    refreshed = pd.Timestamp(refreshed_at)
    if refreshed.tzinfo is None:
        raise ValueError("refreshed_at must be timezone-aware.")

    decision = bundle.authority_decision
    overlay = bundle.setup_overlay
    confluence = bundle.confluence_result
    direction = (
        decision.roles.context_direction.value.title()
        if decision.roles.context_direction is not None
        else "Conflicting"
    )
    required = tuple(
        EvidenceItemView(
            key=gate.key.value,
            name=_GATE_LABELS[gate.key],
            satisfied=gate.satisfied,
            active=True,
            explanation=gate.explanation,
        )
        for gate in decision.gates
    )
    optional = tuple(
        EvidenceItemView(
            key=factor.key,
            name=factor.name,
            satisfied=factor.satisfied,
            active=factor.active,
            explanation=factor.explanation,
        )
        for factor in confluence.implemented_factors
        if not factor.required
    )
    pending_names = tuple(
        factor.name for factor in confluence.pending_future_factors
    )
    return TradingWorkstationView(
        top_bar=TopBarView(
            instrument_key=bundle.instrument.key,
            chart_timeframe=selected_chart_timeframe,
            authority_status=decision.recommendation,
            direction=direction,
            refreshed_at=refreshed,
            data_state=_data_state(bundle),
        ),
        authority=AuthoritySummaryView(
            status=decision.recommendation,
            direction=direction,
            playbook=decision.playbook["playbook"],
            phase=decision.playbook["phase"],
            next_event=decision.playbook["next_event"],
            next_action=decision.trade_plan["next_action"],
            confirmed_gates=tuple(
                item.explanation for item in decision.gates if item.satisfied
            ),
            missing_gates=tuple(
                item.explanation for item in decision.gates if not item.satisfied
            ),
            market_story=tuple(build_authority_market_story(decision.roles)),
        ),
        current_setup=CurrentSetupView(
            stage=decision.playbook["phase"],
            waiting_event=decision.playbook["next_event"],
            next_milestone=decision.trade_plan["next_action"],
            pending_optional_evidence=pending_names,
        ),
        timeline=_timeline(bundle),
        required_gates=required,
        optional_evidence=optional,
        unavailable_evidence=pending_names,
        execution_inspector=_execution_inspector(bundle, optional),
    )


def _data_state(bundle: InstrumentAnalysisBundle) -> str:
    available = sum(
        not analysis.data.empty for analysis in bundle.timeframe_analyses.values()
    )
    if available == len(bundle.timeframe_analyses):
        return "Available"
    if available:
        return "Degraded"
    return "Unavailable"


def _timeline(bundle: InstrumentAnalysisBundle) -> tuple[TimelineItemView, ...]:
    decision = bundle.authority_decision
    gates = {gate.key: gate for gate in decision.gates}
    ordered = tuple(_GATE_LABELS)
    first_missing = next(
        (index for index, key in enumerate(ordered) if not gates[key].satisfied),
        None,
    )
    timestamps = {
        AuthorityGateKey.LIQUIDITY_SWEEP: _level_time(
            bundle.setup_overlay.relevant_liquidity_level, confirmed_only=False
        ),
        AuthorityGateKey.CONFIRMATION_5M: _level_time(
            bundle.setup_overlay.confirmation_level_5m, confirmed_only=True
        ),
        AuthorityGateKey.TRIGGER_1M: _level_time(
            bundle.setup_overlay.trigger_level_1m, confirmed_only=True
        ),
        AuthorityGateKey.DIRECTIONAL_FVG_1M: (
            bundle.setup_overlay.active_execution_zone.formation_end_time
            if bundle.setup_overlay.active_execution_zone is not None
            else None
        ),
    }
    items = []
    for index, key in enumerate(ordered):
        gate = gates[key]
        if gate.satisfied:
            state = TimelineState.COMPLETE
        elif index == first_missing:
            state = TimelineState.CURRENT
        else:
            state = TimelineState.FUTURE
        items.append(TimelineItemView(
            key=key.value,
            label=_GATE_LABELS[key],
            state=state,
            timestamp=timestamps.get(key),
            explanation=gate.explanation,
        ))
    active_optional = any(
        factor.active for factor in bundle.confluence_result.implemented_factors
        if not factor.required
    )
    items.append(TimelineItemView(
        key="optional_confluence",
        label="Optional Confluence",
        state=(TimelineState.COMPLETE if active_optional else TimelineState.UNAVAILABLE),
        timestamp=None,
        explanation="Optional evidence does not change DecisionAuthority.",
    ))
    return tuple(items)


def _level_time(level, *, confirmed_only: bool) -> pd.Timestamp | None:
    if level is None:
        return None
    if confirmed_only and level.state != OverlayLevelState.CONFIRMED_BY_CLOSE:
        return None
    return level.timestamp


def _execution_inspector(
    bundle: InstrumentAnalysisBundle,
    optional: tuple[EvidenceItemView, ...],
) -> ExecutionInspectorView:
    overlay = bundle.setup_overlay
    zone = overlay.active_execution_zone
    if zone is None:
        return ExecutionInspectorView(
            available=False,
            instrument_key=bundle.instrument.key,
            zone_type=None,
            direction=None,
            formation_time=None,
            formation_end_time=None,
            top=None,
            bottom=None,
            lifecycle=None,
            authority_purpose=None,
            location_id=None,
            ifvg_summary=overlay.ifvg_support.explanation,
            order_block_summary=overlay.order_block_support.explanation,
            premium_discount_summary=overlay.premium_discount_support.explanation,
            volume_profile_summary=overlay.volume_profile_support.explanation,
            evidence=optional,
            limitations=overlay.limitations,
        )
    lifecycle = next(
        (
            item.state.value
            for item in bundle.fvg_lifecycle_result.zones
            if item.top == zone.top
            and item.bottom == zone.bottom
            and item.original_direction == zone.direction
        ),
        None,
    )
    return ExecutionInspectorView(
        available=True,
        instrument_key=bundle.instrument.key,
        zone_type=zone.kind.value,
        direction=zone.direction.value,
        formation_time=zone.start_time,
        formation_end_time=zone.formation_end_time,
        top=zone.top,
        bottom=zone.bottom,
        lifecycle=lifecycle,
        authority_purpose=zone.purpose.value,
        location_id=zone.location_id,
        ifvg_summary=overlay.ifvg_support.explanation,
        order_block_summary=overlay.order_block_support.explanation,
        premium_discount_summary=overlay.premium_discount_support.explanation,
        volume_profile_summary=overlay.volume_profile_support.explanation,
        evidence=optional,
        limitations=overlay.limitations,
    )
