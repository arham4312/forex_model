import pandas as pd
import json
from openai import OpenAI
import re
import os
from datetime import timedelta, datetime

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
    # We'll track if a trade was successfully created
    trade_data = None  

    target_date_dt = pd.to_datetime(target_date_str).date()

    # This entire block is your existing logic, unmodified except we store results
    # in a local dictionary or set "no signal" accordingly.
    df_daily_for_date = df_daily[df_daily["datetime"].dt.date == target_date_dt]
    if df_daily_for_date.empty:
        return {"Date": target_date_str, "NoSignal": "No daily bar"}
    else:
        row_daily = df_daily_for_date.iloc[0]
        daily_trend = row_daily["trend"]
        print(f"Trend for {target_date_str}: {daily_trend}")

        if daily_trend not in ["BULLISH", "BEARISH"]:
            # Divergence or None => no signal
            return {"Date": target_date_str, "NoSignal": "Trend is DIVERGENCE or None"}

        # For the selected date, filter hourly data
        df_hourly.sort_values("datetime", ascending=True, inplace=True)
        day_start = pd.to_datetime(target_date_str + " 00:00:00")
        day_end = pd.to_datetime(target_date_str + " 23:59:59")

        df_hourly_day = df_hourly[
            (df_hourly["datetime"] >= day_start) & (df_hourly["datetime"] <= day_end)
        ].copy()

        # BULLISH => first hour W%R < -80
        # BEARISH => first hour W%R > -20
        if daily_trend == "BULLISH":
            df_signal = df_hourly_day[df_hourly_day["wpr_13"] < -80]
        else:  # BEARISH
            df_signal = df_hourly_day[df_hourly_day["wpr_13"] > -20]

        df_signal.sort_values("datetime", ascending=True, inplace=True)

        if df_signal.empty:
            return {"Date": target_date_str, "NoSignal": "No W%R signal found"}

        # Grab the earliest signal row
        first_signal = df_signal.iloc[0]
        signal_time = first_signal["datetime"]
        wpr_value = first_signal["wpr_13"]
        print(f"{daily_trend} signal at hour = {signal_time}, W%R={wpr_value:.2f}")

        # Calculate entry_stop
        entry_stop = None
        if daily_trend == "BULLISH":
            if pd.notna(first_signal["high_prev"]):
                last_closed_high = first_signal["high_prev"]
                entry_stop = last_closed_high + 0.00005  # 5 pips
                print(f"Entry Stop = {entry_stop} (previous high + 0.00005)")
            else:
                return {"Date": target_date_str, "NoSignal": "No previous candle high"}
        else:  # BEARISH
            if pd.notna(first_signal["low_prev"]):
                last_closed_low = first_signal["low_prev"]
                entry_stop = last_closed_low - 0.00005
                print(f"Entry Stop = {entry_stop} (previous low - 0.00005)")
            else:
                return {"Date": target_date_str, "NoSignal": "No previous candle low"}

        if entry_stop is None:
            # No valid entry stop => no trade
            return {"Date": target_date_str, "NoSignal": "entry_stop was None"}

        # 4) CALL OPENAI GPT API FOR SUPPORT / RESISTANCE
        start_30_days = day_start - pd.Timedelta(days=20)

        df_hourly.sort_values("datetime", ascending=True, inplace=True)
        df_30days = df_hourly[
            (df_hourly["datetime"] >= start_30_days)
            & (df_hourly["datetime"] < day_start)
        ].copy()

        data_string = df_30days.to_csv(index=False)


                # Build the prompt
        sr_prompt = f"""
    Identify support and resistance levels on an hourly Forex chart using a multi-timeframe approach.
    Start by analyzing higher timeframes (H4/D1) to mark major S/R zones and refine on the H1 chart.
    Focus on swing highs/lows, candle wick rejections, and psychological levels (e.g., round numbers).
    When selecting key support and resistance levels for a specific date, consider significant levels
    tested over the past 1-2 weeks (~120-240 candles) to find strong, well-tested zones.

    Ensure the chosen support and resistance have a gap of no more than 1000 pips (~0.01000),
    but if no strong levels fit within that range, select the most relevant zones outside that range.
    Prefer zones with multiple touches, rejection candles (pin bars, hammers), and high-volume reactions.

    Present the final support and resistance as single values based on the strongest zones.
    Format your response as JSON ONLY, following this structure:

    {{
    "resistance": "VALUE",
    "support": "VALUE"
    }}

    Do not include any extra text or explanations, only the JSON response.

    CURRENT DATE: {target_date_str}
    Below is the last 30 days (hourly) data:
    {data_string}
    """

        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a trading assistant that outputs JSON only."
                    },
                    {
                        "role": "user",
                        "content": sr_prompt
                    }
                ],
                temperature=0.0
            )
            raw_content = response.choices[0].message.content
            raw_content_clean = re.sub(r'```(?:json)?\s*', '', raw_content)
            raw_content_clean = re.sub(r'```', '', raw_content_clean)

            try:
                sr_data = json.loads(raw_content_clean)
                support_val = float(sr_data["support"])
                resistance_val = float(sr_data["resistance"])
                print("GPT S/R =>", sr_data)
                print(f"Parsed => Support = {support_val}, Resistance = {resistance_val}")

                # 5) Compute final entry price, stop, limit, lots, etc.
                entry_price = None
                stop_price = None
                limit_price = None
                account_size = 100000  # in USD
                risk_pct = 0.075       # 7.5%
                risk_amount = account_size * risk_pct
                pip_cost = 10          # Approx. pip cost for EUR/USD per standard lot
                pip_lots = None

                # Condition logic
                if daily_trend == "BULLISH":
                    condition = (resistance_val - entry_stop) > (entry_stop - support_val)
                else:  # BEARISH
                    condition = (resistance_val - entry_stop) < (entry_stop - support_val)

                if condition is None:
                    entry_price = None
                elif condition:
                    entry_price = entry_stop
                else:
                    entry_price = ((resistance_val - support_val) / 2.0) + support_val

                # Stop / Limit
                if daily_trend == "BULLISH":
                    stop_price = support_val - 0.0005
                    limit_price = resistance_val - 0.0001
                else:
                    stop_price = resistance_val + 0.0005
                    limit_price = support_val + 0.0001

                # Lots
                if entry_price is not None and stop_price is not None:
                    distance_in_pips = abs(entry_price - stop_price) * 100000
                    risk_per_lot = distance_in_pips * pip_cost
                    if risk_per_lot != 0:
                        pip_lots = round(risk_amount / risk_per_lot, 2)

                print(f"Final Entry Price: {entry_price}")
                print(f"Stop Price: {stop_price}")
                print(f"Limit Price: {limit_price}")
                print(f"Pip Lots: {pip_lots}")

                # 6) CREATE A TRADE DATA ROW
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
# 4) LOOP OVER THE LAST 6 MONTHS UP TO 2025-02-21
###############################################################################
end_date = datetime(2025, 2, 21).date()
start_date = end_date - pd.DateOffset(months=8)  # 8 months prior

# Convert to daily range (inclusive)
date_range = pd.date_range(start=start_date, end=end_date, freq='D')

csv_filename = "trade_signal_log.csv"
write_header = not os.path.exists(csv_filename)

# We'll process each day in ascending order
for current_date in date_range:
    day_str = current_date.strftime("%Y-%m-%d")
    result = process_signal_for_date(day_str)

    if "NoSignal" in result:
        # No signal => store a row with a minimal set of columns
        row_data = {
            "Date": result["Date"],
            "NoSignal": result["NoSignal"]
        }
        df_trade = pd.DataFrame([row_data])
        df_trade.to_csv(
            csv_filename, mode="a", index=False, header=write_header
        )
        write_header = False

    else:
        # We got a trade_data row => append to CSV
        df_trade = pd.DataFrame([result])
        df_trade.to_csv(
            csv_filename, mode="a", index=False, header=write_header
        )
        write_header = False

print(f"Done! Check {csv_filename} for all signals from {start_date.date()} to {end_date}.")
