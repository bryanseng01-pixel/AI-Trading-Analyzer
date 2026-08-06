import streamlit as st


def render_market_brief(
    trade_plan,
    market_story,
    ict_playbook,
):
    """
    Renders the main AI Trading Assistant panel.
    """

    st.subheader("🧠 AI Trading Assistant")

    status = trade_plan["status"]
    if status == "READY":
        st.success("🟢 READY")
    elif status == "WATCH":
        st.warning("🟡 WATCH")
    elif status == "WAIT":
        st.info("🟡 WAIT")
    else:
        st.error("🔴 AVOID")

    status_col, bias_col, confidence_col, phase_col = st.columns(4)
    status_col.metric("Status", status)
    bias_col.metric("Bias", trade_plan["bias"])
    confidence_col.metric("Authority Confidence", f'{trade_plan["confidence"]}/100')
    phase_col.metric(
        "Playbook Phase",
        ict_playbook["phase"].replace("_", " ").title(),
    )

    st.write("### Today's Market Story")
    for sentence in market_story:
        st.write("• " + sentence)

    st.info("Next Event: " + ict_playbook["next_event"])
    st.success("Next Action: " + trade_plan["next_action"])


def render_setup_progress(trade_plan):
    """Render progress using only DecisionAuthority gate results."""

    st.subheader("📋 Authority Setup Progress")
    confirmed = trade_plan["reasons"]
    missing = trade_plan["missing"]
    total = len(confirmed) + len(missing)
    completed = len(confirmed)
    progress = completed / total if total else 0.0

    st.metric("Completed Authority Gates", f"{completed}/{total}")
    st.progress(progress)

    confirmed_col, missing_col = st.columns(2)
    with confirmed_col:
        st.write("**Confirmed Conditions**")
        if confirmed:
            for reason in confirmed:
                st.markdown(f"✅ {reason}")
        else:
            st.caption("No authority gates are confirmed.")

    with missing_col:
        st.write("**Missing Conditions**")
        if missing:
            for item in missing:
                st.markdown(f"⏳ {item}")
        else:
            st.caption("No authority gates are missing.")
