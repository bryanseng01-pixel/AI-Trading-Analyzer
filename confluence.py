from dataclasses import dataclass
from typing import Iterable

from decision_authority import (
    AuthorityDecision,
    AuthorityGateKey,
)
from setup_overlay import SetupOverlay
from timeframe_roles import Direction


@dataclass(frozen=True)
class ConfluenceFactor:
    """A factual evidence result supplied by an approved analytical engine."""

    key: str
    name: str
    implemented: bool
    active: bool
    required: bool
    satisfied: bool | None
    importance: str | None
    source: str
    explanation: str

    def __post_init__(self) -> None:
        if not self.key or not self.name or not self.source:
            raise ValueError("Confluence factors require key, name, and source.")
        if self.importance not in {"primary", "secondary", None}:
            raise ValueError("importance must be primary, secondary, or None.")
        if not self.implemented:
            if self.active or self.required or self.satisfied is not None:
                raise ValueError(
                    "Future placeholders must be inactive, optional, and unevaluated."
                )
        elif self.active and self.satisfied is None:
            raise ValueError("Active implemented factors require a result.")


@dataclass(frozen=True)
class ConfluenceResult:
    """Describes evidence at a location without issuing a recommendation."""

    active_playbook: str
    authority_status: str
    authority_direction: Direction | None
    authority_phase: str
    execution_location_available: bool
    total_supported: int
    total_satisfied: int
    completion_percentage: float
    implemented_factors: tuple[ConfluenceFactor, ...]
    pending_future_factors: tuple[ConfluenceFactor, ...]
    strengths: tuple[str, ...]
    weaknesses: tuple[str, ...]
    explanation: str
    location_notes: tuple[str, ...] = ()


_BUILTIN_FACTORS = (
    (AuthorityGateKey.HTF_CONTEXT, "HTF Context", "primary"),
    (AuthorityGateKey.LIQUIDITY_SWEEP, "Liquidity Sweep", "primary"),
    (AuthorityGateKey.SETUP_15M, "15M Setup", "primary"),
    (AuthorityGateKey.CONFIRMATION_5M, "5M Confirmation", "primary"),
    (AuthorityGateKey.TRIGGER_1M, "1M Trigger", "primary"),
    (
        AuthorityGateKey.DIRECTIONAL_FVG_1M,
        "Active Directional 1M FVG",
        "primary",
    ),
)

_FUTURE_FACTORS = (
    ("ifvg", "IFVG"),
    ("order_block", "Order Block"),
    ("premium_discount", "Premium/Discount"),
    ("volume_profile", "Volume Profile"),
    ("delta_confirmation", "Delta Confirmation"),
    ("cumulative_delta_context", "Cumulative Delta Context"),
    ("footprint_imbalance", "Footprint Imbalance"),
    ("absorption", "Absorption"),
    ("smt", "SMT"),
    ("ote", "OTE"),
)


def evaluate_confluence(
    authority_decision: AuthorityDecision,
    setup_overlay: SetupOverlay,
    contributed_factors: Iterable[ConfluenceFactor] = (),
) -> ConfluenceResult:
    """Evaluate already-derived evidence without performing market analysis."""

    _validate_provenance(authority_decision, setup_overlay)
    authority_gates = {gate.key: gate for gate in authority_decision.gates}

    builtins = tuple(
        ConfluenceFactor(
            key=key.value,
            name=name,
            implemented=True,
            active=True,
            required=True,
            satisfied=authority_gates[key].satisfied,
            importance=importance,
            source="DecisionAuthority",
            explanation=authority_gates[key].explanation,
        )
        for key, name, importance in _BUILTIN_FACTORS
    )

    contributions = tuple(contributed_factors)
    _validate_contributions(contributions)
    contributions_by_key = {factor.key: factor for factor in contributions}
    placeholders = tuple(
        _future_placeholder(key, name)
        for key, name in _FUTURE_FACTORS
        if key not in contributions_by_key
    )
    implemented = builtins + tuple(
        sorted(contributions, key=lambda factor: factor.key)
    )
    supported = tuple(
        factor
        for factor in implemented
        if factor.implemented and factor.active
    )
    satisfied = tuple(factor for factor in supported if factor.satisfied)
    strengths = tuple(factor.name for factor in satisfied)
    weaknesses = tuple(
        factor.name for factor in supported if factor.satisfied is False
    )
    total_supported = len(supported)
    total_satisfied = len(satisfied)
    completion = (
        total_satisfied / total_supported * 100.0
        if total_supported
        else 0.0
    )

    return ConfluenceResult(
        active_playbook=setup_overlay.active_playbook,
        authority_status=authority_decision.recommendation,
        authority_direction=authority_decision.roles.context_direction,
        authority_phase=setup_overlay.current_phase,
        execution_location_available=(
            setup_overlay.active_execution_zone is not None
        ),
        total_supported=total_supported,
        total_satisfied=total_satisfied,
        completion_percentage=completion,
        implemented_factors=implemented,
        pending_future_factors=placeholders,
        strengths=strengths,
        weaknesses=weaknesses,
        explanation=(
            f"{total_satisfied} of {total_supported} active implemented "
            "evidence factors are satisfied. Future placeholders are excluded."
        ),
        location_notes=(),
    )


def _future_placeholder(key: str, name: str) -> ConfluenceFactor:
    return ConfluenceFactor(
        key=key,
        name=name,
        implemented=False,
        active=False,
        required=False,
        satisfied=None,
        importance=None,
        source="Future approved engine",
        explanation="Reserved for a future approved location engine.",
    )


def _validate_provenance(
    authority_decision: AuthorityDecision,
    setup_overlay: SetupOverlay,
) -> None:
    expected = (
        authority_decision.playbook["playbook"],
        authority_decision.recommendation,
        authority_decision.roles.context_direction,
        authority_decision.playbook["phase"],
    )
    actual = (
        setup_overlay.active_playbook,
        setup_overlay.authority_status,
        setup_overlay.direction,
        setup_overlay.current_phase,
    )
    if actual != expected:
        raise ValueError(
            "SetupOverlay provenance does not match the authority decision."
        )


def _validate_contributions(
    contributions: tuple[ConfluenceFactor, ...],
) -> None:
    builtin_keys = {key.value for key, _, _ in _BUILTIN_FACTORS}
    seen: set[str] = set()
    for factor in contributions:
        if not factor.implemented:
            raise ValueError("Contributed factors must be implemented results.")
        if factor.key in builtin_keys:
            raise ValueError("Contributed factors cannot replace authority gates.")
        if factor.key in seen:
            raise ValueError("Contributed factor keys must be unique.")
        seen.add(factor.key)
