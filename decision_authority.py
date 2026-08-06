from dataclasses import dataclass
from typing import Any, Mapping

from analysis_pipeline import TimeframeAnalysis, select_active_fvgs
from timeframe_roles import (
    Direction,
    SetupState,
    TimeframeRoleState,
    evaluate_timeframe_roles,
)


@dataclass(frozen=True)
class AuthorityDecision:
    """The one final recommendation exposed by the application."""

    recommendation: str
    roles: TimeframeRoleState
    active_fvgs: list[dict[str, Any]]
    trade_plan: dict[str, Any]
    playbook: dict[str, Any]


class DecisionAuthority:
    """Gate the final recommendation through approved timeframe roles."""

    def evaluate(
        self,
        analyses: Mapping[str, TimeframeAnalysis],
        session_levels: Mapping[str, dict[str, Any]],
        *,
        minimum_fvg_size: float,
        maximum_fvgs: int,
    ) -> AuthorityDecision:
        roles = evaluate_timeframe_roles(analyses)
        active_fvgs = select_active_fvgs(
            analyses["1 Minute"],
            minimum_size=minimum_fvg_size,
            maximum_count=maximum_fvgs,
        )
        direction = roles.context_direction
        direction_value = direction.value if direction is not None else None
        directional_fvgs = [
            fvg
            for fvg in active_fvgs
            if fvg["type"] == direction_value
        ]
        liquidity_swept = _relevant_liquidity_swept(
            direction,
            session_levels,
        )

        status = _recommendation_status(
            roles,
            liquidity_swept=liquidity_swept,
            execution_fvg_available=bool(directional_fvgs),
        )
        trade_plan = _build_trade_plan_view(
            roles,
            status=status,
            liquidity_swept=liquidity_swept,
            execution_fvg_available=bool(directional_fvgs),
            session_levels=session_levels,
        )
        playbook = _build_playbook_view(
            roles,
            status=status,
            liquidity_swept=liquidity_swept,
            execution_fvg_available=bool(directional_fvgs),
            reasons=trade_plan["reasons"],
            missing=trade_plan["missing"],
        )

        return AuthorityDecision(
            recommendation=status,
            roles=roles,
            active_fvgs=active_fvgs,
            trade_plan=trade_plan,
            playbook=playbook,
        )


def _relevant_liquidity_swept(
    direction: Direction | None,
    session_levels: Mapping[str, dict[str, Any]],
) -> bool:
    if direction == Direction.BULLISH:
        return any(
            session.get("low_swept", False)
            for session in session_levels.values()
        )
    if direction == Direction.BEARISH:
        return any(
            session.get("high_swept", False)
            for session in session_levels.values()
        )
    return False


def _recommendation_status(
    roles: TimeframeRoleState,
    *,
    liquidity_swept: bool,
    execution_fvg_available: bool,
) -> str:
    if roles.context_direction is None:
        return "AVOID"
    if roles.setup_state == SetupState.UNCONFIRMED:
        return "WAIT"
    if not liquidity_swept:
        return "WAIT"
    if (
        roles.setup_state == SetupState.COUNTERTREND_PULLBACK
        and not roles.confirmation_aligned
    ):
        return "WAIT"
    if not roles.confirmation_aligned:
        return "WATCH"
    if not roles.trigger_aligned or not execution_fvg_available:
        return "WATCH"
    return "READY"


