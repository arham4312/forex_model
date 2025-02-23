import pandas as pd

# 1) Read daily data
df_daily = pd.read_csv(
    "EURUSD1440.csv",
    header=None,
    names=["date", "time", "open", "high", "low", "close", "volume"],
)

df_daily["datetime"] = pd.to_datetime(df_daily["date"] + " " + df_daily["time"])
df_daily.sort_values("datetime", ascending=True, inplace=True)

# 2) Indicators
df_daily["ema_8"] = df_daily["close"].ewm(span=8, adjust=False).mean()

df_daily["ema_fast_13"] = df_daily["close"].ewm(span=13, adjust=False).mean()
df_daily["ema_slow_34"] = df_daily["close"].ewm(span=34, adjust=False).mean()
df_daily["macd_line"] = df_daily["ema_fast_13"] - df_daily["ema_slow_34"]
df_daily["macd_signal"] = df_daily["macd_line"].rolling(window=8).mean()
df_daily["macd_hist"] = df_daily["macd_line"] - df_daily["macd_signal"]

# 3) Create "last_closed" and "one_ago" columns
df_daily["last_closed_ema"] = df_daily["ema_8"].shift(1)
df_daily["one_ago_ema"] = df_daily["ema_8"].shift(2)

df_daily["last_closed_macd"] = df_daily["macd_line"].shift(1)
df_daily["one_ago_macd"] = df_daily["macd_line"].shift(2)


# 4) Define function that compares (i-1) vs (i-2)
def get_trend_shifted(row):
    ma_last_closed = row["last_closed_ema"]
    ma_one_ago = row["one_ago_ema"]
    macd_last_closed = row["last_closed_macd"]
    macd_one_ago = row["one_ago_macd"]

    if (
        pd.isna(ma_last_closed)
        or pd.isna(ma_one_ago)
        or pd.isna(macd_last_closed)
        or pd.isna(macd_one_ago)
    ):
        return None

    ma_bullish = ma_last_closed > ma_one_ago
    macd_bullish = macd_last_closed > macd_one_ago
    ma_bearish = ma_last_closed < ma_one_ago
    macd_bearish = macd_last_closed < macd_one_ago

    if ma_bullish and macd_bullish:
        return "BULLISH"
    elif ma_bearish and macd_bearish:
        return "BEARISH"
    else:
        return "DIVERGENCE"


df_daily["trend"] = df_daily.apply(get_trend_shifted, axis=1)

# 5) Now sort descending if desired
df_daily.sort_values("datetime", ascending=False, inplace=True)

# 6) Slice the latest 10 records
daily_latest_10 = df_daily.head(10)

print("===== Daily (Latest 10) with SHIFTED Trend =====")
print(
    daily_latest_10[
        ["datetime", "open", "high", "low", "close", "ema_8", "macd_line", "trend"]
    ]
)

print()

# --- HOURLY DATA (unchanged) ---
df_hourly = pd.read_csv(
    "EURUSD60.csv",
    header=None,
    names=["date", "time", "open", "high", "low", "close", "volume"],
)

# 1) Create a datetime
df_hourly["datetime"] = pd.to_datetime(df_hourly["date"] + " " + df_hourly["time"])

# 2) Sort ascending so rolling() goes from oldest to newest
df_hourly.sort_values("datetime", ascending=True, inplace=True)

# 3) Compute HighestHigh and LowestLow over the past 13 bars
df_hourly["hh_13"] = df_hourly["high"].rolling(window=13).max()
df_hourly["ll_13"] = df_hourly["low"].rolling(window=13).min()

# 4) Compute Williams %R (Period=13)
df_hourly["wpr_13"] = (
    (df_hourly["hh_13"] - df_hourly["close"]) 
    / (df_hourly["hh_13"] - df_hourly["ll_13"])
) * -100

# 5) If you want newest rows first now, sort descending
df_hourly.sort_values("datetime", ascending=False, inplace=True)

# 6) Get the latest 240 hourly bars
hourly_latest_240 = df_hourly.head(240)

print("----- Hourly (Latest 240 Records w/ Williams%R(13)) -----")
print(hourly_latest_240[[
    "datetime", "open", "high", "low", "close", "volume", "wpr_13"
]])