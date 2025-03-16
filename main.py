from fastapi import FastAPI, HTTPException
import pandas as pd
import json
import re
import os
from datetime import timedelta, datetime
from openai import OpenAI

app = FastAPI()

###############################################################################
# 0) SET YOUR OPENAI API KEY
###############################################################################
client = OpenAI(
    api_key="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"
)

###############################################################################
# 1) DAILY DATA: EMA(8), MACD, SHIFTED TREND
###############################################################################
df_daily = pd.read_csv(
    "EURUSD1440.csv",
    header=None,
    names=["date", "time", "open", "high", "low", "close", "volume"],
)
df_daily["datetime"] = pd.to_datetime(df_daily["date"] + " " + df_daily["time"])
df_daily.sort_values("datetime", ascending=True, inplace=True)

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
df_daily.sort_values("datetime", ascending=False, inplace=True)

###############################################################################
# 2) HOURLY DATA: WILLIAMS %R(13)
###############################################################################
df_hourly = pd.read_csv(
    "EURUSD60.csv",
    header=None,
    names=["date", "time", "open", "high", "low", "close", "volume"],
)
df_hourly["datetime"] = pd.to_datetime(df_hourly["date"] + " " + df_hourly["time"])
df_hourly.sort_values("datetime", ascending=True, inplace=True)

df_hourly["hh_13"] = df_hourly["high"].rolling(window=13).max()
df_hourly["ll_13"] = df_hourly["low"].rolling(window=13).min()
df_hourly["wpr_13"] = (
    (df_hourly["hh_13"] - df_hourly["close"])
    / (df_hourly["hh_13"] - df_hourly["ll_13"])
) * -100

df_hourly["high_prev"] = df_hourly["high"].shift(1)
df_hourly["low_prev"] = df_hourly["low"].shift(1)

df_hourly.sort_values("datetime", ascending=False, inplace=True)

