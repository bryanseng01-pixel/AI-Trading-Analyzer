import streamlit as st

from analysis_pipeline import TimeframeAnalysis
from instrument_pipeline import InstrumentAnalysisBundle
from tradingview_chart import display_tradingview_chart
from workstation_view import (
    EvidenceItemView,
    ExecutionInspectorView,
    TimelineState,
    TradingWorkstationView,
)


def render_top_bar(view: TradingWorkstationView) -> None:
    top = view.top_bar
    with st.container(border=True):
        columns = st.columns((1, 1, 1, 1, 1.4, 1.2))
        columns[0].metric("Instrument", top.instrument_key)
        columns[1].metric("Chart", top.chart_timeframe)
        columns[2].metric("Status", top.authority_status)
        columns[3].metric("Context", top.direction)
        columns[4].metric("Data", top.data_state)
        columns[5].metric("Updated", top.refreshed_at.strftime("%I:%M:%S %p"))


def render_authority_summary(view: TradingWorkstationView) -> None:
    authority = view.authority
    st.subheader("🧠 AI Trading Assistant")
    with st.container(border=True):
        if authority.status == "READY":
            st.success(f"🟢 READY · {authority.direction}")
        elif authority.status == "WATCH":
            st.warning(f"🟡 WATCH · {authority.direction}")
        elif authority.status == "WAIT":
            st.info(f"🟡 WAIT · {authority.direction}")
        else:
            st.error("🔴 AVOID · Context conflict")
        identity, phase = st.columns(2)
        identity.markdown(f"**Playbook:** {authority.playbook}")
        phase.markdown(f"**Phase:** {_label(authority.phase)}")
        st.info(f"**Next Event:** {authority.next_event}")
        st.markdown(f"**Next Action:** {authority.next_action}")
        confirmed, missing = st.columns(2)
        with confirmed:
            st.markdown("**Confirmed Gates**")
            _render_text_items(authority.confirmed_gates, "✅", "None confirmed")
        with missing:
            st.markdown("**Missing Gates**")
            _render_text_items(authority.missing_gates, "⏳", "None missing")
        st.markdown("**Market Story**")
        for sentence in authority.market_story:
            st.caption(sentence)


def render_current_setup(view: TradingWorkstationView) -> None:
    setup = view.current_setup
    with st.container(border=True):
        st.markdown("#### Current Setup")
        stage, waiting, milestone = st.columns(3)
        stage.markdown(f"**Stage**  \n{_label(setup.stage)}")
        waiting.markdown(f"**Waiting Event**  \n{setup.waiting_event}")
        milestone.markdown(f"**Next Milestone**  \n{setup.next_milestone}")
        if setup.pending_optional_evidence:
            st.caption(
                "Future evidence not connected: "
                + ", ".join(setup.pending_optional_evidence)
            )


def render_chart_workspace(
    view: TradingWorkstationView,
    analysis: TimeframeAnalysis,
    *,
    setup_overlay,
) -> None:
    chart_column, inspector_column = st.columns((2.35, 1), gap="medium")
    with chart_column:
        st.subheader(
            f"📊 {view.top_bar.instrument_key} · "
            f"{view.top_bar.chart_timeframe} Chart"
        )
        display_tradingview_chart(analysis.data, setup_overlay=setup_overlay, height=680)
    with inspector_column:
        render_execution_inspector(view.execution_inspector)


def render_execution_inspector(inspector: ExecutionInspectorView) -> None:
    st.subheader("Execution-Zone Inspector")
    with st.container(border=True):
        if not inspector.available:
            st.info("No authority execution zone is currently available.")
            st.caption(inspector.premium_discount_summary)
            st.caption(inspector.volume_profile_summary)
            return
        st.markdown(
            f"**{inspector.instrument_key} · {_label(inspector.zone_type)} · "
            f"{_label(inspector.direction)}**"
        )
        top, bottom = st.columns(2)
        top.metric("Top", f"{inspector.top:.2f}")
        bottom.metric("Bottom", f"{inspector.bottom:.2f}")
        st.caption("Formed: " + inspector.formation_time.strftime("%Y-%m-%d %H:%M %Z"))
        st.write(f"**Lifecycle:** {_label(inspector.lifecycle or 'Unavailable')}")
        st.write(f"**Purpose:** {_label(inspector.authority_purpose)}")
        st.caption(f"Location ID: {inspector.location_id}")
        st.divider()
        st.markdown("**Overlapping Evidence**")
        st.caption("IFVG — " + inspector.ifvg_summary)
        st.caption("Order Block — " + inspector.order_block_summary)
        st.caption("Premium / Discount — " + inspector.premium_discount_summary)
        st.caption("Volume Profile — " + inspector.volume_profile_summary)
        if inspector.limitations:
            with st.expander("Limitations", expanded=False):
                for limitation in inspector.limitations:
                    st.caption("• " + limitation)


