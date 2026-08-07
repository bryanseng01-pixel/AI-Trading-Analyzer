from dataclasses import replace

from setup_overlay import (
    OverlayAnnotation,
    OverlayAnnotationKind,
    build_setup_overlay,
)
from test_decision_authority import _analyses, _evaluate
from test_setup_overlay import _add_execution_fvg, _sessions
from tradingview_chart import (
    LIGHTWEIGHT_CHARTS_CDN_URL,
    LIGHTWEIGHT_CHARTS_VERSION,
    _serialize_setup_overlay,
    build_tradingview_chart_html,
    display_tradingview_chart,
)


def test_overlay_none_preserves_existing_chart_contract():
    assert _serialize_setup_overlay(None) is None


def test_renderer_keeps_overlay_optional(monkeypatch, ohlc_factory):
    data = ohlc_factory(
        [
            (100, 101, 99, 100, 10),
            (100, 103, 100, 102, 10),
        ]
    )
    rendered = {}
    monkeypatch.setattr(
        "tradingview_chart.st.iframe",
        lambda html, **kwargs: rendered.update(html=html, kwargs=kwargs),
    )

    display_tradingview_chart(data, setup_overlay=None)

    assert "const setupOverlayData = null;" in rendered["html"]
    assert "candleSeries.setData(candleData);" in rendered["html"]
    assert rendered["kwargs"] == {
        "width": "stretch",
        "height": 700,
        "tab_index": -1,
    }


def test_chart_runtime_is_version_pinned_and_responsive(ohlc_factory):
    data = ohlc_factory([(100, 101, 99, 100, 10)])

    html = build_tradingview_chart_html(data, height=640)

    assert LIGHTWEIGHT_CHARTS_VERSION == "5.0.9"
    assert LIGHTWEIGHT_CHARTS_CDN_URL in html
    assert f"height: 640px" in html
    assert "new ResizeObserver" in html
    assert "Chart runtime unavailable." in html
    assert "innerHTML" not in html
    assert "annotation.textContent = text;" in html


def test_annotation_text_is_json_encoded_not_executable(ohlc_factory):
    analyses = _analyses(ohlc_factory)
    decision = _evaluate(analyses, {})
    overlay = build_setup_overlay(decision, analyses, {})
    overlay = replace(
        overlay,
        annotations=(
            OverlayAnnotation(
                kind=OverlayAnnotationKind.LIMITATION,
                text="</script><script>unsafe()</script>",
            ),
        ),
    )

    html = build_tradingview_chart_html(
        analyses["1 Minute"].data,
        setup_overlay=overlay,
    )

    assert "</script><script>unsafe()" not in html
    assert "\\u003c/script\\u003e\\u003cscript\\u003eunsafe()" in html


def test_ready_overlay_serializes_only_visible_authority_objects(ohlc_factory):
    analyses = _analyses(ohlc_factory)
    analyses["1 Minute"] = _add_execution_fvg(analyses["1 Minute"])
    sessions = _sessions(analyses["5 Minute"], "bullish", swept=True)
    decision = _evaluate(analyses, sessions)
    overlay = build_setup_overlay(decision, analyses, sessions)

    serialized = _serialize_setup_overlay(overlay)

    assert serialized is not None
    assert serialized["authority_status"] == decision.recommendation
    assert serialized["direction"] == "bullish"
    assert serialized["current_phase"] == "execution_zone_available"
    assert serialized["progress_step"] == len(decision.trade_plan["reasons"])
    assert serialized["total_steps"] == 6
    assert serialized["execution_zone"]["bottom"] == 100.0
    assert serialized["execution_zone"]["top"] == 106.0
    assert serialized["execution_zone"]["purpose"] == "authority_required"
    assert serialized["optional_ifvg_zone"] is None
    assert serialized["optional_order_block_zone"] is None
    assert serialized["dealing_range"] is None
    assert serialized["volume_profile"] is None
    assert {level["role"] for level in serialized["levels"]} == {
        "liquidity",
        "confirmation",
        "trigger",
    }
    assert "entry" not in serialized
    assert "stop" not in serialized
    assert "invalidation" not in serialized
    assert "targets" not in serialized


def test_avoid_overlay_serializes_no_levels_or_zone(ohlc_factory):
    analyses = _analyses(ohlc_factory)
    analyses["1 Hour"] = replace(
        analyses["1 Hour"],
        trend="BEARISH 🔴",
    )
    decision = _evaluate(analyses, {})
    overlay = build_setup_overlay(decision, analyses, {})

    serialized = _serialize_setup_overlay(overlay)

    assert serialized["authority_status"] == "AVOID"
    assert serialized["levels"] == []
    assert serialized["execution_zone"] is None
    assert serialized["optional_ifvg_zone"] is None
    assert serialized["optional_order_block_zone"] is None
    assert serialized["dealing_range"] is None
    assert serialized["volume_profile"] is None
    assert serialized["annotations"] == [
        "AVOID — 4H and 1H preliminary context conflicts."
    ]
