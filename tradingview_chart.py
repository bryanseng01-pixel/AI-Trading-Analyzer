import json

import pandas as pd
import streamlit.components.v1 as components

from setup_overlay import SetupOverlay


def display_tradingview_chart(
    data: pd.DataFrame,
    high_labels=None,
    low_labels=None,
    bos=None,
    choch=None,
    equal_highs=None,
    equal_lows=None,
    fvgs=None,
    setup_overlay: SetupOverlay | None = None,
    height: int = 700,
) -> None:


    """
    Displays candlestick data using TradingView Lightweight Charts.

    Args:
        data: DataFrame containing Open, High, Low, and Close columns.
        height: Chart height in pixels.
    """
    high_labels = high_labels or []
    low_labels = low_labels or []
    bos = bos or None
    choch = choch or None
    equal_highs = equal_highs or []
    equal_lows = equal_lows or []
    fvgs = fvgs or []

    if data is None or data.empty:
        return

    required_columns = {"Open", "High", "Low", "Close"}

    if not required_columns.issubset(data.columns):
        raise ValueError(
            "Chart data must contain Open, High, Low, and Close columns."
        )

    chart_data = []
    ema_data = []
    markers = []
    bos_line = None
    choch_line = None
    liquidity_lines = []

    for timestamp, row in data.iterrows():
        timestamp = pd.Timestamp(timestamp)

        # Lightweight Charts accepts Unix timestamps in seconds
        unix_time = int(timestamp.timestamp())

        chart_data.append(
            {
                "time": unix_time,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
            }
        )

        # This must remain INSIDE the for loop
        if "EMA50" in data.columns and pd.notna(row["EMA50"]):
            ema_data.append(
                {
                    "time": unix_time,
                    "value": float(row["EMA50"]),
                }
            )

    for timestamp, price, label in high_labels:
        unix_time = int(pd.Timestamp(timestamp).timestamp())

        markers.append(
            {
                "time": unix_time,
                "position": "aboveBar",
                "color": "#26a69a" if label == "HH" else "#ef5350",
                "shape": "arrowDown",
                "text": label,
            }
        )

    for timestamp, price, label in low_labels:
        unix_time = int(pd.Timestamp(timestamp).timestamp())

        markers.append(
            {
                "time": unix_time,
                "position": "belowBar",
                "color": "#26a69a" if label == "HL" else "#ef5350",
                "shape": "arrowUp",
                "text": label,
            }
        )

    markers.sort(key=lambda marker: marker["time"])

    if bos is not None:

        bos_line = {
            "time": int(pd.Timestamp(bos["time"]).timestamp()),
            "price": float(bos["level"]),
            "direction": bos["direction"],
        }
    if choch is not None:
        choch_line = {
            "time": int(pd.Timestamp(choch["time"]).timestamp()),
            "price": float(choch["level"]),
            "direction": choch["direction"],
        }

    liquidity_lines = []

    for pool in equal_highs:
        liquidity_lines.append(
            {
                "type": "buy_side",
                "start_time": int(pd.Timestamp(pool["start_time"]).timestamp()),
                "end_time": int(pd.Timestamp(pool["end_time"]).timestamp()),
                "price": float(pool["level"]),
            }
        )

    for pool in equal_lows:
        liquidity_lines.append(
            {
                "type": "sell_side",
                "start_time": int(pd.Timestamp(pool["start_time"]).timestamp()),
                "end_time": int(pd.Timestamp(pool["end_time"]).timestamp()),
                "price": float(pool["level"]),
            }
        )

    candles_json = json.dumps(chart_data)
    ema_json = json.dumps(ema_data)
    markers_json = json.dumps(markers)
    bos_json = json.dumps(bos_line)
    choch_json = json.dumps(choch_line)
    liquidity_json = json.dumps(liquidity_lines)

    active_fvgs = []

    for fvg in fvgs:
        if fvg["mitigated"]:
            continue

        active_fvgs.append(
            {
                "type": fvg["type"],
                "start_time": int(
                    pd.Timestamp(fvg["start_time"]).timestamp()
                ),
                "end_time": int(
                    pd.Timestamp(fvg["end_time"]).timestamp()
                ),
                "top": float(fvg["top"]),
                "bottom": float(fvg["bottom"]),
                "mitigated": False,
            }
        )

    fvg_json = json.dumps(active_fvgs)
    setup_overlay_json = json.dumps(
        _serialize_setup_overlay(setup_overlay)
    )
    
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">

        <script
            src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js">
        </script>

        <style>
            html, body {{
                margin: 0;
                padding: 0;
                background-color: #0e1117;
                overflow: hidden;
            }}

            #chart {{
                width: 100%;
                height: {height}px;
            }}

            #setup-summary {{
                position: absolute;
                top: 10px;
                left: 10px;
                z-index: 10;
                max-width: 440px;
                padding: 8px 10px;
                border: 1px solid #374151;
                border-radius: 4px;
                color: #d1d4dc;
                background: rgba(14, 17, 23, 0.88);
                font: 12px sans-serif;
                pointer-events: none;
            }}
        </style>
    </head>

    <body>
        <div id="chart"></div>
        <div id="setup-summary"></div>

        <script>
            const chartContainer = document.getElementById("chart");

            const chart = LightweightCharts.createChart(
                chartContainer,
                {{
                    width: chartContainer.clientWidth,
                    height: {height},

                    layout: {{
                        background: {{
                            type: "solid",
                            color: "#0e1117"
                        }},
                        textColor: "#d1d4dc"
                    }},

                    grid: {{
                        vertLines: {{
                            color: "#1f2937"
                        }},
                        horzLines: {{
                            color: "#1f2937"
                        }}
                    }},

                    crosshair: {{
                        mode: LightweightCharts.CrosshairMode.Normal
                    }},

                    rightPriceScale: {{
                        borderColor: "#374151"
                    }},

                    timeScale: {{
                        borderColor: "#374151",
                        timeVisible: true,
                        secondsVisible: false
                    }}
                }}
            );

            const candleSeries = chart.addSeries(
                LightweightCharts.CandlestickSeries,
                {{
                    upColor: "#26a69a",
                    downColor: "#ef5350",
                    borderVisible: false,
                    wickUpColor: "#26a69a",
                    wickDownColor: "#ef5350"
                }}
            );

            const candleData = {candles_json};

            candleSeries.setData(candleData);

            const emaSeries = chart.addSeries(
                LightweightCharts.LineSeries,
                {{
                    title: "EMA 50",
                    lineWidth: 2,
                    priceLineVisible: false,
                    lastValueVisible: true
                }}
            );

            const emaData = {ema_json};
            emaSeries.setData(emaData);

            const structureMarkers = {markers_json};

            LightweightCharts.createSeriesMarkers(
                candleSeries,
                structureMarkers
            );

            const bosData = {bos_json};

            if (bosData !== null) {{
                const bosColor =
                    bosData.direction === "bullish"
                        ? "#26a69a"
                        : "#ef5350";

                candleSeries.createPriceLine({{
                    price: bosData.price,
                    color: bosColor,
                    lineWidth: 2,
                    lineStyle: LightweightCharts.LineStyle.Dashed,
                    axisLabelVisible: true,
                    title: "BOS"
                }});
            }}

            const chochData = {choch_json};

            if (chochData !== null) {{
                const chochColor =
                    chochData.direction === "bullish"
                        ? "#42a5f5"
                        : "#ff9800";

                candleSeries.createPriceLine({{
                    price: chochData.price,
                    color: chochColor,
                    lineWidth: 2,
                    lineStyle: LightweightCharts.LineStyle.Dotted,
                    axisLabelVisible: true,
                    title: "CHoCH"
                }});
            }}

            const liquidityData = {liquidity_json};
            const fvgData = {fvg_json};
            const setupOverlayData = {setup_overlay_json};

            liquidityData.forEach((level) => {{

                const color =
                    level.type === "buy_side"
                        ? "#00bcd4"
                        : "#ffb300";

                candleSeries.createPriceLine({{
                    price: level.price,
                    color: color,
                    lineWidth: 1,
                    lineStyle: LightweightCharts.LineStyle.Dotted,
                    axisLabelVisible: true,
                    title:
                        level.type === "buy_side"
                            ? "BSL"
                            : "SSL",
                }});

            }});

           
            fvgData.forEach((fvg) => {{

                const fvgColor =
                    fvg.type === "bullish"
                        ? "rgba(38, 166, 154, 0.25)"
                        : "rgba(239, 83, 80, 0.25)";

                const borderColor =
                    fvg.type === "bullish"
                        ? "#26a69a"
                        : "#ef5350";

                const fvgSeries = chart.addSeries(
                    LightweightCharts.BaselineSeries,
                    {{
                        baseValue: {{
                            type: "price",
                            price: fvg.bottom
                        }},
                        topFillColor1: fvgColor,
                        topFillColor2: fvgColor,
                        bottomFillColor1: fvgColor,
                        bottomFillColor2: fvgColor,
                        topLineColor: borderColor,
                        bottomLineColor: borderColor,
                        lineWidth: 1,
                        priceLineVisible: false,
                        lastValueVisible: false
                    }}
                );

                fvgSeries.setData([
                    {{
                        time: fvg.start_time,
                        value: fvg.top
                    }},
                    {{
                        time: candleData[candleData.length - 1].time,
                        value: fvg.top
                    }}
                ]);

            }});

            const overlaySummary = document.getElementById("setup-summary");

            if (setupOverlayData === null) {{
                overlaySummary.style.display = "none";
            }} else {{
                overlaySummary.innerHTML = setupOverlayData.annotations
                    .map((text) => `<div>${{text}}</div>`)
                    .join("");

                setupOverlayData.levels.forEach((level) => {{
                    const levelColor =
                        level.role === "liquidity"
                            ? "#ffb300"
                            : level.state === "confirmed_by_close"
                            ? "#26a69a"
                            : "#42a5f5";

                    candleSeries.createPriceLine({{
                        price: level.price,
                        color: levelColor,
                        lineWidth: level.importance === "primary" ? 2 : 1,
                        lineStyle:
                            level.state === "confirmed_by_close"
                                ? LightweightCharts.LineStyle.Solid
                                : LightweightCharts.LineStyle.Dashed,
                        axisLabelVisible: true,
                        title: level.label
                    }});
                }});

                if (setupOverlayData.execution_zone !== null) {{
                    const zone = setupOverlayData.execution_zone;
                    const zoneColor =
                        zone.direction === "bullish"
                            ? "rgba(38, 166, 154, 0.28)"
                            : "rgba(239, 83, 80, 0.28)";
                    const zoneBorder =
                        zone.direction === "bullish" ? "#26a69a" : "#ef5350";
                    const zoneSeries = chart.addSeries(
                        LightweightCharts.BaselineSeries,
                        {{
                            baseValue: {{ type: "price", price: zone.bottom }},
                            topFillColor1: zoneColor,
                            topFillColor2: zoneColor,
                            bottomFillColor1: zoneColor,
                            bottomFillColor2: zoneColor,
                            topLineColor: zoneBorder,
                            bottomLineColor: zoneBorder,
                            lineWidth: 2,
                            priceLineVisible: false,
                            lastValueVisible: false
                        }}
                    );
                    zoneSeries.setData([
                        {{ time: zone.start_time, value: zone.top }},
                        {{
                            time: candleData[candleData.length - 1].time,
                            value: zone.top
                        }}
                    ]);
                }}

                if (setupOverlayData.optional_ifvg_zone !== null) {{
                    const zone = setupOverlayData.optional_ifvg_zone;
                    const ifvgSeries = chart.addSeries(
                        LightweightCharts.BaselineSeries,
                        {{
                            baseValue: {{ type: "price", price: zone.bottom }},
                            topFillColor1: "rgba(168, 85, 247, 0.05)",
                            topFillColor2: "rgba(168, 85, 247, 0.05)",
                            bottomFillColor1: "rgba(168, 85, 247, 0.05)",
                            bottomFillColor2: "rgba(168, 85, 247, 0.05)",
                            topLineColor: "#a855f7",
                            bottomLineColor: "#a855f7",
                            lineStyle: LightweightCharts.LineStyle.Dashed,
                            lineWidth: 2,
                            priceLineVisible: false,
                            lastValueVisible: false
                        }}
                    );
                    ifvgSeries.setData([
                        {{ time: zone.start_time, value: zone.top }},
                        {{
                            time: candleData[candleData.length - 1].time,
                            value: zone.top
                        }}
                    ]);
                }}
            }}

            chart.timeScale().fitContent();

            const resizeObserver = new ResizeObserver(() => {{
                chart.applyOptions({{
                    width: chartContainer.clientWidth
                }});
            }});

            resizeObserver.observe(chartContainer);
        </script>
    </body>
    </html>
    """

    components.html(
        html_code,
        height=height,
        scrolling=False,
    )


def _serialize_setup_overlay(
    overlay: SetupOverlay | None,
) -> dict | None:
    """Serialize a completed overlay without deriving any strategy state."""

    if overlay is None:
        return None

    levels = []
    seen = set()

    def add_level(level, visible):
        if not visible or level is None:
            return
        key = (level.role.value, level.price, level.label)
        if key in seen:
            return
        seen.add(key)
        levels.append(
            {
                "price": level.price,
                "timeframe": level.timeframe,
                "role": level.role.value,
                "state": level.state.value,
                "label": level.label,
                "event_type": level.event_type,
                "timestamp": (
                    int(level.timestamp.timestamp())
                    if level.timestamp is not None
                    else None
                ),
                "source": level.source,
                "importance": level.importance,
            }
        )

    visibility = overlay.visibility
    add_level(
        overlay.primary_waiting_level,
        visibility.show_primary_waiting_level,
    )
    add_level(
        overlay.relevant_liquidity_level,
        visibility.show_liquidity_level,
    )
    add_level(
        overlay.confirmation_level_5m,
        visibility.show_confirmation_level,
    )
    add_level(
        overlay.trigger_level_1m,
        visibility.show_trigger_level,
    )

    execution_zone = None
    zone = overlay.active_execution_zone
    if visibility.show_execution_zone and zone is not None:
        execution_zone = {
            "top": zone.top,
            "bottom": zone.bottom,
            "timeframe": zone.timeframe,
            "direction": zone.direction.value,
            "label": zone.label,
            "start_time": int(zone.start_time.timestamp()),
            "formation_end_time": int(zone.formation_end_time.timestamp()),
            "source": zone.source,
            "importance": zone.importance,
            "kind": zone.kind.value,
            "purpose": zone.purpose.value,
            "inversion_time": (
                int(zone.inversion_time.timestamp())
                if zone.inversion_time is not None
                else None
            ),
        }

    optional_ifvg_zone = None
    zone = overlay.ifvg_support.supporting_zone
    if visibility.show_optional_ifvg_zone and zone is not None:
        optional_ifvg_zone = {
            "top": zone.top,
            "bottom": zone.bottom,
            "timeframe": zone.timeframe,
            "direction": zone.direction.value,
            "label": zone.label,
            "start_time": int(zone.start_time.timestamp()),
            "formation_end_time": int(zone.formation_end_time.timestamp()),
            "source": zone.source,
            "importance": zone.importance,
            "kind": zone.kind.value,
            "purpose": zone.purpose.value,
            "inversion_time": (
                int(zone.inversion_time.timestamp())
                if zone.inversion_time is not None
                else None
            ),
        }

    return {
        "active_playbook": overlay.active_playbook,
        "authority_status": overlay.authority_status,
        "direction": overlay.direction.value if overlay.direction else None,
        "current_phase": overlay.current_phase,
        "next_required_event": overlay.next_required_event,
        "progress_step": overlay.progress_step,
        "total_steps": overlay.total_steps,
        "completion_percentage": overlay.completion_percentage,
        "levels": levels,
        "execution_zone": execution_zone,
        "optional_ifvg_zone": optional_ifvg_zone,
        "annotations": [annotation.text for annotation in overlay.annotations],
        "limitations": list(overlay.limitations),
    }