def render_setup_timeline(view: TradingWorkstationView) -> None:
    st.subheader("Setup Timeline")
    columns = st.columns(len(view.timeline))
    symbols = {
        TimelineState.COMPLETE: "✅",
        TimelineState.CURRENT: "🟡",
        TimelineState.FUTURE: "○",
        TimelineState.UNAVAILABLE: "—",
    }
    for column, item in zip(columns, view.timeline):
        with column:
            st.markdown(f"{symbols[item.state]} **{item.label}**")
            st.caption(_label(item.state.value))
            if item.timestamp is not None:
                st.caption(item.timestamp.strftime("%H:%M:%S %Z"))


def render_confluence_panel(view: TradingWorkstationView) -> None:
    st.subheader("Setup Evidence")
    required, optional = st.columns(2)
    with required:
        with st.container(border=True):
            st.markdown("#### Authority-Required Gates")
            for item in view.required_gates:
                _render_evidence(item, required=True)
    with optional:
        with st.container(border=True):
            st.markdown("#### Optional Location Evidence")
            for item in view.optional_evidence:
                _render_evidence(item, required=False)
            if view.unavailable_evidence:
                st.caption("Not connected: " + ", ".join(view.unavailable_evidence))


def render_diagnostics(
    bundle: InstrumentAnalysisBundle,
    selected_analysis: TimeframeAnalysis,
    *,
    displayed_active_fvgs: int,
) -> None:
    with st.expander("Technical Diagnostics", expanded=False):
        st.caption(
            f"Selected instrument: {bundle.instrument.key}; displayed chart: "
            f"{selected_analysis.timeframe}"
        )
        for name, analysis in bundle.timeframe_analyses.items():
            st.markdown(f"**{name} · {analysis.instrument_key}**")
            columns = st.columns(4)
            columns[0].metric("EMA Trend", analysis.trend)
            columns[1].metric("Structure", analysis.structure)
            columns[2].metric("BOS", analysis.bos["direction"] if analysis.bos else "None")
            columns[3].metric("CHoCH", analysis.choch["direction"] if analysis.choch else "None")
            st.caption(
                f"Swings H/L: {len(analysis.highs)}/{len(analysis.lows)} · "
                f"Equal H/L: {len(analysis.equal_highs)}/{len(analysis.equal_lows)}"
            )
        st.caption(f"Displayed active FVGs: {displayed_active_fvgs}")

    with st.expander("Location Diagnostics", expanded=False):
        st.markdown("**FVG Lifecycle**")
        st.write({
            "active_fvgs": len(bundle.fvg_lifecycle_result.active_fvgs),
            "active_ifvgs": len(bundle.fvg_lifecycle_result.active_ifvgs),
        })
        st.markdown("**Order Blocks**")
        st.write({"active": len(bundle.order_block_result.active_order_blocks)})
        st.markdown("**Premium / Discount**")
        st.write(bundle.setup_overlay.premium_discount_support.explanation)
        st.markdown("**Volume Profile**")
        st.write(bundle.setup_overlay.volume_profile_support.explanation)
        for limitation in bundle.setup_overlay.volume_profile_support.limitations:
            st.caption("• " + limitation)

    with st.expander("Order Flow Diagnostics", expanded=False):
        st.info("No licensed real-time order-flow provider is configured.")
        st.caption("Delta: analytical engine available; no live assessment supplied.")
        st.caption("Cumulative Delta: descriptive engine; no live assessment supplied.")
        st.caption("Footprint: analytical engine available; no live assessment supplied.")
        st.caption("Absorption / Exhaustion: future approved engines.")

    with st.expander("Data / Provenance", expanded=False):
        instrument = bundle.instrument
        st.write({
            "instrument": instrument.key,
            "yahoo_symbol": instrument.yahoo_symbol,
            "futures_root": instrument.root_symbol,
            "tick_size": instrument.tick_size,
            "exchange": instrument.exchange,
            "exchange_timezone": instrument.exchange_timezone,
            "display_timezone": instrument.display_timezone,
            "market_data": "Yahoo OHLCV — temporary",
            "order_flow_provider": "Not configured",
        })
        st.warning(
            "Yahoo OHLCV cannot provide true bid/ask order flow, footprint, "
            "delta, absorption, or exhaustion."
        )

    with st.expander("Legacy Diagnostics", expanded=False):
        st.warning(
            "Non-authoritative retained diagnostics. These values do not control "
            "DecisionAuthority or recommendations."
        )
        context = bundle.timeframe_analyses["4 Hour"]
        st.write({
            "trend": context.trend,
            "structure": context.structure,
            "bos": context.bos,
            "choch": context.choch,
        })


def _render_evidence(item: EvidenceItemView, *, required: bool) -> None:
    if item.satisfied is True:
        symbol, text = "✅", item.name
    elif item.active:
        symbol, text = ("⏳" if required else "○"), item.name
    else:
        symbol, text = "—", f"{item.name} · not applicable"
    st.markdown(f"{symbol} {text}")
    st.caption(item.explanation)


def _render_text_items(items: tuple[str, ...], symbol: str, empty: str) -> None:
    if not items:
        st.caption(empty)
        return
    for item in items:
        st.caption(f"{symbol} {item}")


def _label(value: str | None) -> str:
    if not value:
        return "Unavailable"
    return str(value).replace("_", " ").title()
