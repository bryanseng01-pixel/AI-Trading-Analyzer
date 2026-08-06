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

    col1, col2 = st.columns([1, 3])

    with col1:

        status = trade_plan["status"]

        if status == "READY":
            st.success("🟢 READY")

        elif status == "WATCH":
            st.warning("🟡 WATCH")

        elif status == "WAIT":
            st.info("🟡 WAIT")

        else:
            st.error("🔴 AVOID")

        st.metric(
            "Confidence",
            f'{trade_plan["confidence"]}/100'
        )
        st.write("**Playbook**")
        st.write(ict_playbook["playbook"])

        st.write("**Current Phase**")
        st.write(
            ict_playbook["phase"]
            .replace("_", " ")
            .title()
        )

    with col2:

        st.write("### Today's Market Brief")

        for sentence in market_story["story"]:
            st.write("• " + sentence)

        st.info(
            "Next Event: "
            + ict_playbook["next_event"]
        )
        with st.expander("Setup Progress"):
            if ict_playbook["reasons"]:
                st.write("**Confirmed**")

                for reason in ict_playbook["reasons"]:
                    st.markdown(f"✅ {reason}")

            if ict_playbook["missing"]:
                st.write("**Still Missing**")

                for item in ict_playbook["missing"]:
                    st.markdown(f"⏳ {item}")