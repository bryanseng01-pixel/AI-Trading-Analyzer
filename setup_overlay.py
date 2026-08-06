from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Mapping

import pandas as pd

from analysis_pipeline import TimeframeAnalysis
from decision_authority import AuthorityDecision
from timeframe_roles import Direction


class OverlayLevelRole(str, Enum):
    SETUP = "setup"
    LIQUIDITY = "liquidity"
    CONFIRMATION = "confirmation"
    TRIGGER = "trigger"
    INVALIDATION = "invalidation"
    TARGET = "target"


class OverlayLevelState(str, Enum):
    WAITING_FOR_CLOSE = "waiting_for_close"
    CONFIRMED_BY_CLOSE = "confirmed_by_close"
    WAITING_FOR_SWEEP = "waiting_for_sweep"
    SWEPT_BY_WICK = "swept_by_wick"
    PLACEHOLDER = "placeholder"


class OverlayAnnotationKind(str, Enum):
    CONTEXT = "context"
    WAITING = "waiting"
    LIQUIDITY = "liquidity"
    STRUCTURE = "structure"
    EXECUTION_ZONE = "execution_zone"
    LIMITATION = "limitation"


@dataclass(frozen=True)
class OverlayLevel:
    price: float
    timeframe: str
    role: OverlayLevelRole
    state: OverlayLevelState
    label: str
    event_type: str | None = None
    timestamp: pd.Timestamp | None = None
    source: str | None = None
    importance: str | None = None


@dataclass(frozen=True)
class OverlayZone:
    top: float
    bottom: float
    timeframe: str
    direction: Direction
    label: str
    start_time: pd.Timestamp
    formation_end_time: pd.Timestamp
    source: str
    importance: str | None = None


@dataclass(frozen=True)
class OverlayAnnotation:
    kind: OverlayAnnotationKind
    text: str
    level: OverlayLevel | None = None
    zone: OverlayZone | None = None


@dataclass(frozen=True)
class OverlayVisibility:
    show_context_explanation: bool
    show_primary_waiting_level: bool
    show_liquidity_level: bool
    show_confirmation_level: bool
    show_trigger_level: bool
    show_execution_zone: bool
    show_invalidation_level: bool
    show_target_levels: bool


@dataclass(frozen=True)
class SetupOverlay:
    active_playbook: str
    authority_status: str
    direction: Direction | None
    current_phase: str
    next_required_event: str
    progress_step: int
    total_steps: int
    completion_percentage: float
    primary_waiting_level: OverlayLevel | None
    relevant_liquidity_level: OverlayLevel | None
    confirmation_level_5m: OverlayLevel | None
    trigger_level_1m: OverlayLevel | None
    active_execution_zone: OverlayZone | None
    invalidation_level: OverlayLevel | None
    target_levels: tuple[OverlayLevel, ...]
    annotations: tuple[OverlayAnnotation, ...]
    visibility: OverlayVisibility
    limitations: tuple[str, ...]


# A future OverlayEvent timeline can record ordered setup transitions without
# changing this snapshot contract. Timeline events are intentionally deferred.


