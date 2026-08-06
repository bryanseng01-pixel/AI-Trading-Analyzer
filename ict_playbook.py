def evaluate_ict_liquidity_sweep_playbook(
    htf_bias,
    setup_structure,
    confirmation_structure,
    trigger_structure,
    active_fvgs,
    session_levels,
):
    """
    Evaluate the first ICT playbook:

    Liquidity Sweep
        -> MSS / CHoCH
        -> Displacement
        -> FVG / IFVG retracement
        -> Entry confirmation

    This first version tracks the playbook state.
    It does not generate an entry, stop, or target yet.
    """

    direction = None
    phase = "waiting_for_context"
    status = "NO SETUP"
    next_event = "Wait for higher-timeframe directional alignment."
    reasons = []
    missing = []

    htf_context_ok = False
    liquidity_swept = False
    mss_confirmed = False
    execution_fvg_available = False

    # 1. Higher-timeframe directional context
    if htf_bias == "Bullish":
        direction = "bullish"
        htf_context_ok = True
        reasons.append("Higher-timeframe context is bullish.")

    elif htf_bias == "Bearish":
        direction = "bearish"
        htf_context_ok = True
        reasons.append("Higher-timeframe context is bearish.")

    else:
        missing.append("Clear higher-timeframe direction")

    # 2. Relevant session-liquidity sweep
    if direction == "bearish":
        liquidity_swept = any(
            session.get("high_swept", False)
            for session in session_levels.values()
        )

        if liquidity_swept:
            reasons.append(
                "Buy-side session liquidity has been swept."
            )
        else:
            missing.append("Buy-side liquidity sweep")

    elif direction == "bullish":
        liquidity_swept = any(
            session.get("low_swept", False)
            for session in session_levels.values()
        )

        if liquidity_swept:
            reasons.append(
                "Sell-side session liquidity has been swept."
            )
        else:
            missing.append("Sell-side liquidity sweep")

    # 3. Lower-timeframe market-structure shift
    if direction == "bearish":
        mss_confirmed = (
            confirmation_structure == "bearish"
            or trigger_structure == "bearish"
        )

        if mss_confirmed:
            reasons.append(
                "Lower-timeframe bearish structure shift is confirmed."
            )
        else:
            missing.append("Bearish 5M or 1M MSS / CHoCH")

    elif direction == "bullish":
        mss_confirmed = (
            confirmation_structure == "bullish"
            or trigger_structure == "bullish"
        )

        if mss_confirmed:
            reasons.append(
                "Lower-timeframe bullish structure shift is confirmed."
            )
        else:
            missing.append("Bullish 5M or 1M MSS / CHoCH")

    # 4. Execution imbalance
    if direction is not None:
        execution_fvg_available = any(
            fvg["type"] == direction
            for fvg in active_fvgs
        )

        if execution_fvg_available:
            reasons.append(
                f"An active {direction} execution FVG is available."
            )
        else:
            missing.append(
                f"Active {direction} execution FVG or IFVG"
            )

    # 5. Determine current playbook phase
    if not htf_context_ok:
        phase = "waiting_for_context"
        status = "NO SETUP"
        next_event = "Wait for 4H and 1H directional alignment."

    elif not liquidity_swept:
        phase = "waiting_for_liquidity"
        status = "DEVELOPING"
        next_event = (
            "Wait for the relevant session liquidity to be swept."
        )

    elif not mss_confirmed:
        phase = "waiting_for_mss"
        status = "WATCH"
        next_event = (
            "Wait for a 5M or 1M MSS / CHoCH confirmed by candle close."
        )

    elif not execution_fvg_available:
        phase = "waiting_for_execution_zone"
        status = "WATCH"
        next_event = (
            "Wait for a valid FVG or IFVG execution zone."
        )

    else:
        phase = "execution_zone_available"
        status = "CANDIDATE"
        next_event = (
            "Wait for price to retrace into the execution zone "
            "and confirm order flow before entry."
        )

    return {
        "playbook": "ICT Liquidity Sweep Reversal",
        "direction": direction,
        "phase": phase,
        "status": status,
        "htf_context_ok": htf_context_ok,
        "liquidity_swept": liquidity_swept,
        "mss_confirmed": mss_confirmed,
        "execution_fvg_available": execution_fvg_available,
        "reasons": reasons,
        "missing": missing,
        "next_event": next_event,
        "entry_zone": None,
        "stop": None,
        "targets": [],
        "volume_profile_state": "not_connected",
        "order_flow_state": "not_connected",
    }