import pandas as pd


SESSION_WINDOWS = {
    "Asia": ("18:00", "03:00"),
    "London": ("03:00", "08:30"),
    "New York": ("08:30", "17:00"),
}


def _to_new_york_time(data):
    """
    Return a copy of the dataframe with its index converted
    to America/New_York.
    """

    session_data = data.copy()
    index = pd.DatetimeIndex(session_data.index)

    if index.tz is None:
        index = index.tz_localize("UTC")

    index = index.tz_convert("America/New_York")
    session_data.index = index

    return session_data


def _session_mask(index, start_time, end_time):
    """
    Build a boolean mask for a session.

    Handles sessions such as Asia that cross midnight.
    """

    clock_times = index.time

    start = pd.Timestamp(start_time).time()
    end = pd.Timestamp(end_time).time()

    if start < end:
        return (clock_times >= start) & (clock_times < end)

    return (clock_times >= start) | (clock_times < end)


def detect_session_levels(data):
    """
    Detect the latest Asia, London, and New York session highs/lows.

    Returns:
        A dictionary containing each session's high, low,
        start time, and end time.
    """

    if data is None or data.empty:
        return {}

    session_data = _to_new_york_time(data)
    latest_timestamp = session_data.index[-1]
    current_date = latest_timestamp.date()

    results = {}

    for session_name, (start_time, end_time) in SESSION_WINDOWS.items():
        mask = _session_mask(
            session_data.index,
            start_time,
            end_time,
        )

        filtered = session_data.loc[mask]

        if filtered.empty:
            continue

        if session_name == "Asia":
            latest_time = latest_timestamp.time()
            asia_end = pd.Timestamp("03:00").time()
            asia_start = pd.Timestamp("18:00").time()

            if latest_time >= asia_start:
                # We are currently inside the evening portion
                # of today's Asia session.
                session_start_date = current_date
            else:
                # Before 6 PM, use the Asia session that began yesterday.
                session_start_date = (
                    pd.Timestamp(current_date)
                    - pd.Timedelta(days=1)
                ).date()

            start_timestamp = pd.Timestamp(
                f"{session_start_date} {start_time}",
                tz="America/New_York",
            )

            end_timestamp = start_timestamp + pd.Timedelta(hours=9)
        else:
            session_start_clock = pd.Timestamp(start_time).time()

            if latest_timestamp.time() >= session_start_clock:
                session_date = current_date
            else:
                session_date = (
                    pd.Timestamp(current_date)
                    - pd.Timedelta(days=1)
                ).date()

            start_timestamp = pd.Timestamp(
                f"{session_date} {start_time}",
                tz="America/New_York",
            )

            end_timestamp = pd.Timestamp(
                f"{session_date} {end_time}",
                tz="America/New_York",
            )

        current_session = filtered[
            (filtered.index >= start_timestamp)
            & (filtered.index < end_timestamp)
        ]

        if current_session.empty:
            continue

        session_high = float(current_session["High"].max())
        session_low = float(current_session["Low"].min())

        candles_after_session = session_data[
            session_data.index > end_timestamp
        ]

        high_swept = False
        low_swept = False
        high_sweep_time = None
        low_sweep_time = None

        if not candles_after_session.empty:
            high_breaks = candles_after_session[
                candles_after_session["High"] > session_high
            ]

            low_breaks = candles_after_session[
                candles_after_session["Low"] < session_low
            ]

            if not high_breaks.empty:
                high_swept = True
                high_sweep_time = high_breaks.index[0]

            if not low_breaks.empty:
                low_swept = True
                low_sweep_time = low_breaks.index[0]

        results[session_name] = {
            "high": session_high,
            "low": session_low,
            "start_time": current_session.index[0],
            "end_time": current_session.index[-1],
            "high_swept": high_swept,
            "low_swept": low_swept,
            "high_sweep_time": high_sweep_time,
            "low_sweep_time": low_sweep_time,
        }
    return results