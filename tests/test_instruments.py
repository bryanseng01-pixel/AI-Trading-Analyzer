from dataclasses import FrozenInstanceError, replace

import pandas as pd
import pytest
import streamlit as st
import yfinance as yf

from confluence import ConfluenceFactor, evaluate_confluence
from data import get_market_data
from instrument_pipeline import AnalysisSettings, TIMEFRAMES, build_instrument_analysis
from instruments import (
    ES,
    INSTRUMENT_REGISTRY,
    NQ,
    InstrumentConfig,
    InstrumentRegistry,
    build_location_id,
)
from order_flow_models import FuturesContract
from setup_overlay import build_setup_overlay
from test_decision_authority import _analyses, _evaluate
from test_setup_overlay import _add_execution_fvg, _sessions


def _frame():
    index = pd.date_range("2026-08-05", periods=400, freq="5min", tz="UTC")
    return pd.DataFrame({
        "Open": range(400),
        "High": [value + 2 for value in range(400)],
        "Low": [value - 2 for value in range(400)],
        "Close": [value + 1 for value in range(400)],
        "Volume": [100] * 400,
    }, index=index, dtype=float)


def test_registry_resolves_nq_es_and_tick_metadata():
    assert INSTRUMENT_REGISTRY.keys == ("NQ", "ES")
    assert INSTRUMENT_REGISTRY.resolve_yahoo_symbol("NQ") == "NQ=F"
    assert INSTRUMENT_REGISTRY.resolve_yahoo_symbol("es") == "ES=F"
    assert NQ.root_symbol == "NQ" and ES.root_symbol == "ES"
    assert NQ.tick_size == ES.tick_size == 0.25
    assert NQ.tick_size * 4 == ES.tick_size * 4 == 1.0
    with pytest.raises(FrozenInstanceError):
        NQ.yahoo_symbol = "changed"


def test_registry_growth_requires_only_an_entry():
    mnq = InstrumentConfig(
        key="MNQ",
        display_name="MNQ — Micro E-mini Nasdaq-100",
        yahoo_symbol="MNQ=F",
        futures_instrument=replace(
            NQ.futures_instrument,
            root_symbol="MNQ",
            product_name="Micro E-mini Nasdaq-100",
            tick_value=0.5,
        ),
    )
    registry = InstrumentRegistry(INSTRUMENT_REGISTRY.instruments + (mnq,))
    assert registry.resolve("MNQ") is mnq
    assert registry.keys == ("NQ", "ES", "MNQ")


@pytest.mark.parametrize("field", ("key", "yahoo"))
def test_registry_rejects_duplicate_identity(field):
    duplicate = (
        replace(NQ, yahoo_symbol="NQ-DUPLICATE=F")
        if field == "key"
        else replace(ES, yahoo_symbol=NQ.yahoo_symbol)
    )
    with pytest.raises(ValueError):
        InstrumentRegistry((NQ, duplicate))


def test_market_data_cache_is_instrument_keyed(monkeypatch):
    calls = []
    frame = _frame()
    st.cache_data.clear()

    def download(symbol, **kwargs):
        calls.append(symbol)
        return frame.copy()

    monkeypatch.setattr(yf, "download", download)
    get_market_data("NQ", "1m")
    get_market_data("NQ", "1m")
    get_market_data("ES", "1m")

    assert calls == ["NQ=F", "ES=F"]


def test_instrument_analysis_bundle_is_strategy_wide_and_authority_unchanged():
    frames = {item["interval"]: _frame() for item in TIMEFRAMES.values()}
    settings = AnalysisSettings(5.0, 3)
    nq = build_instrument_analysis(NQ, frames, settings)
    es = build_instrument_analysis(ES, frames, settings)

    assert {item.instrument_key for item in nq.timeframe_analyses.values()} == {"NQ"}
    assert {item.instrument_key for item in es.timeframe_analyses.values()} == {"ES"}
    assert nq.authority_decision == es.authority_decision
    assert nq.setup_overlay.instrument_key == nq.confluence_result.instrument_key == "NQ"
    assert es.setup_overlay.instrument_key == es.confluence_result.instrument_key == "ES"
    assert nq.volume_profile_result.instrument_key == "NQ"
    assert es.volume_profile_result.instrument_key == "ES"


def test_mixed_analysis_provenance_is_rejected(ohlc_factory):
    analyses = _analyses(ohlc_factory)
    analyses["1 Minute"] = replace(analyses["1 Minute"], instrument_key="ES")
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=True)
    decision = _evaluate(analyses, sessions)
    with pytest.raises(ValueError, match="selected instrument"):
        build_setup_overlay(decision, analyses, sessions, instrument_key="NQ")


def test_location_ids_and_confluence_cannot_cross_instruments(ohlc_factory):
    base = _analyses(ohlc_factory)
    base["1 Minute"] = _add_execution_fvg(base["1 Minute"])
    sessions = _sessions(base["5 Minute"], "bullish", swept=True)
    nq_decision = _evaluate(base, sessions)
    nq_overlay = build_setup_overlay(nq_decision, base, sessions, instrument_key="NQ")
    es_analyses = {key: replace(value, instrument_key="ES") for key, value in base.items()}
    es_decision = _evaluate(es_analyses, sessions)
    es_overlay = build_setup_overlay(es_decision, es_analyses, sessions, instrument_key="ES")

    assert nq_overlay.active_execution_zone.location_id != es_overlay.active_execution_zone.location_id
    assert nq_overlay.active_execution_zone.instrument_key == "NQ"
    assert es_overlay.active_execution_zone.instrument_key == "ES"
    wrong_factor = ConfluenceFactor(
        key="synthetic",
        name="Synthetic",
        implemented=True,
        active=True,
        required=False,
        satisfied=True,
        importance="secondary",
        source="test",
        explanation="Mismatched instrument.",
        instrument_key="NQ",
    )
    with pytest.raises(ValueError, match="must match"):
        evaluate_confluence(es_decision, es_overlay, (wrong_factor,))


def test_location_id_uses_root_not_yahoo_symbol():
    location_id = build_location_id(
        ES,
        source_identity="ESU6",
        timeframe="1M",
        zone_kind="original_fvg",
        formation_time=pd.Timestamp("2026-08-05 14:30", tz="UTC"),
        bottom=6300.0,
        top=6301.0,
    )
    assert location_id.startswith("ES:ESU6:1M:original_fvg:")
    assert "ES=F" not in location_id


@pytest.mark.parametrize("instrument", (NQ, ES))
def test_yahoo_symbol_cannot_be_a_real_order_flow_contract(instrument):
    with pytest.raises(ValueError, match="not real order-flow"):
        FuturesContract(
            instrument=instrument.futures_instrument,
            contract_code=instrument.yahoo_symbol,
            contract_month=9,
            contract_year=2026,
            expiration_time=pd.Timestamp("2026-09-18 16:00", tz="UTC"),
            first_notice_time=None,
            provider_symbols=(),
        )
