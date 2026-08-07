from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Mapping

import pandas as pd

from analysis_pipeline import TimeframeAnalysis
from decision_authority import AuthorityDecision
from fvg_lifecycle import (
    FvgLifecycle,
    FvgLifecycleResult,
    FvgLifecycleState,
    ImbalanceKind,
)
from order_block_engine import (
    OrderBlockResult,
    select_relevant_order_block,
)
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
    OPTIONAL_CONFLUENCE = "optional_confluence"
    LIMITATION = "limitation"


class OverlayZoneKind(str, Enum):
    ORIGINAL_FVG = "original_fvg"
    IFVG = "ifvg"
    ORDER_BLOCK = "order_block"


class OverlayZonePurpose(str, Enum):
    AUTHORITY_REQUIRED = "authority_required"
    OPTIONAL_CONFLUENCE = "optional_confluence"


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
    kind: OverlayZoneKind = OverlayZoneKind.ORIGINAL_FVG
    purpose: OverlayZonePurpose = OverlayZonePurpose.AUTHORITY_REQUIRED
    inversion_time: pd.Timestamp | None = None


@dataclass(frozen=True)
class IfvgOverlaySupport:
    """Optional IFVG evidence projected against the authority FVG zone."""

    applicable: bool
    evaluated: bool
    supporting_zone: OverlayZone | None
    overlap_bottom: float | None
    overlap_top: float | None
    overlap_percentage: float | None
    explanation: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.overlap_percentage is not None and not (
            0.0 <= self.overlap_percentage <= 1.0
        ):
            raise ValueError("overlap_percentage must be between 0.0 and 1.0.")
        if self.supporting_zone is not None:
            if not self.applicable or not self.evaluated:
                raise ValueError("A supporting IFVG must be applicable and evaluated.")
            if self.supporting_zone.kind != OverlayZoneKind.IFVG:
                raise ValueError("IFVG support requires an IFVG overlay zone.")
            if (
                self.supporting_zone.purpose
                != OverlayZonePurpose.OPTIONAL_CONFLUENCE
            ):
                raise ValueError("IFVG support must remain optional confluence.")
            if None in {
                self.overlap_bottom,
                self.overlap_top,
                self.overlap_percentage,
            }:
                raise ValueError("A supporting IFVG requires overlap geometry.")
        elif any(
            value is not None
            for value in (
                self.overlap_bottom,
                self.overlap_top,
                self.overlap_percentage,
            )
        ):
            raise ValueError("Overlap geometry requires a supporting IFVG.")


