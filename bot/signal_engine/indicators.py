import pandas as pd
import numpy as np
from typing import Tuple


# ---------------------------------------------------------------------------
# RSI — Relative Strength Index
# ---------------------------------------------------------------------------

def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Standard Wilder RSI.
    Returns a Series of RSI values (0-100). NaN for first `period` rows.
    """
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.rename("rsi")


# ---------------------------------------------------------------------------
# MACD — Moving Average Convergence Divergence
# ---------------------------------------------------------------------------

def calculate_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Returns (macd_line, signal_line, histogram).
    macd_line   = EMA(fast) - EMA(slow)
    signal_line = EMA(macd_line, signal)
    histogram   = macd_line - signal_line
    """
    ema_fast   = close.ewm(span=fast, adjust=False).mean()
    ema_slow   = close.ewm(span=slow, adjust=False).mean()
    macd_line  = (ema_fast - ema_slow).rename("macd")
    signal_line = macd_line.ewm(span=signal, adjust=False).mean().rename("macd_signal")
    histogram  = (macd_line - signal_line).rename("macd_hist")
    return macd_line, signal_line, histogram


# ---------------------------------------------------------------------------
# ATR — Average True Range
# ---------------------------------------------------------------------------

def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """
    Wilder ATR. Used for dynamic SL buffer sizing.
    """
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return atr.rename("atr")


# ---------------------------------------------------------------------------
# Swing Highs and Lows
# ---------------------------------------------------------------------------

def find_swing_high(high: pd.Series, lookback: int = 10) -> float:
    """
    Returns the highest high over the last `lookback` candles.
    Used on 4H to define the top of the retracement range.
    """
    return float(high.iloc[-lookback:].max())


def find_swing_low(low: pd.Series, lookback: int = 10) -> float:
    """
    Returns the lowest low over the last `lookback` candles.
    Used on 4H to define the bottom of the retracement range.
    """
    return float(low.iloc[-lookback:].min())


# ---------------------------------------------------------------------------
# Fibonacci Retracement Levels
# ---------------------------------------------------------------------------

FIB_LEVELS = {
    "0.236": 0.236,
    "0.382": 0.382,
    "0.500": 0.500,
    "0.618": 0.618,
    "0.786": 0.786,
}

def calculate_fib_levels(swing_high: float, swing_low: float) -> dict:
    """
    Returns price levels for each Fibonacci ratio.
    For an uptrend: price retraces DOWN from high, so levels are below swing_high.
    fib_price = swing_high - (ratio * range)
    """
    price_range = swing_high - swing_low
    return {
        label: round(swing_high - ratio * price_range, 6)
        for label, ratio in FIB_LEVELS.items()
    }


def get_fib_zone(swing_high: float, swing_low: float) -> Tuple[float, float]:
    """
    Returns (zone_bottom, zone_top) for the 38.2%–61.8% golden zone.
    This is the primary OB/FVG hunting area per the strategy.
    """
    levels = calculate_fib_levels(swing_high, swing_low)
    return levels["0.618"], levels["0.382"]   # bottom, top


# ---------------------------------------------------------------------------
# Order Block Detection
# ---------------------------------------------------------------------------

def find_order_blocks(
    df: pd.DataFrame,
    direction: str = "bullish",
    lookback: int = 20,
) -> list[dict]:
    """
    Detects Order Blocks (OB) in a OHLCV DataFrame.

    Bullish OB: the last bearish candle before a strong bullish move.
    - A bearish candle (close < open)
    - Followed by a bullish candle that closes above the bearish open
    - The OB zone = [low of bearish candle, high of bearish candle]

    Returns a list of dicts: {top, bottom, index, strength}
    """
    obs = []
    window = df.iloc[-lookback:]

    for i in range(1, len(window) - 1):
        prev = window.iloc[i - 1]
        curr = window.iloc[i]

        if direction == "bullish":
            is_bearish_candle = prev["close"] < prev["open"]
            is_bullish_follow = curr["close"] > prev["open"]
            if is_bearish_candle and is_bullish_follow:
                strength = (curr["close"] - prev["open"]) / (prev["high"] - prev["low"] + 1e-9)
                obs.append({
                    "top":      prev["high"],
                    "bottom":   prev["low"],
                    "index":    window.index[i - 1],
                    "strength": round(strength, 3),
                })

        elif direction == "bearish":
            is_bullish_candle  = prev["close"] > prev["open"]
            is_bearish_follow  = curr["close"] < prev["open"]
            if is_bullish_candle and is_bearish_follow:
                strength = (prev["open"] - curr["close"]) / (prev["high"] - prev["low"] + 1e-9)
                obs.append({
                    "top":      prev["high"],
                    "bottom":   prev["low"],
                    "index":    window.index[i - 1],
                    "strength": round(strength, 3),
                })

    return sorted(obs, key=lambda x: x["strength"], reverse=True)


