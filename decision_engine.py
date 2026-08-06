def build_trade_plan(
    trend,
    structure,
    bos,
    choch,
    bullish_fvgs,
    bearish_fvgs,
    session_levels,
):
    """
    Build one simple trade plan from the current analysis.

    This first version focuses on:
    - directional bias
    - setup readiness
    - missing confirmation
    - concise explanation
    """

    bullish_points = 0
    bearish_points = 0
    missing = []
    reasons = []

    # -------------------------
    # 1. Trend
    # -------------------------
    if "BULLISH" in trend:
        bullish_points += 25
        reasons.append("Trend supports bullish conditions.")

    elif "BEARISH" in trend:
        bearish_points += 25
        reasons.append("Trend supports bearish conditions.")

    # -------------------------
    # 2. Market structure
    # -------------------------
    if structure == "Bullish Structure":
        bullish_points += 25
        reasons.append("Market structure is bullish.")

    elif structure == "Bearish Structure":
        bearish_points += 25
        reasons.append("Market structure is bearish.")

    else:
        missing.append("Clear market structure")

    # -------------------------
    # 3. BOS
    # -------------------------
    if bos is not None:
        if bos["direction"] == "bullish":
            bullish_points += 20
            reasons.append("Bullish BOS is confirmed.")

        elif bos["direction"] == "bearish":
            bearish_points += 20
            reasons.append("Bearish BOS is confirmed.")
    else:
        missing.append("Continuation BOS")

    # -------------------------
    # 4. CHoCH
    # -------------------------
    if choch is not None:
        if choch["direction"] == "bullish":
            bullish_points += 15
            reasons.append("Bullish CHoCH is confirmed.")

        elif choch["direction"] == "bearish":
            bearish_points += 15
            reasons.append("Bearish CHoCH is confirmed.")
    else:
        missing.append("Lower-timeframe CHoCH")

    # -------------------------
    # 5. FVG context
    # -------------------------
    if bullish_fvgs:
        bullish_points += 10
        reasons.append(
            f"{len(bullish_fvgs)} active bullish FVG(s) remain."
        )

    if bearish_fvgs:
        bearish_points += 10
        reasons.append(
            f"{len(bearish_fvgs)} active bearish FVG(s) remain."
        )

    if not bullish_fvgs and not bearish_fvgs:
        missing.append("Relevant active FVG")

    # -------------------------
    # 6. Session liquidity
    # -------------------------
    untouched_session_levels = []

    for session_name, session in session_levels.items():
        if not session.get("high_swept", False):
            untouched_session_levels.append(
                f"{session_name} High"
            )

        if not session.get("low_swept", False):
            untouched_session_levels.append(
                f"{session_name} Low"
            )

    if untouched_session_levels:
        reasons.append(
            "Untouched session liquidity remains available."
        )
    else:
        missing.append("Untouched session liquidity")

    # -------------------------
    # 7. Direction
    # -------------------------
    point_difference = abs(
        bullish_points - bearish_points
    )

    if bullish_points >= bearish_points + 20:
        bias = "Bullish"
        dominant_points = bullish_points

    elif bearish_points >= bullish_points + 20:
        bias = "Bearish"
        dominant_points = bearish_points

    else:
        bias = "Neutral / Conflicting"
        dominant_points = max(
            bullish_points,
            bearish_points,
        )

    # -------------------------
    # 8. Confidence
    # -------------------------
    confidence = min(
        100,
        int(dominant_points + point_difference / 2),
    )

    if bias == "Neutral / Conflicting":
        confidence = min(confidence, 55)

    # -------------------------
    # 9. Status
    # -------------------------
    confirmation_missing = (
        "Lower-timeframe CHoCH" in missing
    )

    if bias == "Neutral / Conflicting":
        status = "AVOID"

    elif confidence >= 80 and not confirmation_missing:
        status = "READY"

    elif confidence >= 60:
        status = "WATCH"

    else:
        status = "WAIT"

    # -------------------------
    # 10. Next action
    # -------------------------
    if status == "READY":
        next_action = (
            f"{bias} conditions are aligned. "
            "Validate the entry location, invalidation level, "
            "and risk-to-reward before taking the trade."
        )

    elif status == "WATCH":
        next_action = (
            f"{bias} conditions are developing. "
            "Wait for the missing confirmation before entering."
        )

    elif status == "WAIT":
        next_action = (
            "The setup is incomplete. Stay patient and wait "
            "for stronger alignment."
        )

    else:
        next_action = (
            "Conditions conflict. Avoid forcing a directional trade."
        )

    return {
        "status": status,
        "bias": bias,
        "confidence": confidence,
        "bullish_points": bullish_points,
        "bearish_points": bearish_points,
        "missing": missing,
        "reasons": reasons,
        "untouched_session_levels": untouched_session_levels,
        "next_action": next_action,
        "entry_zone": None,
        "stop": None,
        "targets": [],
    }