@dataclass(frozen=True)
class OrderBlockOverlaySupport:
    """Optional Order Block evidence projected against the authority FVG."""

    applicable: bool
    evaluated: bool
    supporting_zone: OverlayZone | None
    overlap_bottom: float | None
    overlap_top: float | None
    overlap_percentage: float | None
    explanation: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.overlap_percentage is not None and not (
            0.0 <= self.overlap_percentage <= 1.0
        ):
            raise ValueError("overlap_percentage must be between 0.0 and 1.0.")
        if self.supporting_zone is not None:
            if not self.applicable or not self.evaluated:
                raise ValueError(
                    "A supporting Order Block must be applicable and evaluated."
                )
            if self.supporting_zone.kind != OverlayZoneKind.ORDER_BLOCK:
                raise ValueError("Order Block support requires an Order Block zone.")
            if (
                self.supporting_zone.purpose
                != OverlayZonePurpose.OPTIONAL_CONFLUENCE
            ):
                raise ValueError("Order Block support must remain optional.")
            if None in {
                self.overlap_bottom,
                self.overlap_top,
                self.overlap_percentage,
            }:
                raise ValueError("Order Block support requires overlap geometry.")
        elif any(
            value is not None
            for value in (
                self.overlap_bottom,
                self.overlap_top,
                self.overlap_percentage,
            )
        ):
            raise ValueError("Overlap geometry requires a supporting Order Block.")


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
    show_optional_ifvg_zone: bool
    show_optional_order_block_zone: bool
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
    ifvg_support: IfvgOverlaySupport
    order_block_support: OrderBlockOverlaySupport
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
    *,
    fvg_lifecycle_result: FvgLifecycleResult | None = None,
    minimum_ifvg_size: float | None = None,
    order_block_result: OrderBlockResult | None = None,
) -> SetupOverlay:
    """Project authoritative setup state into a chart-ready snapshot."""

    status = authority_decision.recommendation
    direction = authority_decision.roles.context_direction
    phase = authority_decision.playbook["phase"]
    limitations = [
        "Invalidation awaits approved Trade Planner rules.",
        "Targets await approved Trade Planner rules.",
    ]

    progress_step = sum(gate.satisfied for gate in authority_decision.gates)
    total_steps = len(authority_decision.gates)
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
    ifvg_support = _build_ifvg_support(
        status=status,
        direction=direction,
        execution_zone=execution_zone,
        execution_zone_visible=visibility.show_execution_zone,
        lifecycle_result=fvg_lifecycle_result,
        minimum_size=minimum_ifvg_size,
    )
    limitations.extend(ifvg_support.limitations)
    visibility = replace(
        visibility,
        show_optional_ifvg_zone=(ifvg_support.supporting_zone is not None),
    )
    order_block_support = _build_order_block_support(
        status=status,
        direction=direction,
        execution_zone=execution_zone,
        execution_zone_visible=visibility.show_execution_zone,
        result=order_block_result,
    )
    limitations.extend(order_block_support.limitations)
    visibility = replace(
        visibility,
        show_optional_order_block_zone=(
            order_block_support.supporting_zone is not None
        ),
    )
    annotations = _annotations(
        authority_decision,
        primary_waiting_level=primary_waiting_level,
        liquidity_level=liquidity_level,
        confirmation_level=confirmation_level,
        trigger_level=trigger_level,
        execution_zone=execution_zone,
        ifvg_support=ifvg_support,
        order_block_support=order_block_support,
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
        ifvg_support=ifvg_support,
        order_block_support=order_block_support,
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
        show_optional_ifvg_zone=False,
        show_optional_order_block_zone=False,
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
        ifvg_support=_inactive_ifvg_support(
            "IFVG confluence is not applicable while authority status is AVOID."
        ),
        order_block_support=_inactive_order_block_support(
            "Order Block confluence is not applicable while authority status is AVOID."
        ),
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
        kind=OverlayZoneKind.ORIGINAL_FVG,
        purpose=OverlayZonePurpose.AUTHORITY_REQUIRED,
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
        show_optional_ifvg_zone=False,
        show_optional_order_block_zone=False,
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
    ifvg_support: IfvgOverlaySupport,
    order_block_support: OrderBlockOverlaySupport,
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
    if (
        visibility.show_optional_order_block_zone
        and order_block_support.supporting_zone is not None
    ):
        zone = order_block_support.supporting_zone
        annotations.append(
            OverlayAnnotation(
                kind=OverlayAnnotationKind.OPTIONAL_CONFLUENCE,
                text=(
                    f"Optional Order Block overlap: {zone.bottom:.2f}–"
                    f"{zone.top:.2f}"
                ),
                zone=zone,
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
        visibility.show_optional_ifvg_zone
        and ifvg_support.supporting_zone is not None
    ):
        zone = ifvg_support.supporting_zone
        annotations.append(
            OverlayAnnotation(
                kind=OverlayAnnotationKind.OPTIONAL_CONFLUENCE,
                text=(
                    f"Optional IFVG overlap: {zone.bottom:.2f}–"
                    f"{zone.top:.2f}"
                ),
                zone=zone,
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


def _build_ifvg_support(
    *,
    status: str,
    direction: Direction | None,
    execution_zone: OverlayZone | None,
    execution_zone_visible: bool,
    lifecycle_result: FvgLifecycleResult | None,
    minimum_size: float | None,
) -> IfvgOverlaySupport:
    applicable = (
        status in {"WATCH", "READY"}
        and direction is not None
        and execution_zone is not None
        and execution_zone_visible
    )
    if not applicable:
        return _inactive_ifvg_support(
            "IFVG confluence requires a visible authority execution FVG."
        )
    if lifecycle_result is None:
        return IfvgOverlaySupport(
            applicable=True,
            evaluated=False,
            supporting_zone=None,
            overlap_bottom=None,
            overlap_top=None,
            overlap_percentage=None,
            explanation="IFVG lifecycle data was not supplied.",
            limitations=("IFVG support cannot be evaluated without 1M lifecycle data.",),
        )
    if _normalized_timeframe(lifecycle_result.timeframe) != "1m":
        return IfvgOverlaySupport(
            applicable=True,
            evaluated=False,
            supporting_zone=None,
            overlap_bottom=None,
            overlap_top=None,
            overlap_percentage=None,
            explanation="The supplied lifecycle result is not 1M execution data.",
            limitations=("IFVG support requires a 1M lifecycle result.",),
        )
    if minimum_size is None:
        return IfvgOverlaySupport(
            applicable=True,
            evaluated=False,
            supporting_zone=None,
            overlap_bottom=None,
            overlap_top=None,
            overlap_percentage=None,
            explanation="The existing FVG size threshold was not supplied.",
            limitations=("IFVG support requires the existing FVG size threshold.",),
        )

    candidates = []
    for zone in lifecycle_result.active_ifvgs:
        overlap = _ifvg_overlap(execution_zone, zone)
        if (
            zone.kind == ImbalanceKind.IFVG
            and zone.state == FvgLifecycleState.INVERTED
            and zone.active
            and zone.current_direction == direction
            and zone.invalidation_time is None
            and zone.size >= minimum_size
            and overlap is not None
        ):
            overlap_bottom, overlap_top = overlap
            overlap_size = overlap_top - overlap_bottom
            candidates.append(
                (
                    zone,
                    overlap_bottom,
                    overlap_top,
                    overlap_size,
                )
            )

    if not candidates:
        return IfvgOverlaySupport(
            applicable=True,
            evaluated=True,
            supporting_zone=None,
            overlap_bottom=None,
            overlap_top=None,
            overlap_percentage=None,
            explanation=(
                "No active directional 1M IFVG overlaps the authority execution FVG."
            ),
            limitations=tuple(lifecycle_result.limitations),
        )

    authority_midpoint = (execution_zone.top + execution_zone.bottom) / 2.0
    selected = min(
        candidates,
        key=lambda item: (
            -item[3],
            abs(((item[0].top + item[0].bottom) / 2.0) - authority_midpoint),
            -(item[0].inversion_time.value if item[0].inversion_time else -1),
            -item[0].formation_time.value,
            item[0].original_direction.value,
            item[0].bottom,
            item[0].top,
        ),
    )
    zone, overlap_bottom, overlap_top, _ = selected
    overlap_percentage = (
        (overlap_top - overlap_bottom)
        / (execution_zone.top - execution_zone.bottom)
    )
    inversion_time = zone.inversion_time
    if inversion_time is None:
        raise ValueError("An active IFVG must have an inversion timestamp.")
    overlay_zone = OverlayZone(
        top=zone.top,
        bottom=zone.bottom,
        timeframe="1M",
        direction=zone.current_direction,
        label=f"Optional {zone.current_direction.value} 1M IFVG confluence",
        start_time=inversion_time,
        formation_end_time=inversion_time,
        source="fvg_lifecycle",
        importance="secondary",
        kind=OverlayZoneKind.IFVG,
        purpose=OverlayZonePurpose.OPTIONAL_CONFLUENCE,
        inversion_time=inversion_time,
    )
    return IfvgOverlaySupport(
        applicable=True,
        evaluated=True,
        supporting_zone=overlay_zone,
        overlap_bottom=overlap_bottom,
        overlap_top=overlap_top,
        overlap_percentage=overlap_percentage,
        explanation="An active directional 1M IFVG overlaps the authority FVG.",
        limitations=tuple(lifecycle_result.limitations),
    )


def _inactive_ifvg_support(explanation: str) -> IfvgOverlaySupport:
    return IfvgOverlaySupport(
        applicable=False,
        evaluated=False,
        supporting_zone=None,
        overlap_bottom=None,
        overlap_top=None,
        overlap_percentage=None,
        explanation=explanation,
        limitations=(),
    )


def _ifvg_overlap(
    execution_zone: OverlayZone,
    ifvg: FvgLifecycle,
) -> tuple[float, float] | None:
    overlap_bottom = max(execution_zone.bottom, ifvg.bottom)
    overlap_top = min(execution_zone.top, ifvg.top)
    if overlap_top <= overlap_bottom:
        return None
    return overlap_bottom, overlap_top


def _normalized_timeframe(timeframe: str) -> str:
    normalized = timeframe.strip().lower().replace(" ", "")
    if normalized in {"1m", "1min", "1minute"}:
        return "1m"
    return normalized


def _build_order_block_support(
    *,
    status: str,
    direction: Direction | None,
    execution_zone: OverlayZone | None,
    execution_zone_visible: bool,
    result: OrderBlockResult | None,
) -> OrderBlockOverlaySupport:
    applicable = (
        status in {"WATCH", "READY"}
        and direction is not None
        and execution_zone is not None
        and execution_zone_visible
    )
    if not applicable:
        return _inactive_order_block_support(
            "Order Block confluence requires a visible authority execution FVG."
        )
    if result is None:
        return OrderBlockOverlaySupport(
            applicable=True,
            evaluated=False,
            supporting_zone=None,
            overlap_bottom=None,
            overlap_top=None,
            overlap_percentage=None,
            explanation="Order Block analysis was not supplied.",
            limitations=(
                "Order Block support cannot be evaluated without a 1M result.",
            ),
        )
    if _normalized_timeframe(result.timeframe) != "1m":
        return OrderBlockOverlaySupport(
            applicable=True,
            evaluated=False,
            supporting_zone=None,
            overlap_bottom=None,
            overlap_top=None,
            overlap_percentage=None,
            explanation="The supplied Order Block result is not 1M execution data.",
            limitations=("Order Block support requires a 1M result.",),
        )

    selected = select_relevant_order_block(
        result,
        direction=direction,
        authority_zone_bottom=execution_zone.bottom,
        authority_zone_top=execution_zone.top,
    )
    if selected is None:
        return OrderBlockOverlaySupport(
            applicable=True,
            evaluated=True,
            supporting_zone=None,
            overlap_bottom=None,
            overlap_top=None,
            overlap_percentage=None,
            explanation=(
                "No active directional 1M Order Block overlaps the authority FVG."
            ),
            limitations=result.limitations,
        )

    overlap_bottom = max(execution_zone.bottom, selected.bottom)
    overlap_top = min(execution_zone.top, selected.top)
    overlap_percentage = (
        (overlap_top - overlap_bottom)
        / (execution_zone.top - execution_zone.bottom)
    )
    zone = OverlayZone(
        top=selected.top,
        bottom=selected.bottom,
        timeframe="1M",
        direction=selected.direction,
        label=f"Optional {selected.direction.value} 1M Order Block confluence",
        start_time=selected.formation_time,
        formation_end_time=selected.formation_time,
        source="order_block_engine",
        importance="secondary",
        kind=OverlayZoneKind.ORDER_BLOCK,
        purpose=OverlayZonePurpose.OPTIONAL_CONFLUENCE,
    )
    return OrderBlockOverlaySupport(
        applicable=True,
        evaluated=True,
        supporting_zone=zone,
        overlap_bottom=overlap_bottom,
        overlap_top=overlap_top,
        overlap_percentage=overlap_percentage,
        explanation="An active directional 1M Order Block overlaps the authority FVG.",
        limitations=result.limitations,
    )


def _inactive_order_block_support(
    explanation: str,
) -> OrderBlockOverlaySupport:
    return OrderBlockOverlaySupport(
        applicable=False,
        evaluated=False,
        supporting_zone=None,
        overlap_bottom=None,
        overlap_top=None,
        overlap_percentage=None,
        explanation=explanation,
        limitations=(),
    )
