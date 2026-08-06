import pandas as pd
import yfinance as yf
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
    assert subheaders[:4] == [
        "🧠 AI Trading Assistant",
        "📊 Displayed Chart — 4 Hour",
        "📋 Authority Setup Progress",
        "▫️ 1M Execution FVG Context",
    ]
    assert "🧠 AI Market Coach" not in subheaders
    assert "📋 Trade Readiness" not in subheaders
    assert "🧠 Decision Engine" not in subheaders

    expander_labels = [element.label for element in app.expander]
    assert expander_labels == [
        "📊 Technical Diagnostics",
        "🌍 Session Liquidity",
        "🧪 Legacy Diagnostics",
    ]

    metric_labels = [element.label for element in app.metric]
    assert "Authority Confidence" in metric_labels
    assert "Completed Authority Gates" in metric_labels
    assert "Market Score" not in metric_labels
    assert "Readiness Score" not in metric_labels

    markdown = [str(element.value) for element in app.markdown]
    assert any("Preliminary EMA Context Only" in value for value in markdown)
    assert any("Confirmed Conditions" in value for value in markdown)
    assert any("Missing Conditions" in value for value in markdown)

    initial_status = _authority_status(app)
    statuses = set()
    for option in app.selectbox[0].options:
        app.selectbox[0].select(option).run(timeout=30)
        assert not app.exception
        statuses.add(_authority_status(app))

    assert statuses == {initial_status}
