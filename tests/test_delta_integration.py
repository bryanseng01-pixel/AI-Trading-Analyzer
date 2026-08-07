from copy import deepcopy
from dataclasses import fields

from confluence import evaluate_confluence
from delta_engine import DeltaLocationState
from delta_integration import build_delta_confluence_factor
from order_flow_models import AggressorSide
from setup_overlay import build_setup_overlay
from test_decision_authority import _analyses, _evaluate as _authority_evaluate
from test_delta_engine import _evaluate as _delta_evaluate, _trade
from test_setup_overlay import _add_execution_fvg, _sessions


def test_supportive_delta_replaces_placeholder_as_optional_factor(
    ohlc_factory,
):
    analyses = _analyses(ohlc_factory)
    analyses["1 Minute"] = _add_execution_fvg(analyses["1 Minute"])
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=True)
    decision = _authority_evaluate(analyses, sessions)
    overlay = build_setup_overlay(decision, analyses, sessions)
    _, assessment = _delta_evaluate(
        (
            _trade("a", 1, 100, 3, AggressorSide.BUY),
            _trade("b", 2, 101, 1, AggressorSide.SELL),
        )
    )
    factor = build_delta_confluence_factor(assessment)
    result = evaluate_confluence(decision, overlay, (factor,))

    assert assessment.state == DeltaLocationState.SUPPORTIVE_CONTINUATION
    assert factor.key == "delta_confirmation"
    assert factor.name == "Delta Confirmation"
    assert factor.active is True
    assert factor.required is False
    assert factor.satisfied is True
    assert factor.importance == "secondary"
    assert factor.source == "DeltaEngine"
    assert "delta_confirmation" not in {
        item.key for item in result.pending_future_factors
    }
    assert "delta" not in {
        item.key for item in result.pending_future_factors
    }


def test_opposing_and_mixed_delta_are_active_but_unsatisfied():
    cases = (
        (
            _trade("a", 1, 102, 1, AggressorSide.BUY),
            _trade("b", 2, 101, 3, AggressorSide.SELL),
        ),
        (
            _trade("c", 1, 100, 1, AggressorSide.SELL),
            _trade("d", 2, 101, 3, AggressorSide.SELL),
        ),
    )

    for trades in cases:
        _, assessment = _delta_evaluate(trades)
        factor = build_delta_confluence_factor(assessment)
        assert assessment.state in {
            DeltaLocationState.OPPOSING_CONTINUATION,
            DeltaLocationState.MIXED_OR_DIVERGENT,
        }
        assert factor.active is True
        assert factor.satisfied is False


def test_unavailable_delta_is_inactive_and_unevaluated():
    _, assessment = _delta_evaluate(
        (_trade("unknown", 1, 100, 5, AggressorSide.UNKNOWN),)
    )
    factor = build_delta_confluence_factor(assessment)

    assert assessment.state == DeltaLocationState.UNAVAILABLE
    assert factor.active is False
    assert factor.satisfied is None


def test_delta_evaluation_and_confluence_do_not_mutate_authority(ohlc_factory):
    analyses = _analyses(ohlc_factory)
    analyses["1 Minute"] = _add_execution_fvg(analyses["1 Minute"])
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=True)
    decision = _authority_evaluate(analyses, sessions)
    original = deepcopy(decision)
    overlay = build_setup_overlay(decision, analyses, sessions)
    _, assessment = _delta_evaluate(
        (
            _trade("a", 1, 100, 3, AggressorSide.BUY),
            _trade("b", 2, 101, 1, AggressorSide.SELL),
        )
    )

    evaluate_confluence(
        decision,
        overlay,
        (build_delta_confluence_factor(assessment),),
    )

    assert decision == original
    assert decision.recommendation == "READY"


def test_chart_selection_is_not_an_input_to_delta_or_confluence(ohlc_factory):
    analyses = _analyses(ohlc_factory)
    analyses["1 Minute"] = _add_execution_fvg(analyses["1 Minute"])
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=True)
    decision = _authority_evaluate(analyses, sessions)
    overlay = build_setup_overlay(decision, analyses, sessions)
    trades = (
        _trade("a", 1, 100, 3, AggressorSide.BUY),
        _trade("b", 2, 101, 1, AggressorSide.SELL),
    )
    snapshots = set()

    for selected in analyses:
        assert analyses[selected] is not None
        _, assessment = _delta_evaluate(trades)
        factor = build_delta_confluence_factor(assessment)
        snapshots.add(
            (
                decision.recommendation,
                assessment.delta_result.net_delta,
                assessment.state,
                factor.satisfied,
            )
        )

    assert snapshots == {
        ("READY", 2.0, DeltaLocationState.SUPPORTIVE_CONTINUATION, True)
    }


def test_delta_outputs_have_no_trade_projection_or_recommendation_fields():
    forbidden = {
        "recommendation",
        "confidence_score",
        "probability",
        "score",
        "entry",
        "stop",
        "target",
    }

    assert forbidden.isdisjoint(
        field.name for field in fields(__import__("delta_engine").DeltaLocationAssessment)
    )