###############################################################################
# 3) WRAP THE EXISTING LOGIC INTO A FUNCTION (UNCHANGED INSIDE)
###############################################################################
def process_signal_for_date(target_date_str):
    """
    Runs your existing logic for a single date, including GPT call.
    Returns:
      - A dictionary with all trade info if a signal is generated
      - A dictionary with {"Date": <date>, "NoSignal": "reason"} if no signal
    """
    trade_data = None
    target_date_dt = pd.to_datetime(target_date_str).date()

    # Filter daily data for the target date
    df_daily_for_date = df_daily[df_daily["datetime"].dt.date == target_date_dt]
    if df_daily_for_date.empty:
        return {"Date": target_date_str, "NoSignal": "No daily bar"}
    else:
        row_daily = df_daily_for_date.iloc[0]
        daily_trend = row_daily["trend"]
        print(f"Trend for {target_date_str}: {daily_trend}")

        if daily_trend not in ["BULLISH", "BEARISH"]:
            return {"Date": target_date_str, "NoSignal": "Trend is DIVERGENCE or None"}

        # Filter hourly data for the day
        df_hourly.sort_values("datetime", ascending=True, inplace=True)
        day_start = pd.to_datetime(target_date_str + " 00:00:00")
        day_end = pd.to_datetime(target_date_str + " 23:59:59")

        df_hourly_day = df_hourly[
            (df_hourly["datetime"] >= day_start) & (df_hourly["datetime"] <= day_end)
        ].copy()

        # Get the first valid signal based on the trend
        if daily_trend == "BULLISH":
            df_signal = df_hourly_day[df_hourly_day["wpr_13"] < -80]
        else:
            df_signal = df_hourly_day[df_hourly_day["wpr_13"] > -20]

        df_signal.sort_values("datetime", ascending=True, inplace=True)
        if df_signal.empty:
            return {"Date": target_date_str, "NoSignal": "No W%R signal found"}

        first_signal = df_signal.iloc[0]
        signal_time = first_signal["datetime"]
        wpr_value = first_signal["wpr_13"]
        print(f"{daily_trend} signal at hour = {signal_time}, W%R={wpr_value:.2f}")

        # Calculate entry_stop based on previous candle high/low
        entry_stop = None
        if daily_trend == "BULLISH":
            if pd.notna(first_signal["high_prev"]):
                last_closed_high = first_signal["high_prev"]
                entry_stop = last_closed_high + 0.00005  # 5 pips
                print(f"Entry Stop = {entry_stop} (previous high + 0.00005)")
            else:
                return {"Date": target_date_str, "NoSignal": "No previous candle high"}
        else:
            if pd.notna(first_signal["low_prev"]):
                last_closed_low = first_signal["low_prev"]
                entry_stop = last_closed_low - 0.00005
                print(f"Entry Stop = {entry_stop} (previous low - 0.00005)")
            else:
                return {"Date": target_date_str, "NoSignal": "No previous candle low"}

        if entry_stop is None:
            return {"Date": target_date_str, "NoSignal": "entry_stop was None"}

        # 4) CALL OPENAI GPT API FOR SUPPORT / RESISTANCE
        start_14_days = day_start - pd.Timedelta(days=14)
        df_hourly.sort_values("datetime", ascending=True, inplace=True)
        df_30days = df_hourly[
            (df_hourly["datetime"] >= start_14_days) & (df_hourly["datetime"] < day_start)
        ].copy()
        data_string = df_30days.to_csv(index=False)

        sr_prompt = f"""
Given the past 14 days of hourly EUR/USD data (Open, High, Low, Close, Volume):
Identify the Support and Resistance levels using the following method:

Resistance Level:
Select the most recent prominent swing high, a price point where the market has recently struggled or failed to move above.

Support Level:
Identify the most recent prominent swing low, a clear price level where downward movement stopped, and price moved significantly upward afterward.

**Output format (STRICTLY FOLLOW THIS FORMAT):**
{{
  "resistance": "RESISTANCE_VALUE",
  "support": "SUPPORT_VALUE"
}}

CURRENT DATA (Last 14 Days):
{data_string}
"""

        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a trading assistant that outputs JSON only.",
                    },
                    {"role": "user", "content": sr_prompt},
                ],
                temperature=0.0,
            )
            raw_content = response.choices[0].message.content
            raw_content_clean = re.sub(r"```(?:json)?\s*", "", raw_content)
            raw_content_clean = re.sub(r"```", "", raw_content_clean)

            try:
                sr_data = json.loads(raw_content_clean)
                support_val = float(sr_data["support"])
                resistance_val = float(sr_data["resistance"])
                print("GPT S/R =>", sr_data)
                print(
                    f"Parsed => Support = {support_val}, Resistance = {resistance_val}"
                )

                # 5) Compute final trade parameters
                entry_price = None
                stop_price = None
                limit_price = None
                account_size = 100000  # in USD
                risk_pct = 0.075  # 7.5%
                risk_amount = account_size * risk_pct
                pip_cost = 10  # Approx. pip cost for EUR/USD per standard lot
                pip_lots = None

                if daily_trend == "BULLISH":
                    condition = (resistance_val - entry_stop) > (entry_stop - support_val)
                else:
                    condition = (resistance_val - entry_stop) < (entry_stop - support_val)

                if condition is None:
                    entry_price = None
                elif condition:
                    entry_price = entry_stop
                else:
                    entry_price = ((resistance_val - support_val) / 2.0) + support_val

                if daily_trend == "BULLISH":
                    stop_price = support_val - 0.0005
                    limit_price = resistance_val - 0.0001
                else:
                    stop_price = resistance_val + 0.0005
                    limit_price = support_val + 0.0001

                if entry_price is not None and stop_price is not None:
                    distance_in_pips = abs(entry_price - stop_price) * 100000
                    risk_per_lot = distance_in_pips * pip_cost
                    if risk_per_lot != 0:
                        pip_lots = round(risk_amount / risk_per_lot, 2)

                print(f"Final Entry Price: {entry_price}")
                print(f"Stop Price: {stop_price}")
                print(f"Limit Price: {limit_price}")
                print(f"Pip Lots: {pip_lots}")

                trade_data = {
                    "Date": target_date_str,
                    "Trend": daily_trend,
                    "SignalTime": signal_time,
                    "WPR": wpr_value,
                    "EntryStop": entry_stop,
                    "Support": support_val,
                    "Resistance": resistance_val,
                    "EntryPrice": entry_price,
                    "StopPrice": stop_price,
                    "LimitPrice": limit_price,
                    "Lots": pip_lots,
                }
                return trade_data

            except json.JSONDecodeError:
                return {"Date": target_date_str, "NoSignal": "Invalid JSON from GPT"}

        except Exception as e:
            return {"Date": target_date_str, "NoSignal": f"OpenAI error: {str(e)}"}

###############################################################################
# 4) FASTAPI ENDPOINT TO PROCESS A DATE RANGE AND RETURN SIGNALS
###############################################################################
@app.get("/signals")
def get_signals(start_date: str, end_date: str):
    """
    GET endpoint to process trade signals for a given date range.
    Query Parameters:
      - start_date: Start date in 'YYYY-MM-DD'
      - end_date: End date in 'YYYY-MM-DD'
    """
    try:
        start_date_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must be in YYYY-MM-DD format")

    if start_date_dt > end_date_dt:
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date")

    date_range = pd.date_range(start=start_date_dt, end=end_date_dt, freq="D")
    results = []
    for current_date in date_range:
        day_str = current_date.strftime("%Y-%m-%d")
        result = process_signal_for_date(day_str)
        results.append(result)

    return {"results": results}

###############################################################################
# MAIN: Run with Uvicorn
###############################################################################
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
