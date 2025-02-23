import pandas as pd
import json
from openai import OpenAI
import re
from datetime import timedelta

###############################################################################
# 0) SET YOUR OPENAI API KEY
###############################################################################
# Either set it directly:
# Or rely on an environment variable: export OPENAI_API_KEY="..."
# Then skip the line above.

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
# Sort ascending to compute rolling
df_hourly.sort_values("datetime", ascending=True, inplace=True)

df_hourly["hh_13"] = df_hourly["high"].rolling(window=13).max()
df_hourly["ll_13"] = df_hourly["low"].rolling(window=13).min()
df_hourly["wpr_13"] = (
    (df_hourly["hh_13"] - df_hourly["close"])
    / (df_hourly["hh_13"] - df_hourly["ll_13"])
) * -100

df_hourly["high_prev"] = df_hourly["high"].shift(1)
df_hourly["low_prev"] = df_hourly["low"].shift(1)

# (Optional) sort descending if you want newest first for display
df_hourly.sort_values("datetime", ascending=False, inplace=True)

###############################################################################
# 3) GENERATE A SIGNAL FOR A GIVEN DATE
###############################################################################
target_date_str = "2024-07-18"
target_date_dt = pd.to_datetime(target_date_str).date()

# Filter daily data to find the trend
df_daily_for_date = df_daily[df_daily["datetime"].dt.date == target_date_dt]
if df_daily_for_date.empty:
    print(f"No daily bar for {target_date_str}")
else:
    row_daily = df_daily_for_date.iloc[0]
    daily_trend = row_daily["trend"]
    print(f"Trend for {target_date_str}: {daily_trend}")

    if daily_trend not in ["BULLISH", "BEARISH"]:
        print("No signal: trend is either DIVERGENCE or None.")
    else:
        # For the selected date, filter hourly data
        # We re-sort ascending so we can find the earliest signal
        df_hourly.sort_values("datetime", ascending=True, inplace=True)
        day_start = pd.to_datetime(target_date_str + " 00:00:00")
        day_end = pd.to_datetime(target_date_str + " 23:59:59")

        df_hourly_day = df_hourly[
            (df_hourly["datetime"] >= day_start) &
            (df_hourly["datetime"] <= day_end)
        ].copy()

        # BULLISH => find the first hour W%R < -80
        # BEARISH => find the first hour W%R > -20
        if daily_trend == "BULLISH":
            df_signal = df_hourly_day[df_hourly_day["wpr_13"] < -80]
        else:  # BEARISH
            df_signal = df_hourly_day[df_hourly_day["wpr_13"] > -20]

        df_signal.sort_values("datetime", ascending=True, inplace=True)

        if df_signal.empty:
            print(f"No {daily_trend} signal found for {target_date_str}")
        else:
            # Grab the earliest signal row
            first_signal = df_signal.iloc[0]
            signal_time = first_signal["datetime"]
            wpr_value = first_signal["wpr_13"]
            print(f"{daily_trend} signal at hour = {signal_time}, W%R={wpr_value:.2f}")

            if daily_trend == "BULLISH":
                if pd.notna(first_signal["high_prev"]):
                    last_closed_high = first_signal["high_prev"]
                    entry_stop = last_closed_high + 0.00005  # 5 pips
                    print(f"Entry Stop = {entry_stop} (previous high + 0.00005)")
                else:
                    print("No previous candle high found for that signal hour.")
            else:  # BEARISH
                if pd.notna(first_signal["low_prev"]):
                    last_closed_low = first_signal["low_prev"]
                    entry_stop = last_closed_low - 0.00005
                    print(f"Entry Stop = {entry_stop} (previous low - 0.00005)")
                else:
                    print("No previous candle low found for that signal hour.")

            ###############################################################################
            # 4) CALL OPENAI GPT API FOR SUPPORT / RESISTANCE
            ###############################################################################

            # Example: gather last 30 days of hourly data to pass to GPT
            start_30_days = day_start - pd.Timedelta(days=20)

            # Re-sort df_hourly ascending to slice the 30 days easily
            df_hourly.sort_values("datetime", ascending=True, inplace=True)
            df_30days = df_hourly[
                (df_hourly["datetime"] >= start_30_days) &
                (df_hourly["datetime"] < day_start)
            ].copy()

            # Convert that data to CSV for GPT prompt (watch out for token limits)
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

            # Now we call the OpenAI ChatCompletion endpoint
            try:
                # response = client.chat.completions.create(
                #     model="gpt-4o",  # or "gpt-3.5-turbo", etc.
                #     messages=[
                #         {
                #             "role": "system",
                #             "content": "You are a trading assistant that outputs JSON only."
                #         },
                #         {
                #             "role": "user",
                #             "content": sr_prompt
                #         }
                #     ],
                #     temperature=0.0  # For more deterministic output
                # )
                # raw_content = response.choices[0].message.content
                # raw_content_clean = re.sub(r'```(?:json)?\s*', '', raw_content)  # remove ```json or ```
                # raw_content_clean = re.sub(r'```', '', raw_content_clean)  
                # Example: raw_content might be:
                raw_content_clean=  json.dumps({"resistance": "1.0948", "support": "1.08715"})

                try:
                    sr_data = json.loads(raw_content_clean)
                    support_val = float(sr_data["support"])
                    resistance_val = float(sr_data["resistance"])
                    print("GPT S/R =>", sr_data)
                    print(f"Parsed => Support = {support_val}, Resistance = {resistance_val}")
                except json.JSONDecodeError:
                    print("GPT returned invalid JSON or additional text:")
                    print(raw_content_clean)

            except Exception as e:
                print("OpenAI API error:", str(e))
