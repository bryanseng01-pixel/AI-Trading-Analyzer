from copy import deepcopy
from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from confluence import evaluate_confluence
from order_flow_engines import (
    AbsorptionResult,
    BidAskImbalanceResult,
    CumulativeDeltaResult,
    DeltaBucket,
    DeltaResult,
    ExhaustionResult,
    FootprintLevel,
    FootprintResult,
)
from order_flow_integration import (
    CompletedOrderFlowAssessment,
    OrderFlowFactorKey,
    build_order_flow_confluence_factor,
)
from order_flow_models import (
    AnalyticalAvailability,
    AuthorityExecutionLocation,
    OrderFlowAnalysisMetadata,
)
from setup_overlay import build_setup_overlay
from test_decision_authority import _analyses, _evaluate
from test_order_flow_architecture import _provenance
from test_setup_overlay import _add_execution_fvg, _sessions
from timeframe_roles import Direction


def _metadata():
    location = AuthorityExecutionLocation(
        playbook="ICT Liquidity Sweep Reversal",
        authority_status="READY",
        authority_phase="execution_zone_available",
        direction=Direction.BULLISH,
        timeframe="1M",
        zone_kind="original_fvg",
        bottom=100.0,
        top=106.0,
        formation_time=pd.Timestamp("2026-08-05 14:29", tz="UTC"),
        source="authority_filtered_fvg",
    )
    return OrderFlowAnalysisMetadata(
        engine_name="SyntheticContractTest",
        engine_version="0",
        provenance=_provenance(),
        location=location,
        evaluated_start_time=pd.Timestamp("2026-08-05 14:30", tz="UTC"),
        evaluated_end_time=pd.Timestamp("2026-08-05 14:31", tz="UTC"),
        availability=AnalyticalAvailability.AVAILABLE,
        limitations=(),
        confidence_reasons=("Complete synthetic sequence coverage.",),
    )


def test_domain_result_contracts_are_independent_and_immutable():
    metadata = _metadata()
    bucket = DeltaBucket(
        start_time=metadata.evaluated_start_time,
        end_time=metadata.evaluated_end_time,
        ask_volume=12,
        bid_volume=7,
        unknown_volume=2,
        delta=5,
        total_classified_volume=19,
    )
    delta = DeltaResult(metadata, (bucket,), 12, 7, 2, 5, 19 / 21)
    cumulative = CumulativeDeltaResult(
        metadata,
        metadata.evaluated_start_time,
        "explicit_test_anchor",
        0,
        5,
        (),
    )
    imbalance = BidAskImbalanceResult(
        metadata, 12, 7, 2, 12 / 7, None, None, "Rules are not approved."
    )
    footprint = FootprintResult(
        metadata,
        0.25,
        (FootprintLevel(100, 7, 12, 2, 5, 4),),
        (),
    )
    absorption = AbsorptionResult(metadata, (), ())
    exhaustion = ExhaustionResult(metadata, (), ())

    assert delta.net_delta == 5
    assert cumulative.ending_value == 5
    assert imbalance.threshold_satisfied is None
    assert footprint.levels[0].delta == 5
    assert absorption.observations == ()
    assert exhaustion.observations == ()
    with pytest.raises(FrozenInstanceError):
        delta.net_delta = 10


def test_completed_assessment_adapter_adds_no_order_flow_rules():
    assessment = CompletedOrderFlowAssessment(
        key=OrderFlowFactorKey.DELTA,
        name="Delta Confirmation",
        metadata=_metadata(),
        evaluated=True,
        supportive=True,
        explanation="A future approved engine supplied this completed result.",
    )
    factor = build_order_flow_confluence_factor(assessment)

    assert factor.key == "delta"
    assert factor.active is True
    assert factor.required is False
    assert factor.satisfied is True
    assert factor.source == "SyntheticContractTest"


def test_unevaluated_assessment_is_inactive_and_has_no_result():
    assessment = CompletedOrderFlowAssessment(
        key=OrderFlowFactorKey.FOOTPRINT,
        name="Footprint Imbalance",
        metadata=_metadata(),
        evaluated=False,
        supportive=None,
        explanation="Licensed footprint data is unavailable.",
    )
    factor = build_order_flow_confluence_factor(assessment)

    assert factor.active is False
    assert factor.satisfied is None


def test_confidence_reasons_do_not_enter_confluence_factor():
    metadata = _metadata()
    assessment = CompletedOrderFlowAssessment(
        key=OrderFlowFactorKey.ABSORPTION,
        name="Absorption",
        metadata=metadata,
        evaluated=True,
        supportive=False,
        explanation="No approved supporting observation was supplied.",
    )
    factor = build_order_flow_confluence_factor(assessment)

    assert "Complete synthetic sequence coverage" not in factor.explanation
    assert not hasattr(factor, "confidence_reasons")


def test_optional_order_flow_factor_cannot_mutate_authority(ohlc_factory):
    analyses = _analyses(ohlc_factory)
    analyses["1 Minute"] = _add_execution_fvg(analyses["1 Minute"])
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=True)
    decision = _evaluate(analyses, sessions)
    overlay = build_setup_overlay(decision, analyses, sessions)
    original = deepcopy(decision)
    factor = build_order_flow_confluence_factor(
        CompletedOrderFlowAssessment(
            key=OrderFlowFactorKey.DELTA,
            name="Delta Confirmation",
            metadata=_metadata(),
            evaluated=True,
            supportive=True,
            explanation="Completed synthetic assessment.",
        )
    )

    result = evaluate_confluence(decision, overlay, (factor,))

    assert decision == original
    assert decision.recommendation == "READY"
    assert factor.required is False
    assert "delta" not in {item.key for item in result.pending_future_factors}


def test_no_domain_contract_generates_trade_projections_or_recommendations():
    forbidden = {"recommendation", "entry", "stop", "target", "score", "probability"}

    for model in (
        DeltaResult,
        CumulativeDeltaResult,
        BidAskImbalanceResult,
        FootprintResult,
        AbsorptionResult,
        ExhaustionResult,
    ):
        assert forbidden.isdisjoint(model.__dataclass_fields__)
