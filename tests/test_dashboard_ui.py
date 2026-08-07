import pandas as pd
import yfinance as yf
import streamlit as st
from streamlit.testing.v1 import AppTest


def _market_frame():
    index = pd.date_range(
        "2026-08-05",
        periods=400,
        freq="5min",
        tz="UTC",
    )
    return pd.DataFrame(
        {
            "Open": range(400),
            "High": [value + 2 for value in range(400)],
            "Low": [value - 2 for value in range(400)],
            "Close": [value + 1 for value in range(400)],
            "Volume": [100] * 400,
        },
        index=index,
        dtype=float,
    )


def _authority_status(app):
    rendered = [
        element.value
        for element in app.metric
        if element.label == "Status"
    ]
    assert len(rendered) == 1
    return rendered[0]


def test_dashboard_uses_authority_layout_and_display_only_selector(monkeypatch):
    frame = _market_frame()
    monkeypatch.setattr(
        yf,
        "download",
        lambda *args, **kwargs: frame.copy(),
    )

    app = AppTest.from_file("app.py").run(timeout=30)

    assert not app.exception
    subheaders = [element.value for element in app.subheader]
    assert subheaders[:5] == [
        "🧠 AI Trading Assistant",
        "📊 NQ · 4 Hour Chart",
        "Execution-Zone Inspector",
        "Setup Timeline",
        "Setup Evidence",
    ]
    assert "🧠 AI Market Coach" not in subheaders
    assert "📋 Trade Readiness" not in subheaders
    assert "🧠 Decision Engine" not in subheaders

    expander_labels = [element.label for element in app.expander]
    assert expander_labels == [
        "Technical Diagnostics",
        "Location Diagnostics",
        "Order Flow Diagnostics",
        "Data / Provenance",
        "Legacy Diagnostics",
    ]

    metric_labels = [element.label for element in app.metric]
    assert "Instrument" in metric_labels
    assert "Data" in metric_labels
    assert "Authority Confidence" not in metric_labels
    assert "Market Score" not in metric_labels
    assert "Readiness Score" not in metric_labels

    markdown = [str(element.value) for element in app.markdown]
    assert any("Current Setup" in value for value in markdown)
    assert any("Authority-Required Gates" in value for value in markdown)
    assert any("Optional Location Evidence" in value for value in markdown)

    initial_status = _authority_status(app)
    assert app.radio[0].options == ["NQ", "ES"]
    app.selectbox[0].select("1 Minute").run(timeout=30)
    assert not app.exception
    assert _authority_status(app) == initial_status


def test_instrument_selector_reloads_the_entire_market_data_scope(monkeypatch):
    frame = _market_frame()
    calls = []
    st.cache_data.clear()

    def download(symbol, **kwargs):
        calls.append(symbol)
        return frame.copy()

    monkeypatch.setattr(yf, "download", download)
    app = AppTest.from_file("app.py").run(timeout=30)
    assert not app.exception
    assert set(calls) == {"NQ=F"}

    calls.clear()
    app.radio[0].set_value("ES").run(timeout=30)

    assert not app.exception
    assert set(calls) == {"ES=F"}
    assert app.title[0].value == "📈 AI Trading Workstation"
    assert any(
        item.value.startswith("📊 ES · ")
        for item in app.subheader
    )
    instrument_metrics = [
        item.value for item in app.metric if item.label == "Instrument"
    ]
    assert instrument_metrics == ["ES"]
