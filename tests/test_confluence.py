from dataclasses import FrozenInstanceError, fields, replace
from inspect import signature

import pytest

from confluence import (
    ConfluenceFactor,
    ConfluenceResult,
    evaluate_confluence,
)
from decision_authority import AuthorityGateKey
from setup_overlay import build_setup_overlay
from test_decision_authority import _analyses, _evaluate, _session_sweep


def _result(ohlc_factory, **analysis_options):
    analyses = _analyses(ohlc_factory, **analysis_options)
    direction = analysis_options.get("context", "bullish")
    sessions = _session_sweep(direction)
    decision = _evaluate(analyses, sessions)
    overlay = build_setup_overlay(decision, analyses, sessions)
    return decision, overlay, evaluate_confluence(decision, overlay)


def test_result_is_immutable_and_has_no_recommendation_output(ohlc_factory):
    decision, _, result = _result(ohlc_factory)

    assert result.authority_status == decision.recommendation
    assert result.location_notes == ()
    assert "recommendation" not in {field.name for field in fields(result)}
    assert "confidence" not in {field.name for field in fields(result)}
    with pytest.raises(FrozenInstanceError):
        result.total_satisfied = 0


def test_implemented_factors_mirror_authority_gates(ohlc_factory):
    decision, _, result = _result(
        ohlc_factory,
        trigger=False,
        execution_fvg=False,
    )
    expected = {gate.key.value: gate.satisfied for gate in decision.gates}

    assert {
        factor.key: factor.satisfied for factor in result.implemented_factors
    } == expected
    assert result.total_supported == 6
    assert result.total_satisfied == sum(expected.values())
    assert result.completion_percentage == pytest.approx(
        result.total_satisfied / 6 * 100.0
    )


def test_future_placeholders_are_unevaluated_and_excluded(ohlc_factory):
    _, _, result = _result(ohlc_factory)

    assert len(result.pending_future_factors) == 10
    assert result.total_supported == 6
    assert all(not factor.implemented for factor in result.pending_future_factors)
    assert all(factor.satisfied is None for factor in result.pending_future_factors)
    assert not set(result.weaknesses).intersection(
        factor.name for factor in result.pending_future_factors
    )


def test_approved_future_factor_replaces_placeholder_without_engine_logic(
    ohlc_factory,
):
    analyses = _analyses(ohlc_factory)
    sessions = _session_sweep("bullish")
    decision = _evaluate(analyses, sessions)
    overlay = build_setup_overlay(decision, analyses, sessions)
    factor = ConfluenceFactor(
        key="order_block",
        name="Order Block",
        implemented=True,
        active=True,
        required=False,
        satisfied=True,
        importance="secondary",
        source="OrderBlockEngine",
        explanation="An approved engine found a relevant order block.",
    )

    result = evaluate_confluence(decision, overlay, (factor,))

    assert result.total_supported == 7
    assert result.total_satisfied == 7
    assert factor in result.implemented_factors
    assert "order_block" not in {
        item.key for item in result.pending_future_factors
    }


def test_evaluation_is_deterministic_for_contribution_order(ohlc_factory):
    analyses = _analyses(ohlc_factory)
    sessions = _session_sweep("bullish")
    decision = _evaluate(analyses, sessions)
    overlay = build_setup_overlay(decision, analyses, sessions)
    factors = tuple(
        ConfluenceFactor(
            key=key,
            name=name,
            implemented=True,
            active=True,
            required=False,
            satisfied=satisfied,
            importance=None,
            source="ApprovedEngine",
            explanation="Already-derived observation.",
        )
        for key, name, satisfied in (
            ("volume_profile", "Volume Profile", True),
            ("delta_confirmation", "Delta Confirmation", False),
        )
    )

    forward = evaluate_confluence(decision, overlay, factors)
    reverse = evaluate_confluence(decision, overlay, reversed(factors))

    assert forward == reverse


def test_evaluator_contract_is_chart_and_raw_analysis_independent():
    assert tuple(signature(evaluate_confluence).parameters) == (
        "authority_decision",
        "setup_overlay",
        "contributed_factors",
    )


def test_mismatched_overlay_is_rejected_without_changing_authority(
    ohlc_factory,
):
    decision, overlay, _ = _result(ohlc_factory)
    original = decision

    with pytest.raises(ValueError, match="provenance"):
        evaluate_confluence(
            decision,
            replace(overlay, authority_status="WAIT"),
        )

    assert decision == original


def test_overlay_location_does_not_rewrite_fvg_gate(ohlc_factory):
    decision, overlay, _ = _result(ohlc_factory)
    without_drawable_zone = replace(overlay, active_execution_zone=None)

    result = evaluate_confluence(decision, without_drawable_zone)
    fvg = next(
        factor
        for factor in result.implemented_factors
        if factor.key == AuthorityGateKey.DIRECTIONAL_FVG_1M.value
    )

    assert fvg.satisfied is True
    assert result.execution_location_available is False


def test_factor_invariants_keep_placeholders_separate():
    with pytest.raises(ValueError, match="Future placeholders"):
        ConfluenceFactor(
            key="ifvg",
            name="IFVG",
            implemented=False,
            active=True,
            required=False,
            satisfied=True,
            importance=None,
            source="Future approved engine",
            explanation="Not implemented.",
        )

    assert "buy" not in {field.name.lower() for field in fields(ConfluenceResult)}
    assert "sell" not in {field.name.lower() for field in fields(ConfluenceResult)}