def build_setup_overlay(
    authority_decision: AuthorityDecision,
    timeframe_analyses: Mapping[str, TimeframeAnalysis],
    session_levels: Mapping[str, dict[str, Any]],
) -> SetupOverlay:
    """Project authoritative setup state into a chart-ready snapshot."""

    status = authority_decision.recommendation
    direction = authority_decision.roles.context_direction
    phase = authority_decision.playbook["phase"]
    limitations = [
        "Invalidation awaits approved Trade Planner rules.",
        "Targets await approved Trade Planner rules.",
    ]

    confirmed_gates = authority_decision.trade_plan["reasons"]
    missing_gates = authority_decision.trade_plan["missing"]
    progress_step = len(confirmed_gates)
    total_steps = progress_step + len(missing_gates)
    completion_percentage = (
        progress_step / total_steps * 100.0 if total_steps else 0.0
    )

    if status == "AVOID":
        return _avoid_overlay(
            authority_decision,
            progress_step=progress_step,
            total_steps=total_steps,
            completion_percentage=completion_percentage,
            limitations=limitations,
        )

    setup_level = None
    if phase == "waiting_for_setup" and direction is not None:
        setup_level = _pending_structure_level(
            timeframe_analyses["15 Minute"],
            direction,
            timeframe="15M",
            role=OverlayLevelRole.SETUP,
            importance="primary",
        )
        if setup_level is None:
            limitations.append(
                "A reliable pending 15M setup level cannot be derived from "
                "the current structure and labels."
            )

    liquidity_level = None
    if direction is not None and phase not in {
        "waiting_for_context",
        "waiting_for_setup",
    }:
        swept = phase != "waiting_for_liquidity"
        liquidity_level, liquidity_limitation = _select_liquidity_level(
            direction,
            session_levels,
            swept=swept,
            importance=(
                "primary" if phase == "waiting_for_liquidity" else "secondary"
            ),
        )
        if liquidity_limitation:
            limitations.append(liquidity_limitation)

    confirmation_level = None
    if direction is not None and phase in {
        "waiting_for_mss",
        "waiting_for_trigger",
        "waiting_for_execution_zone",
        "execution_zone_available",
    }:
        confirmation_level = _structure_level(
            timeframe_analyses["5 Minute"],
            direction,
            timeframe="5M",
            role=OverlayLevelRole.CONFIRMATION,
            importance=("primary" if phase == "waiting_for_mss" else "secondary"),
        )
        if confirmation_level is None:
            limitations.append(
                "A reliable 5M confirmation level cannot be derived from "
                "the current structure and labels."
            )

    trigger_level = None
    if direction is not None and phase in {
        "waiting_for_trigger",
        "waiting_for_execution_zone",
        "execution_zone_available",
    }:
        trigger_level = _structure_level(
            timeframe_analyses["1 Minute"],
            direction,
            timeframe="1M",
            role=OverlayLevelRole.TRIGGER,
            importance=("primary" if phase == "waiting_for_trigger" else "secondary"),
        )
        if trigger_level is None:
            limitations.append(
                "A reliable 1M trigger level cannot be derived from the "
                "current structure and labels."
            )

    execution_zone = _execution_zone(authority_decision, direction)
    if phase == "waiting_for_execution_zone" and execution_zone is None:
        limitations.append(
            "A future 1M FVG location cannot be calculated before it forms."
        )

    primary_waiting_level = {
        "waiting_for_setup": setup_level,
        "waiting_for_liquidity": liquidity_level,
        "waiting_for_mss": confirmation_level,
        "waiting_for_trigger": trigger_level,
    }.get(phase)

    visibility = _visibility(
        status,
        phase,
        primary_waiting_level=primary_waiting_level,
        liquidity_level=liquidity_level,
        confirmation_level=confirmation_level,
        trigger_level=trigger_level,
        execution_zone=execution_zone,
    )
    annotations = _annotations(
        authority_decision,
        primary_waiting_level=primary_waiting_level,
        liquidity_level=liquidity_level,
        confirmation_level=confirmation_level,
        trigger_level=trigger_level,
        execution_zone=execution_zone,
        visibility=visibility,
    )

    return SetupOverlay(
        active_playbook=authority_decision.playbook["playbook"],
        authority_status=status,
        direction=direction,
        current_phase=phase,
        next_required_event=authority_decision.playbook["next_event"],
        progress_step=progress_step,
        total_steps=total_steps,
        completion_percentage=completion_percentage,
        primary_waiting_level=primary_waiting_level,
        relevant_liquidity_level=liquidity_level,
        confirmation_level_5m=confirmation_level,
        trigger_level_1m=trigger_level,
        active_execution_zone=execution_zone,
        invalidation_level=None,
        target_levels=(),
        annotations=annotations,
        visibility=visibility,
        limitations=tuple(limitations),
    )


def _avoid_overlay(
    decision: AuthorityDecision,
    *,
    progress_step: int,
    total_steps: int,
    completion_percentage: float,
    limitations: list[str],
) -> SetupOverlay:
    visibility = OverlayVisibility(
        show_context_explanation=True,
        show_primary_waiting_level=False,
        show_liquidity_level=False,
        show_confirmation_level=False,
        show_trigger_level=False,
        show_execution_zone=False,
        show_invalidation_level=False,
        show_target_levels=False,
    )
    annotation = OverlayAnnotation(
        kind=OverlayAnnotationKind.CONTEXT,
        text="AVOID — 4H and 1H preliminary context conflicts.",
    )
    return SetupOverlay(
        active_playbook=decision.playbook["playbook"],
        authority_status=decision.recommendation,
        direction=decision.roles.context_direction,
        current_phase=decision.playbook["phase"],
        next_required_event=decision.playbook["next_event"],
        progress_step=progress_step,
        total_steps=total_steps,
        completion_percentage=completion_percentage,
        primary_waiting_level=None,
        relevant_liquidity_level=None,
        confirmation_level_5m=None,
        trigger_level_1m=None,
        active_execution_zone=None,
        invalidation_level=None,
        target_levels=(),
        annotations=(annotation,),
        visibility=visibility,
        limitations=tuple(limitations),
    )


