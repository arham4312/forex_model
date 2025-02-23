import pandas as pd

# --- DAILY DATA (same as your code) ---
df_daily = pd.read_csv(
    "EURUSD1440.csv",
    header=None,
    names=["date", "time", "open", "high", "low", "close", "volume"],
)
df_daily["datetime"] = pd.to_datetime(df_daily["date"] + " " + df_daily["time"])
df_daily.sort_values("datetime", ascending=True, inplace=True)

# Calculate EMA(8), MACD, etc. (unchanged from your snippet)
df_daily["ema_8"] = df_daily["close"].ewm(span=8, adjust=False).mean()
df_daily["ema_fast_13"] = df_daily["close"].ewm(span=13, adjust=False).mean()
df_daily["ema_slow_34"] = df_daily["close"].ewm(span=34, adjust=False).mean()
df_daily["macd_line"] = df_daily["ema_fast_13"] - df_daily["ema_slow_34"]
df_daily["macd_signal"] = df_daily["macd_line"].rolling(window=8).mean()
df_daily["macd_hist"] = df_daily["macd_line"] - df_daily["macd_signal"]

df_daily["last_closed_ema"] = df_daily["ema_8"].shift(1)
df_daily["one_ago_ema"] = df_daily["ema_8"].shift(2)
df_daily["last_closed_macd"] = df_daily["macd_line"].shift(1)
df_daily["one_ago_macd"] = df_daily["macd_line"].shift(2)

def get_trend_shifted(row):
    ma_last_closed = row["last_closed_ema"]
    ma_one_ago = row["one_ago_ema"]
    macd_last_closed = row["last_closed_macd"]
    macd_one_ago = row["one_ago_macd"]
    if pd.isna(ma_last_closed) or pd.isna(ma_one_ago) \
       or pd.isna(macd_last_closed) or pd.isna(macd_one_ago):
        return None
    
    ma_bullish = (ma_last_closed > ma_one_ago)
    macd_bullish = (macd_last_closed > macd_one_ago)
    ma_bearish = (ma_last_closed < ma_one_ago)
    macd_bearish = (macd_last_closed < macd_one_ago)
    
    if ma_bullish and macd_bullish:
        return "BULLISH"
    elif ma_bearish and macd_bearish:
        return "BEARISH"
    else:
        return "DIVERGENCE"

df_daily["trend"] = df_daily.apply(get_trend_shifted, axis=1)

# Sort descending if you want newest first
df_daily.sort_values("datetime", ascending=False, inplace=True)

###############################################################################
# HOURLY DATA WITH WILLIAMS %R(13)
###############################################################################
df_hourly = pd.read_csv(
    "EURUSD60.csv",
    header=None,
    names=["date", "time", "open", "high", "low", "close", "volume"],
)
df_hourly["datetime"] = pd.to_datetime(df_hourly["date"] + " " + df_hourly["time"])

# 1) Sort ascending to compute rolling
df_hourly.sort_values("datetime", ascending=True, inplace=True)

df_hourly["hh_13"] = df_hourly["high"].rolling(window=13).max()
df_hourly["ll_13"] = df_hourly["low"].rolling(window=13).min()
df_hourly["wpr_13"] = (
    (df_hourly["hh_13"] - df_hourly["close"]) 
    / (df_hourly["hh_13"] - df_hourly["ll_13"])
) * -100

# For convenience, let's create a "previous high/low" column via shift(1).
# Because data is in ascending order, shift(1) means the previous hour's high/low.
df_hourly["high_prev"] = df_hourly["high"].shift(1)
df_hourly["low_prev"] = df_hourly["low"].shift(1)

# 2) (Optional) Sort descending to view newest first
df_hourly.sort_values("datetime", ascending=False, inplace=True)

###############################################################################
# EXAMPLE: GENERATE A SIGNAL FOR 2025-02-21
###############################################################################
target_date_str = "2024-07-18"
target_date_dt = pd.to_datetime(target_date_str).date()

# --- Get daily trend for that date ---
df_daily_for_date = df_daily[df_daily["datetime"].dt.date == target_date_dt]
if df_daily_for_date.empty:
    print(f"No daily bar for {target_date_str}")
else:
    row_daily = df_daily_for_date.iloc[0]  # if only one bar per day
    daily_trend = row_daily["trend"]
    print(f"Trend for {target_date_str}: {daily_trend}")

    # Only proceed if trend is BULLISH or BEARISH
    if daily_trend not in ["BULLISH", "BEARISH"]:
        print("No signal: trend is either DIVERGENCE or None.")
    else:
        # --- Filter hourly for that same date (in ascending order) ---
        df_hourly.sort_values("datetime", ascending=True, inplace=True)
        day_start = pd.to_datetime(target_date_str + " 00:00:00")
        day_end = pd.to_datetime(target_date_str + " 23:59:59")
        
        df_hourly_day = df_hourly[
            (df_hourly["datetime"] >= day_start) &
            (df_hourly["datetime"] <= day_end)
        ].copy()

        # Which condition do we look for?
        if daily_trend == "BULLISH":
            # We want the first hour where wpr_13 < -80
            df_signal = df_hourly_day[df_hourly_day["wpr_13"] < -80]
            # We'll sort ascending so earliest hour is first
            df_signal.sort_values("datetime", ascending=True, inplace=True)

            if df_signal.empty:
                print("No BULLISH signal: no hour with W%R < -80.")
            else:
                # The first row in ascending order is our earliest signal
                first_signal = df_signal.iloc[0]
                signal_time = first_signal["datetime"]
                print(f"BULLISH signal at hour = {signal_time}, W%R={first_signal['wpr_13']:.2f}")

                # The "previous candle" is shift(1), i.e. the row’s 'high_prev'.
                # Make sure high_prev is not NaN
                if pd.notna(first_signal["high_prev"]):
                    last_closed_high = first_signal["high_prev"]
                    # 5 pips for EUR/USD = 0.00005
                    entry_stop = last_closed_high + 0.00005
                    print(f"Use last_closed candle's high ({last_closed_high}) + 5 pips => Entry Stop = {entry_stop}")
                else:
                    print("No previous candle high found for that signal hour.")

        elif daily_trend == "BEARISH":
            # We want the first hour where wpr_13 > -20
            df_signal = df_hourly_day[df_hourly_day["wpr_13"] > -20]
            df_signal.sort_values("datetime", ascending=True, inplace=True)

            if df_signal.empty:
                print("No BEARISH signal: no hour with W%R > -20.")
            else:
                first_signal = df_signal.iloc[0]
                signal_time = first_signal["datetime"]
                print(f"BEARISH signal at hour = {signal_time}, W%R={first_signal['wpr_13']:.2f}")

                if pd.notna(first_signal["low_prev"]):
                    last_closed_low = first_signal["low_prev"]
                    # 5 pips for EUR/USD = 0.00005
                    entry_stop = last_closed_low - 0.00005
                    print(f"Use last_closed candle's low ({last_closed_low}) - 5 pips => Entry Stop = {entry_stop}")
                else:
                    print("No previous candle low found for that signal hour.")