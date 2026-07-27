def generate_market_summary(
    trend,
    structure,
    bos_status,
    choch_status,
    bullish_fvgs,
    bearish_fvgs,
    equal_highs,
    equal_lows,
):
    """
    Generates an AI market summary.
    """

    reasoning = []
    score = 50

    # Trend
    if trend == "BULLISH 🟢":
        reasoning.append("Higher timeframe trend is bullish.")
        score += 10
    else:
        reasoning.append("Higher timeframe trend is bearish.")
        score -= 10

    # Structure
    reasoning.append(f"Current market structure is {structure}.")

    # BOS
    if bos_status is not None:
        if bos_status["direction"] == "bullish":
            reasoning.append("Bullish Break of Structure confirmed.")
            score += 10

        elif bos_status["direction"] == "bearish":
            reasoning.append("Bearish Break of Structure confirmed.")
            score -= 10

    # CHoCH
    if choch_status is not None:
        if choch_status["direction"] == "bullish":
            reasoning.append("Bullish Change of Character detected.")
            score += 5

        elif choch_status["direction"] == "bearish":
            reasoning.append("Bearish Change of Character detected.")
            score -= 5

    # Liquidity
    if equal_highs:
        reasoning.append("Buy-side liquidity remains available.")

    if equal_lows:
        reasoning.append("Sell-side liquidity remains available.")

    # FVG
    if bullish_fvgs:
        reasoning.append(
            f"{len(bullish_fvgs)} active bullish FVG(s)."
        )

    if bearish_fvgs:
        reasoning.append(
            f"{len(bearish_fvgs)} active bearish FVG(s)."
        )

    score = max(0, min(100, score))

    if score >= 70:
        confidence = "High"

    elif score >= 40:
        confidence = "Moderate"

    else:
        confidence = "Low"

    if trend == "BULLISH 🟢":
        game_plan = (
            "Wait for bullish confirmation before entering long."
        )
    else:
        game_plan = (
            "Wait for bearish confirmation before entering short."
        )

    return reasoning, confidence, score, game_plan