def _latest_break_event(
    analysis: TimeframeAnalysis,
) -> dict[str, Any] | None:
    events: list[tuple[pd.Timestamp, int, dict[str, Any]]] = []
    if analysis.bos is not None:
        events.append((pd.Timestamp(analysis.bos["time"]), 0, analysis.bos))
    if analysis.choch is not None:
        events.append((pd.Timestamp(analysis.choch["time"]), 1, analysis.choch))
    if not events:
        return None
    return max(events, key=lambda item: (item[0], item[1]))[2]


def _structure_level(
    analysis: TimeframeAnalysis,
    direction: Direction,
    *,
    timeframe: str,
    role: OverlayLevelRole,
    importance: str,
) -> OverlayLevel | None:
    event = _latest_break_event(analysis)
    if event is not None and event.get("direction") == direction.value:
        return OverlayLevel(
            price=float(event["level"]),
            timeframe=timeframe,
            role=role,
            state=OverlayLevelState.CONFIRMED_BY_CLOSE,
            label=f'{timeframe} {direction.value} {event.get("text", "BOS/CHoCH")}',
            event_type=event.get("text"),
            timestamp=pd.Timestamp(event["time"]),
            source="latest_close_confirmed_event",
            importance=importance,
        )
    return _pending_structure_level(
        analysis,
        direction,
        timeframe=timeframe,
        role=role,
        importance=importance,
    )


def _pending_structure_level(
    analysis: TimeframeAnalysis,
    direction: Direction,
    *,
    timeframe: str,
    role: OverlayLevelRole,
    importance: str,
) -> OverlayLevel | None:
    label = None
    event_type = None

    if direction == Direction.BULLISH:
        if analysis.structure == "Bearish Structure" and analysis.high_labels:
            label = analysis.high_labels[-1]
            event_type = "CHoCH"
        elif (
            analysis.structure == "Bullish Structure"
            and len(analysis.high_labels) >= 2
        ):
            label = analysis.high_labels[-2]
            event_type = "BOS"
    elif direction == Direction.BEARISH:
        if analysis.structure == "Bullish Structure" and analysis.low_labels:
            label = analysis.low_labels[-1]
            event_type = "CHoCH"
        elif (
            analysis.structure == "Bearish Structure"
            and len(analysis.low_labels) >= 2
        ):
            label = analysis.low_labels[-2]
            event_type = "BOS"

    if label is None:
        return None

    relation = "above" if direction == Direction.BULLISH else "below"
    return OverlayLevel(
        price=float(label[1]),
        timeframe=timeframe,
        role=role,
        state=OverlayLevelState.WAITING_FOR_CLOSE,
        label=(
            f"{timeframe} {direction.value} {event_type}: "
            f"close {relation} {float(label[1]):.2f}"
        ),
        event_type=event_type,
        timestamp=pd.Timestamp(label[0]),
        source="market_structure_labels",
        importance=importance,
    )


def _select_liquidity_level(
    direction: Direction,
    session_levels: Mapping[str, dict[str, Any]],
    *,
    swept: bool,
    importance: str,
) -> tuple[OverlayLevel | None, str | None]:
    side = "low" if direction == Direction.BULLISH else "high"
    time_key = f"{side}_sweep_time" if swept else "end_time"
    swept_key = f"{side}_swept"
    candidates = []

    for session_name, session in session_levels.items():
        if bool(session.get(swept_key, False)) != swept:
            continue
        timestamp = session.get(time_key)
        price = session.get(side)
        if timestamp is None or price is None:
            continue
        candidates.append((pd.Timestamp(timestamp), session_name, float(price)))

    if not candidates:
        state = "swept" if swept else "unswept"
        return None, f"No timestamped {state} relevant session level is available."

    latest_time = max(item[0] for item in candidates)
    latest = [item for item in candidates if item[0] == latest_time]
    if len(latest) != 1:
        return None, "Relevant session levels are ambiguous at the latest timestamp."

    timestamp, session_name, price = latest[0]
    return (
        OverlayLevel(
            price=price,
            timeframe="5M Sessions",
            role=OverlayLevelRole.LIQUIDITY,
            state=(
                OverlayLevelState.SWEPT_BY_WICK
                if swept
                else OverlayLevelState.WAITING_FOR_SWEEP
            ),
            label=(
                f"{session_name} {side.title()} "
                f"{'swept by wick' if swept else 'waiting for sweep'}"
            ),
            timestamp=timestamp,
            source=session_name,
            importance=importance,
        ),
        None,
    )


