import pandas as pd

# 1) Read daily data (no header row).
df_daily = pd.read_csv(
    "EURUSD1440.csv",
    header=None,
    names=["date", "time", "open", "high", "low", "close", "volume"]
)

# 2) Combine date/time into a single datetime column
df_daily["datetime"] = pd.to_datetime(df_daily["date"] + " " + df_daily["time"])

# 3) Sort ascending to ensure proper calculation of moving averages
df_daily.sort_values("datetime", ascending=True, inplace=True)

# === A) 8-Period EMA on Close (the moving average you mentioned) ===
df_daily["ema_8"] = df_daily["close"].ewm(span=8, adjust=False).mean()

# === B) MACD Calculation (MT4-like) ===

# 1. Fast EMA (13)
df_daily["ema_fast_13"] = df_daily["close"].ewm(span=13, adjust=False).mean()

# 2. Slow EMA (34)
df_daily["ema_slow_34"] = df_daily["close"].ewm(span=34, adjust=False).mean()

# 3. MACD line = (Fast EMA) - (Slow EMA)
df_daily["macd_line"] = df_daily["ema_fast_13"] - df_daily["ema_slow_34"]

# 4. Signal line (SMA of MACD line over 8 bars)
#    Note: Many standard MACD formulas use an EMA for the signal, 
#    but MT4’s default can use SMA with "MACD SMA" = 8.
df_daily["macd_signal"] = df_daily["macd_line"].rolling(window=8).mean()

# 5. MACD histogram = (MACD line) - (Signal line)
df_daily["macd_hist"] = df_daily["macd_line"] - df_daily["macd_signal"]

# 4) Now sort descending so newest data is first
df_daily.sort_values("datetime", ascending=False, inplace=True)

# 5) Slice the latest 10 records
daily_latest_10 = df_daily.head(10)

# Display relevant columns (you can add/remove as needed)
print("===== Daily (Latest 10) with EMA(8) and MACD(13,34,8) =====")
print(daily_latest_10[[
    "datetime", "open", "high", "low", "close", "volume",
    "ema_8", "macd_line", "macd_signal", "macd_hist"
]])
print()

# --- HOURLY DATA ---
df_hourly = pd.read_csv(
    "EURUSD60.csv",
    header=None,
    names=["date", "time", "open", "high", "low", "close", "volume"]
)

# Combine date/time into a single datetime column
df_hourly["datetime"] = pd.to_datetime(df_hourly["date"] + " " + df_hourly["time"])

# Sort by datetime descending
df_hourly.sort_values("datetime", ascending=False, inplace=True)

# Get the 240 most recent hourly bars
hourly_latest_240 = df_hourly.head(240)

print("----- Hourly (Latest 240 Records) -----")
print(hourly_latest_240)