# ---------------------------------------------------------------------------
# Fair Value Gap Detection
# ---------------------------------------------------------------------------

def find_fvgs(
    df: pd.DataFrame,
    direction: str = "bullish",
    lookback: int = 20,
) -> list[dict]:
    """
    Detects Fair Value Gaps (FVG) — 3-candle imbalance patterns.

    Bullish FVG: gap between candle[i-2].high and candle[i].low
      - candle[i-2].high < candle[i].low  → unfilled gap above
    Bearish FVG: gap between candle[i-2].low and candle[i].high
      - candle[i-2].low > candle[i].high  → unfilled gap below

    Returns list of dicts: {top, bottom, index, size}
    """
    fvgs = []
    window = df.iloc[-lookback:]

    for i in range(2, len(window)):
        c0 = window.iloc[i - 2]   # oldest of the 3
        c2 = window.iloc[i]       # newest of the 3

        if direction == "bullish":
            gap_bottom = c0["high"]
            gap_top    = c2["low"]
            if gap_top > gap_bottom:
                fvgs.append({
                    "top":    gap_top,
                    "bottom": gap_bottom,
                    "index":  window.index[i - 1],
                    "size":   round(gap_top - gap_bottom, 6),
                })

        elif direction == "bearish":
            gap_top    = c0["low"]
            gap_bottom = c2["high"]
            if gap_top > gap_bottom:
                fvgs.append({
                    "top":    gap_top,
                    "bottom": gap_bottom,
                    "index":  window.index[i - 1],
                    "size":   round(gap_top - gap_bottom, 6),
                })

    return sorted(fvgs, key=lambda x: x["size"], reverse=True)


# ---------------------------------------------------------------------------
# Candle Pattern Detection
# ---------------------------------------------------------------------------

def detect_candle_pattern(candle: pd.Series, atr: float) -> str | None:
    """
    Detects entry-level candle patterns on 5M.
    Returns pattern name or None.

    candle must have: open, high, low, close
    atr is used to filter out tiny candles (< 0.3 * ATR = noise)
    """
    o, h, l, c = candle["open"], candle["high"], candle["low"], candle["close"]
    body   = abs(c - o)
    candle_range = h - l

    if candle_range < 0.3 * atr:
        return None   # too small, ignore

    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l

    # Bullish engulfing: body covers > 70% of range, closes bullish
    if c > o and body / candle_range > 0.70:
        return "engulfing"

    # Doji: body < 10% of range
    if body / candle_range < 0.10:
        return "doji"

    # Bullish pin bar / hammer: lower wick > 2× body, upper wick small
    if lower_wick > 2 * body and upper_wick < body and c > o:
        return "pin_bar"

    # Bullish marubozu: almost no wicks, strong close
    if body / candle_range > 0.85 and c > o:
        return "marubozu"

    return None


# ---------------------------------------------------------------------------
# Trend Detection
# ---------------------------------------------------------------------------

def detect_trend(close: pd.Series, fast: int = 20, slow: int = 50) -> str:
    """
    Simple EMA crossover trend on 4H.
    Returns "bullish", "bearish", or "ranging".
    """
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()

    last_fast = ema_fast.iloc[-1]
    last_slow = ema_slow.iloc[-1]
    diff_pct  = abs(last_fast - last_slow) / last_slow * 100

    if last_fast > last_slow and diff_pct > 0.3:
        return "bullish"
    elif last_fast < last_slow and diff_pct > 0.3:
        return "bearish"
    else:
        return "ranging"