def _execution_zone(
    decision: AuthorityDecision,
    direction: Direction | None,
) -> OverlayZone | None:
    if direction is None:
        return None
    directional_fvgs = [
        fvg
        for fvg in decision.active_fvgs
        if fvg.get("type") == direction.value
    ]
    if not directional_fvgs:
        return None
    fvg = directional_fvgs[0]
    required = {"top", "bottom", "start_time", "end_time"}
    if not required.issubset(fvg):
        return None
    return OverlayZone(
        top=float(fvg["top"]),
        bottom=float(fvg["bottom"]),
        timeframe="1M",
        direction=direction,
        label=f"Active {direction.value} 1M FVG",
        start_time=pd.Timestamp(fvg["start_time"]),
        formation_end_time=pd.Timestamp(fvg["end_time"]),
        source="authority_filtered_fvg",
        importance="primary",
    )


def _visibility(
    status: str,
    phase: str,
    *,
    primary_waiting_level: OverlayLevel | None,
    liquidity_level: OverlayLevel | None,
    confirmation_level: OverlayLevel | None,
    trigger_level: OverlayLevel | None,
    execution_zone: OverlayZone | None,
) -> OverlayVisibility:
    show_waiting = status in {"WAIT", "WATCH"}
    show_liquidity = liquidity_level is not None
    show_confirmation = confirmation_level is not None
    show_trigger = trigger_level is not None
    show_zone = (
        execution_zone is not None and status in {"WATCH", "READY"}
    )

    if status == "WAIT" and phase != "waiting_for_mss":
        show_confirmation = False
    if status == "WAIT":
        show_trigger = False
        show_zone = False

    return OverlayVisibility(
        show_context_explanation=True,
        show_primary_waiting_level=(
            show_waiting and primary_waiting_level is not None
        ),
        show_liquidity_level=show_liquidity,
        show_confirmation_level=show_confirmation,
        show_trigger_level=show_trigger,
        show_execution_zone=show_zone,
        show_invalidation_level=False,
        show_target_levels=False,
    )


def _annotations(
    decision: AuthorityDecision,
    *,
    primary_waiting_level: OverlayLevel | None,
    liquidity_level: OverlayLevel | None,
    confirmation_level: OverlayLevel | None,
    trigger_level: OverlayLevel | None,
    execution_zone: OverlayZone | None,
    visibility: OverlayVisibility,
) -> tuple[OverlayAnnotation, ...]:
    direction = decision.roles.context_direction
    annotations = [
        OverlayAnnotation(
            kind=OverlayAnnotationKind.CONTEXT,
            text=(
                f"{decision.recommendation} — "
                f"{direction.value if direction else 'conflicting'} "
                f"{decision.playbook['playbook']}"
            ),
        )
    ]

    if visibility.show_liquidity_level and liquidity_level is not None:
        annotations.append(
            OverlayAnnotation(
                kind=OverlayAnnotationKind.LIQUIDITY,
                text=f"{liquidity_level.label} at {liquidity_level.price:.2f}",
                level=liquidity_level,
            )
        )
    if (
        visibility.show_confirmation_level
        and confirmation_level is not None
    ):
        annotations.append(
            OverlayAnnotation(
                kind=OverlayAnnotationKind.STRUCTURE,
                text=confirmation_level.label,
                level=confirmation_level,
            )
        )
    if visibility.show_trigger_level and trigger_level is not None:
        annotations.append(
            OverlayAnnotation(
                kind=OverlayAnnotationKind.STRUCTURE,
                text=trigger_level.label,
                level=trigger_level,
            )
        )
    if visibility.show_execution_zone and execution_zone is not None:
        annotations.append(
            OverlayAnnotation(
                kind=OverlayAnnotationKind.EXECUTION_ZONE,
                text=(
                    f"{execution_zone.label}: {execution_zone.bottom:.2f}–"
                    f"{execution_zone.top:.2f}"
                ),
                zone=execution_zone,
            )
        )
    if (
        visibility.show_primary_waiting_level
        and primary_waiting_level is not None
        and all(item.level is not primary_waiting_level for item in annotations)
    ):
        annotations.append(
            OverlayAnnotation(
                kind=OverlayAnnotationKind.WAITING,
                text=primary_waiting_level.label,
                level=replace(primary_waiting_level, importance="primary"),
            )
        )
    return tuple(annotations)
