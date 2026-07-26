import json

import pandas as pd
import streamlit.components.v1 as components


def display_tradingview_chart(
    data: pd.DataFrame,
    high_labels=None,
    low_labels=None,
    bos=None,
    choch=None,
    equal_highs=None,
    equal_lows=None,
    fvgs=None,
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
        </style>
    </head>

    <body>
        <div id="chart"></div>

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