def _build_trade_plan_view(
    roles: TimeframeRoleState,
    *,
    status: str,
    liquidity_swept: bool,
    execution_fvg_available: bool,
    session_levels: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    reasons: list[str] = []
    missing: list[str] = []
    direction = roles.context_direction

    if direction is None:
        missing.append("Aligned 4H and 1H context")
    else:
        reasons.append(
            f"The 4H and 1H context is aligned {direction.value}."
        )

    if roles.setup_state == SetupState.ALIGNED_CONTINUATION:
        reasons.append("The 15M setup supports continuation.")
    elif roles.setup_state == SetupState.COUNTERTREND_PULLBACK:
        reasons.append("The 15M setup is a countertrend pullback.")
    else:
        missing.append("Reliable 15M setup structure")

    if liquidity_swept:
        reasons.append("Relevant session liquidity has been swept by a wick.")
    else:
        missing.append("Relevant session liquidity sweep")

    if roles.confirmation_aligned:
        reasons.append("A close-confirmed 5M BOS/CHoCH aligns with context.")
    else:
        missing.append("Aligned close-confirmed 5M BOS/CHoCH")

    if roles.trigger_aligned:
        reasons.append("A close-confirmed 1M BOS/CHoCH trigger aligns.")
    else:
        missing.append("Aligned close-confirmed 1M BOS/CHoCH")

    if execution_fvg_available:
        reasons.append("A directional active 1M FVG is available.")
    else:
        missing.append("Directional active 1M FVG")

    confidence = _gate_confidence(
        roles,
        liquidity_swept=liquidity_swept,
        execution_fvg_available=execution_fvg_available,
    )
    bias = direction.value.title() if direction is not None else "Neutral / Conflicting"
    bullish_points = confidence if direction == Direction.BULLISH else 0
    bearish_points = confidence if direction == Direction.BEARISH else 0

    next_actions = {
        "AVOID": "Higher-timeframe context conflicts. Avoid forcing a directional trade.",
        "WAIT": "The setup is still developing. Wait for the next required gate.",
        "WATCH": "Context and setup are developing. Wait for the remaining execution confirmation.",
        "READY": "All approved gates align. Validate risk before taking any trade.",
    }

    untouched_session_levels = []
    for session_name, session in session_levels.items():
        if not session.get("high_swept", False):
            untouched_session_levels.append(f"{session_name} High")
        if not session.get("low_swept", False):
            untouched_session_levels.append(f"{session_name} Low")

    return {
        "status": status,
        "bias": bias,
        "confidence": confidence,
        "bullish_points": bullish_points,
        "bearish_points": bearish_points,
        "missing": missing,
        "reasons": reasons,
        "untouched_session_levels": untouched_session_levels,
        "next_action": next_actions[status],
        "entry_zone": None,
        "stop": None,
        "targets": [],
    }


def _gate_confidence(
    roles: TimeframeRoleState,
    *,
    liquidity_swept: bool,
    execution_fvg_available: bool,
) -> int:
    if roles.context_direction is None:
        return 0

    score = 20
    if roles.setup_state != SetupState.UNCONFIRMED:
        score += 20
    if liquidity_swept:
        score += 20
    if roles.confirmation_aligned:
        score += 15
    if roles.trigger_aligned:
        score += 15
    if execution_fvg_available:
        score += 10
    return score


def _build_playbook_view(
    roles: TimeframeRoleState,
    *,
    status: str,
    liquidity_swept: bool,
    execution_fvg_available: bool,
    reasons: list[str],
    missing: list[str],
) -> dict[str, Any]:
    if roles.context_direction is None:
        phase = "waiting_for_context"
        next_event = "Wait for 4H and 1H directional alignment."
    elif roles.setup_state == SetupState.UNCONFIRMED:
        phase = "waiting_for_setup"
        next_event = "Wait for reliable 15M structural setup evidence."
    elif not liquidity_swept:
        phase = "waiting_for_liquidity"
        next_event = "Wait for the relevant session liquidity to be swept."
    elif not roles.confirmation_aligned:
        phase = "waiting_for_mss"
        next_event = "Wait for a close-confirmed 5M BOS or CHoCH."
    elif not roles.trigger_aligned:
        phase = "waiting_for_trigger"
        next_event = "Wait for a close-confirmed 1M BOS or CHoCH."
    elif not execution_fvg_available:
        phase = "waiting_for_execution_zone"
        next_event = "Wait for a directional active 1M FVG."
    else:
        phase = "execution_zone_available"
        next_event = "All approved gates align; validate risk before entry."

    playbook_status = {
        "AVOID": "NO SETUP",
        "WAIT": "DEVELOPING",
        "WATCH": "WATCH",
        "READY": "CANDIDATE",
    }[status]

    return {
        "playbook": "ICT Liquidity Sweep Reversal",
        "direction": (
            roles.context_direction.value
            if roles.context_direction is not None
            else None
        ),
        "phase": phase,
        "status": playbook_status,
        "reasons": reasons,
        "missing": missing,
        "next_event": next_event,
        "entry_zone": None,
        "stop": None,
        "targets": [],
    }
