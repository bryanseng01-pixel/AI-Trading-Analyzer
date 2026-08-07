from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from analysis_pipeline import TimeframeAnalysis, select_active_fvgs
from timeframe_roles import (
    Direction,
    SetupState,
    TimeframeRoleState,
    evaluate_timeframe_roles,
)


class AuthorityGateKey(str, Enum):
    HTF_CONTEXT = "htf_context"
    LIQUIDITY_SWEEP = "liquidity_sweep"
    SETUP_15M = "setup_15m"
    CONFIRMATION_5M = "confirmation_5m"
    TRIGGER_1M = "trigger_1m"
    DIRECTIONAL_FVG_1M = "directional_fvg_1m"


@dataclass(frozen=True)
class AuthorityGate:
    """One immutable gate result calculated by DecisionAuthority."""

    key: AuthorityGateKey
    satisfied: bool
    explanation: str


@dataclass(frozen=True)
class AuthorityDecision:
    """The one final recommendation exposed by the application."""

    recommendation: str
    roles: TimeframeRoleState
    gates: tuple[AuthorityGate, ...]
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
        gates = _build_authority_gates(
            roles,
            liquidity_swept=liquidity_swept,
            execution_fvg_available=bool(directional_fvgs),
        )

        status = _recommendation_status(
            roles,
            gates=gates,
        )
        trade_plan = _build_trade_plan_view(
            roles,
            status=status,
            gates=gates,
            session_levels=session_levels,
        )
        playbook = _build_playbook_view(
            roles,
            status=status,
            gates=gates,
            reasons=trade_plan["reasons"],
            missing=trade_plan["missing"],
        )

        return AuthorityDecision(
            recommendation=status,
            roles=roles,
            gates=gates,
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
    gates: tuple[AuthorityGate, ...],
) -> str:
    gate = {item.key: item.satisfied for item in gates}
    if not gate[AuthorityGateKey.HTF_CONTEXT]:
        return "AVOID"
    if not gate[AuthorityGateKey.SETUP_15M]:
        return "WAIT"
    if not gate[AuthorityGateKey.LIQUIDITY_SWEEP]:
        return "WAIT"
    if (
        roles.setup_state == SetupState.COUNTERTREND_PULLBACK
        and not gate[AuthorityGateKey.CONFIRMATION_5M]
    ):
        return "WAIT"
    if not gate[AuthorityGateKey.CONFIRMATION_5M]:
        return "WATCH"
    if (
        not gate[AuthorityGateKey.TRIGGER_1M]
        or not gate[AuthorityGateKey.DIRECTIONAL_FVG_1M]
    ):
        return "WATCH"
    return "READY"


def _build_authority_gates(
    roles: TimeframeRoleState,
    *,
    liquidity_swept: bool,
    execution_fvg_available: bool,
) -> tuple[AuthorityGate, ...]:
    context = roles.context_direction is not None
    setup = roles.setup_state != SetupState.UNCONFIRMED
    return (
        AuthorityGate(
            AuthorityGateKey.HTF_CONTEXT,
            context,
            (
                f"The 4H and 1H context is aligned {roles.context_direction.value}."
                if context
                else "Aligned 4H and 1H context"
            ),
        ),
        AuthorityGate(
            AuthorityGateKey.SETUP_15M,
            setup,
            (
                "The 15M setup supports continuation."
                if roles.setup_state == SetupState.ALIGNED_CONTINUATION
                else "The 15M setup is a countertrend pullback."
                if roles.setup_state == SetupState.COUNTERTREND_PULLBACK
                else "Reliable 15M setup structure"
            ),
        ),
        AuthorityGate(
            AuthorityGateKey.LIQUIDITY_SWEEP,
            liquidity_swept,
            (
                "Relevant session liquidity has been swept by a wick."
                if liquidity_swept
                else "Relevant session liquidity sweep"
            ),
        ),
        AuthorityGate(
            AuthorityGateKey.CONFIRMATION_5M,
            roles.confirmation_aligned,
            (
                "A close-confirmed 5M BOS/CHoCH aligns with context."
                if roles.confirmation_aligned
                else "Aligned close-confirmed 5M BOS/CHoCH"
            ),
        ),
        AuthorityGate(
            AuthorityGateKey.TRIGGER_1M,
            roles.trigger_aligned,
            (
                "A close-confirmed 1M BOS/CHoCH trigger aligns."
                if roles.trigger_aligned
                else "Aligned close-confirmed 1M BOS/CHoCH"
            ),
        ),
        AuthorityGate(
            AuthorityGateKey.DIRECTIONAL_FVG_1M,
            execution_fvg_available,
            (
                "A directional active 1M FVG is available."
                if execution_fvg_available
                else "Directional active 1M FVG"
            ),
        ),
    )


def _build_trade_plan_view(
    roles: TimeframeRoleState,
    *,
    status: str,
    gates: tuple[AuthorityGate, ...],
    session_levels: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    reasons = [gate.explanation for gate in gates if gate.satisfied]
    missing = [gate.explanation for gate in gates if not gate.satisfied]
    direction = roles.context_direction

    confidence = _gate_confidence(gates)
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
    gates: tuple[AuthorityGate, ...],
) -> int:
    gate = {item.key: item.satisfied for item in gates}
    if not gate[AuthorityGateKey.HTF_CONTEXT]:
        return 0

    score = 20
    if gate[AuthorityGateKey.SETUP_15M]:
        score += 20
    if gate[AuthorityGateKey.LIQUIDITY_SWEEP]:
        score += 20
    if gate[AuthorityGateKey.CONFIRMATION_5M]:
        score += 15
    if gate[AuthorityGateKey.TRIGGER_1M]:
        score += 15
    if gate[AuthorityGateKey.DIRECTIONAL_FVG_1M]:
        score += 10
    return score


def _build_playbook_view(
    roles: TimeframeRoleState,
    *,
    status: str,
    gates: tuple[AuthorityGate, ...],
    reasons: list[str],
    missing: list[str],
) -> dict[str, Any]:
    gate = {item.key: item.satisfied for item in gates}
    if not gate[AuthorityGateKey.HTF_CONTEXT]:
        phase = "waiting_for_context"
        next_event = "Wait for 4H and 1H directional alignment."
    elif not gate[AuthorityGateKey.SETUP_15M]:
        phase = "waiting_for_setup"
        next_event = "Wait for reliable 15M structural setup evidence."
    elif not gate[AuthorityGateKey.LIQUIDITY_SWEEP]:
        phase = "waiting_for_liquidity"
        next_event = "Wait for the relevant session liquidity to be swept."
    elif not gate[AuthorityGateKey.CONFIRMATION_5M]:
        phase = "waiting_for_mss"
        next_event = "Wait for a close-confirmed 5M BOS or CHoCH."
    elif not gate[AuthorityGateKey.TRIGGER_1M]:
        phase = "waiting_for_trigger"
        next_event = "Wait for a close-confirmed 1M BOS or CHoCH."
    elif not gate[AuthorityGateKey.DIRECTIONAL_FVG_1M]:
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
