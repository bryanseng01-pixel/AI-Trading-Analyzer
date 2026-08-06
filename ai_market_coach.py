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
    Generates a directional market summary.

    The score measures how strongly the available evidence agrees,
    not whether the market is bullish or bearish.
    """

    reasoning = []

    bullish_points = 0
    bearish_points = 0
    evidence_count = 0

    # Trend
    if "BULLISH" in trend:
        bullish_points += 30
        evidence_count += 1
        reasoning.append("The EMA trend is bullish.")

    elif "BEARISH" in trend:
        bearish_points += 30
        evidence_count += 1
        reasoning.append("The EMA trend is bearish.")

    # Market structure
    if structure == "Bullish Structure":
        bullish_points += 25
        evidence_count += 1
        reasoning.append("Price is forming higher highs and higher lows.")

    elif structure == "Bearish Structure":
        bearish_points += 25
        evidence_count += 1
        reasoning.append("Price is forming lower highs and lower lows.")

    else:
        reasoning.append(
            "Market structure is mixed or transitioning."
        )

    # BOS
    if bos_status is not None:
        evidence_count += 1

        if bos_status["direction"] == "bullish":
            bullish_points += 20
            reasoning.append(
                "A bullish Break of Structure confirms upward continuation."
            )

        elif bos_status["direction"] == "bearish":
            bearish_points += 20
            reasoning.append(
                "A bearish Break of Structure confirms downward continuation."
            )
    else:
        reasoning.append("No continuation BOS is currently confirmed.")

    # CHoCH
    if choch_status is not None:
        evidence_count += 1

        if choch_status["direction"] == "bullish":
            bullish_points += 15
            reasoning.append(
                "A bullish Change of Character suggests a possible reversal upward."
            )

        elif choch_status["direction"] == "bearish":
            bearish_points += 15
            reasoning.append(
                "A bearish Change of Character suggests a possible reversal downward."
            )
    else:
        reasoning.append("No opposing CHoCH is currently confirmed.")

    # Active FVGs
    if bullish_fvgs:
        bullish_points += min(len(bullish_fvgs) * 5, 10)
        evidence_count += 1
        reasoning.append(
            f"{len(bullish_fvgs)} nearby active bullish FVG(s) remain."
        )

    if bearish_fvgs:
        bearish_points += min(len(bearish_fvgs) * 5, 10)
        evidence_count += 1
        reasoning.append(
            f"{len(bearish_fvgs)} nearby active bearish FVG(s) remain."
        )

    # Liquidity is context, not automatically directional
    if equal_highs:
        reasoning.append(
            "Buy-side liquidity is available above price."
        )

    if equal_lows:
        reasoning.append(
            "Sell-side liquidity is available below price."
        )

    # Determine directional alignment
    point_difference = abs(bullish_points - bearish_points)
    strongest_side = max(bullish_points, bearish_points)

    if bullish_points >= bearish_points + 20:
        market_bias = "Bullish"

    elif bearish_points >= bullish_points + 20:
        market_bias = "Bearish"

    else:
        market_bias = "Neutral / Conflicting"

    # Confidence score measures alignment
    if market_bias == "Neutral / Conflicting":
        score = max(20, min(55, 55 - point_difference))
    else:
        score = min(
            100,
            strongest_side + point_difference // 2,
        )

    # Reduce confidence when little evidence exists
    if evidence_count <= 2:
        score = min(score, 55)

    score = int(max(0, min(100, score)))

    if score >= 80:
        confidence = "High"

    elif score >= 60:
        confidence = "Moderate"

    else:
        confidence = "Low"

    # Game plan
    if market_bias == "Bullish":
        game_plan = (
            "Bullish conditions are better aligned. "
            "Wait for a pullback into a relevant bullish zone "
            "and require lower-timeframe confirmation before considering a long."
        )

    elif market_bias == "Bearish":
        game_plan = (
            "Bearish conditions are better aligned. "
            "Wait for a retracement into a relevant bearish zone "
            "and require lower-timeframe confirmation before considering a short."
        )

    else:
        game_plan = (
            "Conditions are conflicting. Avoid forcing a trade and wait "
            "for BOS, CHoCH, or stronger multi-timeframe alignment."
        )

    reasoning.insert(
        0,
        f"Overall market bias: {market_bias}.",
    )

    return reasoning, confidence, score, game_plan

def generate_multi_timeframe_narrative(results):
    """
    Creates a single narrative from all analyzed timeframes.

    results should look like:

    [
        {
            "timeframe": "4 Hour",
            "trend": "...",
            "structure": "...",
            "bos": ...,
            "choch": ...
        },
        ...
    ]
    """

    narrative = []

    higher_timeframes = results[:-1]
    lower_timeframe = results[-1]

    bearish_htf = sum(
        "BEARISH" in r["trend"]
        for r in higher_timeframes
    )

    bullish_htf = sum(
        "BULLISH" in r["trend"]
        for r in higher_timeframes
    )

    if bearish_htf > bullish_htf:

        narrative.append(
            "Higher timeframes remain bearish."
        )

    elif bullish_htf > bearish_htf:

        narrative.append(
            "Higher timeframes remain bullish."
        )

    else:

        narrative.append(
            "Higher timeframes are mixed."
        )

    # Lower timeframe

    if "BULLISH" in lower_timeframe["trend"]:

        if bearish_htf > bullish_htf:

            narrative.append(
                "The lower timeframe is currently rallying against the higher timeframe trend."
            )

            narrative.append(
                "This move may represent a pullback rather than a full trend reversal."
            )

        else:

            narrative.append(
                "The lower timeframe aligns with the higher timeframe trend."
            )

    elif "BEARISH" in lower_timeframe["trend"]:

        if bullish_htf > bearish_htf:

            narrative.append(
                "The lower timeframe is pulling back against the higher timeframe trend."
            )

        else:

            narrative.append(
                "The lower timeframe remains aligned with the higher timeframe."
            )

    narrative.append(
        "Wait for lower timeframe confirmation before entering."
    )

    return narrative

def build_market_story(timeframe_results):
    """
    Combine the 4H, 1H, 15M, 5M, and 1M trends
    into one clear market narrative.
    """

    four_hour = timeframe_results["4 Hour"]["trend"]
    one_hour = timeframe_results["1 Hour"]["trend"]
    fifteen_minute = timeframe_results["15 Minute"]["trend"]
    five_minute = timeframe_results["5 Minute"]["trend"]
    one_minute = timeframe_results["1 Minute"]["trend"]

    story = []

    htf_bullish = (
        "BULLISH" in four_hour
        and "BULLISH" in one_hour
    )

    htf_bearish = (
        "BEARISH" in four_hour
        and "BEARISH" in one_hour
    )

    if htf_bullish:
        context = "Bullish"
        story.append(
            "The 4-hour and 1-hour timeframes are aligned bullish."
        )

    elif htf_bearish:
        context = "Bearish"
        story.append(
            "The 4-hour and 1-hour timeframes are aligned bearish."
        )

    else:
        context = "Mixed"
        story.append(
            "The higher timeframes are not fully aligned."
        )

    if context == "Bearish" and "BULLISH" in fifteen_minute:
        setup = "Bullish pullback"
        story.append(
            "The 15-minute chart is rallying against the higher-timeframe bearish trend."
        )
        story.append(
            "This currently looks more like a pullback than a confirmed bullish reversal."
        )

    elif context == "Bullish" and "BEARISH" in fifteen_minute:
        setup = "Bearish pullback"
        story.append(
            "The 15-minute chart is pulling back against the higher-timeframe bullish trend."
        )
        story.append(
            "This currently looks more like a retracement than a confirmed bearish reversal."
        )

    elif context == "Bearish" and "BEARISH" in fifteen_minute:
        setup = "Bearish continuation"
        story.append(
            "The 15-minute chart remains aligned with the bearish higher-timeframe trend."
        )

    elif context == "Bullish" and "BULLISH" in fifteen_minute:
        setup = "Bullish continuation"
        story.append(
            "The 15-minute chart remains aligned with the bullish higher-timeframe trend."
        )

    else:
        setup = "Unclear"
        story.append(
            "The 15-minute setup is currently unclear."
        )

    if context == "Bearish":
        five_minute_confirmed = "BEARISH" in five_minute
        one_minute_confirmed = "BEARISH" in one_minute

    elif context == "Bullish":
        five_minute_confirmed = "BULLISH" in five_minute
        one_minute_confirmed = "BULLISH" in one_minute

    else:
        five_minute_confirmed = False
        one_minute_confirmed = False

    if five_minute_confirmed:
        story.append(
            "The 5-minute chart supports the higher-timeframe direction."
        )
    else:
        story.append(
            "The 5-minute chart has not confirmed the higher-timeframe direction yet."
        )

    if one_minute_confirmed:
        execution = "Confirmed"
        story.append(
            "The 1-minute chart is aligned for execution."
        )
    else:
        execution = "Waiting"
        story.append(
            "The 1-minute execution trigger is still missing."
        )

    if context == "Mixed":
        decision = "AVOID"

    elif five_minute_confirmed and one_minute_confirmed:
        decision = "WATCH"

    else:
        decision = "WAIT"

    return {
        "context": context,
        "setup": setup,
        "execution": execution,
        "decision": decision,
        "story": story,
    }

    