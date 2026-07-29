def generate_trade_checklist(
    trend,
    structure,
    bos,
    choch,
    bullish_fvgs,
    bearish_fvgs,
):
    """
    Generates a trade readiness checklist.
    """

    checklist = []

    score = 0

    # Trend

    trend_ok = (
        "BULLISH" in trend
        or "BEARISH" in trend
    )

    checklist.append(
        ("4H / 1H Trend", trend_ok)
    )

    if trend_ok:
        score += 20

    # Structure

    structure_ok = (
        structure in
        [
            "Bullish Structure",
            "Bearish Structure",
        ]
    )

    checklist.append(
        ("1H Structure", structure_ok)
    )

    if structure_ok:
        score += 20

    # BOS

    bos_ok = bos is not None

    checklist.append(
        ("15M Setup", bos_ok)
    )

    if bos_ok:
        score += 20

    # CHoCH

    choch_ok = choch is not None

    checklist.append(
        ("5M Confirmation", choch_ok)
    )

    if choch_ok:
        score += 15

    # FVG

    fvg_ok = (
        len(bullish_fvgs)
        + len(bearish_fvgs)
        > 0
    )

    checklist.append(
        ("1M Trigger Zone", fvg_ok)
    )

    if fvg_ok:
        score += 15

    # Recommendation

    if score >= 80:

        recommendation = "TRADE"

    elif score >= 60:

        recommendation = "WATCH"

    else:

        recommendation = "WAIT"

    return (
        checklist,
        score,
        recommendation,
    )